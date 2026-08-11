"""Live captions: storing each turn of speech and publishing it in the languages read.

The flow is one round trip. A turn is finalised, the agent posts it to the API, the API
stores it and returns it rendered into every language currently being watched, and the
agent publishes that to the room. Translating in the same call is deliberate: the caption
cannot be shown until it is translated, so a second request would sit squarely between
someone finishing a sentence and the other person reading it.

Attribution is the weak point, and it is worth stating plainly rather than discovering it
in a transcript. The realtime model receives every participant mixed into a single audio
stream, so it cannot say who spoke — `speaker_id` is populated on the plugin's STT path,
never on the realtime one. The speaker is therefore taken from LiveKit's own active
speaker detection, which is right whenever one person is talking and guesses when two
people talk over each other.
"""
import asyncio
import json
import logging

import httpx
from livekit import rtc

logger = logging.getLogger(__name__)

# The attribute a client sets on itself to say what language it is reading captions in.
CAPTION_LANGUAGE_ATTRIBUTE = "caption_lang"

# The room data topic captions are published on. Clients filter on it so a caption is
# never confused with the source_added messages already travelling this channel.
CAPTION_TOPIC = "captions"

AGENT_IDENTITY = "agent"


def speaker_role(identity: str) -> str:
    """host, guest or agent, from the LiveKit identity alone.

    A guest joins as `guest-{invitation_id}`; everyone else joins under their user id.
    This is the same rule the API applies, kept in step deliberately — a caption
    attributed to a role the server disagrees with would be stored as one thing and
    displayed as another.
    """
    if identity == AGENT_IDENTITY:
        return "agent"
    return "guest" if identity.startswith("guest-") else "host"


# Set by a participant who has told the room they are speaking only to the agent. Their
# microphone is then subscribable by the agent alone — enforced by the server, not by
# politeness — and this attribute is how the agent learns that what it hears from them is
# direction rather than conversation.
PRIVATE_TO_AGENT_ATTRIBUTE = "private_to_agent"


def speaks_only_to_agent(room: rtc.Room, identity: str) -> bool:
    """Whether this participant has the private toggle on.

    Read at the moment it matters rather than remembered: the toggle is flipped mid-sentence
    in normal use — a clerk turns it on to dictate and off to talk to the room — and a cached
    answer would apply the previous state to the current words.
    """
    if not identity:
        return False
    participant = room.remote_participants.get(identity)
    if participant is None:
        return False
    return (participant.attributes or {}).get(PRIVATE_TO_AGENT_ATTRIBUTE) == "1"


def requested_languages(room: rtc.Room) -> list[str]:
    """Every distinct language the people in this room are reading captions in.

    Read from participant attributes rather than held in the agent's own state: a viewer
    who changes language mid-conversation updates their attribute, and the next turn is
    translated for them without anything having to be told.

    Sorted so the same set of viewers produces the same request every time, which keeps
    the API's cache keys stable and the logs comparable.
    """
    languages = set()
    for participant in room.remote_participants.values():
        chosen = (participant.attributes or {}).get(CAPTION_LANGUAGE_ATTRIBUTE)
        if chosen and chosen.strip():
            languages.add(chosen.strip())
    return sorted(languages)


class CaptionPublisher:
    """Posts finalised turns to the API and publishes the result to the room."""

    def __init__(self, room: rtc.Room, api_url: str, salon_id: str, host_token: str) -> None:
        self._room = room
        self._api_url = api_url
        self._salon_id = salon_id
        self._host_token = host_token
        # Who spoke last, according to LiveKit. Kept rather than read on demand because
        # by the time a transcript is final the speaker has usually stopped talking and
        # room.active_speakers is already empty.
        self._last_speaker: str | None = None

    def track_active_speakers(self) -> None:
        """Follow who is speaking, so a finalised turn can be attributed to someone."""

        def _on_change(speakers) -> None:
            for speaker in speakers:
                if speaker.identity and speaker.identity != self._room.local_participant.identity:
                    self._last_speaker = speaker.identity
                    break

        self._room.on("active_speakers_changed", _on_change)

    def attributed_speaker(self) -> str:
        """The best available guess at who just spoke.

        Falls back to the only remote participant when there is exactly one, which is
        both the common case and the one where a guess cannot be wrong. Beyond that it
        falls back to the last active speaker, and finally to "unknown" — a caption
        attributed to nobody is still worth showing.
        """
        remote = [p.identity for p in self._room.remote_participants.values() if p.identity]
        if len(remote) == 1:
            return remote[0]
        if self._last_speaker in remote:
            return self._last_speaker
        return self._last_speaker or (remote[0] if remote else "unknown")

    async def publish(
        self,
        *,
        text: str,
        identity: str,
        language: str | None = None,
        speaker_name: str | None = None,
    ) -> None:
        """Store one turn and put it on the wire in every language being watched.

        `speaker_name` is passed straight through to the API's own `display_label` — see
        that function for what it does with it. Omitted, this caption is labelled exactly
        as it always was; nothing here looks a name up.

        Best-effort from end to end. A caption that fails to store, fails to translate or
        fails to publish must never interrupt the conversation it is describing.
        """
        text = (text or "").strip()
        if not text:
            return

        payload = {
            "speakerIdentity": identity,
            "speakerRole": speaker_role(identity),
            "speakerName": speaker_name,
            "text": text,
            "language": language,
            "targetLanguages": requested_languages(self._room),
        }

        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                response = await client.post(
                    f"{self._api_url}/salons/{self._salon_id}/utterances",
                    json=payload,
                    headers={"Authorization": f"Bearer {self._host_token}"},
                )
            if response.status_code != 201:
                logger.warning("Caption not stored: HTTP %s", response.status_code)
                return
            stored = response.json()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Caption not stored: %s", exc)
            return

        message = {
            "type": "caption",
            "sequence": stored.get("sequence"),
            "speaker": stored.get("speaker"),
            "speakerIdentity": identity,
            "role": stored.get("role"),
            # As spoken, so a viewer reading a translation can see what it came from.
            "text": stored.get("text"),
            "language": stored.get("language"),
            # Keyed by language. A language whose translation failed is absent, which is
            # what tells the client to fall back to the spoken text rather than show a
            # caption it wrongly believes is translated.
            "translations": stored.get("translations") or {},
            "spokenAt": stored.get("spokenAt"),
        }

        try:
            await self._room.local_participant.publish_data(
                json.dumps(message).encode("utf-8"),
                reliable=True,
                topic=CAPTION_TOPIC,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Caption not published: %s", exc)

    def publish_soon(
        self,
        *,
        text: str,
        identity: str,
        language: str | None = None,
        speaker_name: str | None = None,
    ) -> None:
        """Fire and forget, for use from synchronous event handlers.

        The SDK dispatches events synchronously; awaiting the API from inside one would
        stall the salon for the duration of a network call.
        """
        asyncio.create_task(
            self.publish(
                text=text, identity=identity, language=language, speaker_name=speaker_name
            )
        )
