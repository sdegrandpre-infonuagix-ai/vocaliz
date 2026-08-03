"""
Vocaliz – LiveKit Agent Worker
Entry point for the xAI-powered voice discussion agent.
"""

import asyncio
import json
import logging
import os
from typing import Annotated

import httpx
from dotenv import load_dotenv
from livekit import agents
from livekit.agents import AgentSession, Agent, function_tool, inference
# RoomOptions is not re-exported at the livekit.agents top level the way RoomInputOptions
# was, so it has to be imported from its own module.
from livekit.agents.voice.room_io import RoomOptions
from livekit.plugins import xai, silero

from src.captions import CaptionPublisher
from src.mixed_audio_input import MixedParticipantAudioInput

# override=True is deliberate: load_dotenv() otherwise leaves pre-existing OS
# environment variables untouched, so a stale machine-wide XAI_API_KEY silently wins
# over agent/.env and the realtime handshake fails with an opaque 400.
load_dotenv(override=True)
logger = logging.getLogger("salon-agent")

# Must match SALON_AGENT_NAME in api/src/services/livekit_service.py — the API dispatches
# by this exact name, and a mismatch means the agent is simply never dispatched.
AGENT_NAME = "salon-agent"

# How much of the session cap is left when the agent starts winding the conversation down.
# Slightly more than one heartbeat interval, so the warning cannot be skipped by landing
# between two beats — at 30 s exactly, a heartbeat reporting 31 s then 1 s would jump the
# threshold and the announcement would never fire.
ENDING_WARNING_SECONDS = 75

_BASE_INSTRUCTIONS = (
    "You are Vocaliz, a sophisticated voice discussion facilitator. "
    "Your role is to animate intellectually stimulating conversations "
    "between participants about documents, articles, or current events. "
    "\n\n"
    "NATURAL CONVERSATION (no wake word required): "
    "You respond whenever a participant finishes speaking — detected by a natural pause "
    "after their utterance. Never require a special invocation phrase. "
    "In multi-participant sessions, wait for a genuine conversational pause before "
    "speaking; do not interrupt a breath or a momentary hesitation. "
    "\n\n"
    "INTERVENTION FREQUENCY (default — same-language sessions): "
    "Intervene at most once per minute. Keep each intervention brief and focused: "
    "one question or observation, then yield the floor. "
    "When a participant explicitly asks you to change your frequency, call "
    "set_intervention_frequency immediately and honor the new mode for the rest of the session:\n"
    "  • 'parle moins souvent', 'interviens moins', 'tais-toi un peu', "
    "'laisse-nous parler', 'moins souvent' → direction='less' (once every 3 minutes)\n"
    "  • 'parle plus souvent', 'interviens plus', 'anime plus', "
    "'tu peux participer davantage' → direction='more' (every 30 seconds)\n"
    "  • 'c'est bien comme ça', 'rythme normal', 'reviens à la normale' → direction='normal'\n"
    "Translate the spoken request mentally — the participant may say it in any language.\n"
    "\n\n"
    "LANGUAGE DETECTION (automatic — no configuration required): "
    "Detect the language of each participant from their speech as soon as they start talking. "
    "Never ask participants to configure or select a language. "
    "Respond to each participant in the exact language they are using — "
    "if they speak French, answer in French; if they speak English, answer in English; "
    "and so on for any language you understand. "
    "In multi-participant sessions where participants speak different languages, "
    "address each person in their own language. "
    "Once a participant's language is detected, maintain it for the entire session "
    "unless they explicitly switch to a different language themselves. "
    "This applies to all facilitation, questions, source introductions, and confirmations. "
    "When you detect the HOST's language for the first time, call report_detected_language "
    "with the BCP-47 code (e.g. 'fr' for French, 'en' for English, 'es' for Spanish). "
    "Call this tool only once per session — on first detection, not on every utterance. "
    "\n"
    "Separately, the FIRST time you hear ANY participant speak — host and guests alike "
    "— call report_participant_language once with their LiveKit identity and that "
    "language. Report what you heard first, not what they end up speaking most: it is "
    "recorded once and never revised. Use the identity, not the display name. "
    "\n\n"
    "TRANSCRIPTION NOTICE (everyone, before the conversation begins):\n"
    "The FIRST time each participant speaks, tell them in ONE short sentence, in their\n"
    "own language, that what is said here is transcribed and kept so that everyone can\n"
    "read it in the language they choose. Say it plainly, as a fact about the room, and\n"
    "do not ask for permission or wait for an answer — they can leave if they object.\n"
    "This is not optional and it is not the same as the sponsorship aside below: say it\n"
    "to returning participants too, and say it even when there is nothing else to say.\n"
    "The written notice on the page cannot be relied on — a participant may have joined\n"
    "by telephone, or never looked at the screen.\n"
    "\n\n"
    "SPONSORSHIP MENTION (newcomers only, once):\n"
    "Before greeting someone, call is_first_salon with their LiveKit identity.\n"
    "If it answers 'first_salon', add ONE short sentence to your welcome: a business\n"
    "wishing to advertise in the Salons can contact Infonuagix.ai, the company that built\n"
    "Vocaliz. If it answers 'returning', say nothing about it at all — they have heard it.\n"
    "Say it in the participant's language, once, and never bring it up again: repeating\n"
    "it, or pressing it, would turn a conversation into a sales call. Then move straight\n"
    "on to the topic — the mention is an aside, not the point of the greeting.\n"
    "\n\n"
    "ANSWERING FROM THE SOURCES:\n"
    "What you were given is a summary of the documents, not the documents themselves.\n"
    "When a participant asks about a figure, a name, a quotation or a passage your\n"
    "summary does not carry, call search_source with their keywords before answering.\n"
    "Never invent a detail to fill the gap, and never claim the source is silent on\n"
    "something without having searched. If the search returns nothing, say plainly that\n"
    "the source does not appear to address it.\n"
    "\n\n"
    "SIMULTANEOUS TRANSLATION (multilingual sessions):\n"
    "When participants speak different languages, translate each utterance for the listener(s):\n"
    "1. Wait for the speaker to finish (natural pause) — NEVER interrupt mid-sentence.\n"
    "2. Call mute_translation_recipient to prevent echo before you speak.\n"
    "3. Speak the translation in the listener's language — convey meaning naturally, "
    "not word-for-word. Keep it concise.\n"
    "4. After finishing the translation, call unmute_translation_recipient.\n"
    "Do NOT translate your own facilitator speech — only translate between human participants.\n"
    "In a 3-way session with mixed languages, translate for each non-native listener in turn.\n"
    "\n\n"
    "INVITATION COMMANDS: When the host says 'invite [name]' or 'invite [name] at "
    "[email address]', call invite_contact with the guest's email address. "
    "If the host gives only a name with no address, politely ask: "
    "'Quelle est l'adresse courriel de [name] ?' before calling the tool. "
    "If the invitation succeeds for a Vocaliz user, say: "
    "'J\\'ai envoyé une notification à [name] pour rejoindre le salon.' "
    "If the guest has no Vocaliz account, a join link is emailed to them — say: "
    "'J\\'ai envoyé un lien par courriel à [name] pour rejoindre le salon.' "
    "If the call fails, say: 'Je n\\'ai pas pu inviter ce contact. Pouvez-vous vérifier "
    "l\\'adresse courriel ?' "
    "\n\n"
    "SESSION EXIT (vocal command — any language):\n"
    "When any participant says a phrase indicating they want to leave, such as:\n"
    "  FR: 'Je quitte le Salon', 'je m'en vais', 'je dois partir', 'au revoir'\n"
    "  EN: 'I'm leaving the Salon', 'I have to go', 'goodbye', 'I'm done'\n"
    "  ES: 'Me voy del Salón', 'tengo que irme', 'adiós'\n"
    "  (or an equivalent farewell in any language)\n"
    "then follow this exact three-step sequence:\n"
    "1. Acknowledge their departure warmly in their language (one sentence).\n"
    "2. Immediately ask the satisfaction question in their language:\n"
    "   FR: 'Est-ce que votre conversation dans Vocaliz a été une belle expérience ?'\n"
    "   EN: 'Was your conversation in Vocaliz a wonderful experience?'\n"
    "   ES: '¿Fue tu conversación en Vocaliz una bella experiencia?'\n"
    "   (use the participant's detected language; default to French if unknown)\n"
    "3. After they reply (or after a natural pause of ~3 seconds if no reply),\n"
    "   thank them briefly and call end_session to close the session. Pass their\n"
    "   answer as `enjoyed`: true if positive, false if negative, and leave it unset\n"
    "   if they did not answer — silence is not a complaint.\n"
    "IMPORTANT: You MUST ask the satisfaction question before calling end_session.\n"
    "Do NOT skip directly to end_session — the question is mandatory.\n"
    "\n\n"
    "GUESTS WITHOUT AN ACCOUNT (display name 'Guest' followed by four characters):\n"
    "A browser guest was invited by name, to an email address the host typed in. They\n"
    "are not anonymous — they simply have no Vocaliz account. Rules for them:\n"
    "- Ask the satisfaction question exactly as you would for a registered user.\n"
    "  Their verbal response is valuable even without a profile.\n"
    "- Do NOT call report_detected_language for these guests — that one writes to an\n"
    "  account, and they have none. DO call report_participant_language for them: it\n"
    "  records against the salon, which works for everyone.\n"
    "- A guest joining via browser appears as 'Guest 3F2A' or similar — the four\n"
    "  characters distinguish one guest from another.\n"
    "- Treat a guest without an account as a full participant for facilitation and exit.\n"
)

_CONTENT_PREVIEW_CHARS = 2500
_EXTRA_SOURCE_PREVIEW_CHARS = 1000


def _build_instructions(
    source_content: str | None = None,
    source_type: str | None = None,
    source_url: str | None = None,
    additional_sources: list[dict] | None = None,
    source_summary: str | None = None,
) -> str:
    """Build agent instructions, injecting session content for facilitation and contrast.

    The summary is preferred over the raw text, and that is the whole point: the first
    2 500 characters of a forty-page document were its table of contents, so the agent
    opened conversations on a page and a half it mistook for the whole thing. The summary
    covers all of it, in the host's language, for a fraction of the context — which
    matters because a realtime session reprocesses that context on every turn.

    The truncation remains as the fallback. A summariser that is unreachable or
    unconfigured must degrade to the old behaviour, not to silence.
    """
    instructions = _BASE_INSTRUCTIONS
    additional_sources = additional_sources or []

    body = source_summary or source_content
    if body:
        # Only truncate when falling back to raw text; a summary is already short by
        # construction and cutting it would remove the end of the argument.
        if source_summary:
            preview, ellipsis = source_summary, ""
        else:
            preview = source_content[:_CONTENT_PREVIEW_CHARS]
            ellipsis = "…" if len(source_content) > _CONTENT_PREVIEW_CHARS else ""
        source_label = source_url or f"uploaded {source_type or 'document'}"

        instructions += (
            "\n\n"
            "SESSION CONTENT:\n"
            f"Source: {source_label}\n\n"
            f"{preview}{ellipsis}\n\n"
            "OPENING BEHAVIOR — do this IMMEDIATELY when the first participant joins:\n"
            "1. Greet them warmly in 1-2 sentences.\n"
            "2. Introduce the topic: what it is about and why it is worth discussing (2-3 sentences).\n"
            "3. Read the 2-3 most important passages or ideas from the content above, verbatim or paraphrased.\n"
            "4. Ask one open, thought-provoking question to start the discussion.\n\n"
            "This ensures every participant can engage fully, even without prior reading.\n"
        )
    else:
        instructions += (
            "\n\n"
            "No source content was attached to this session. "
            "Greet participants and invite them to share what they would like to discuss. "
            "Facilitate naturally from there.\n"
        )

    if additional_sources:
        instructions += "\n\nADDITIONAL SOURCES (added during session):\n"
        for i, src in enumerate(additional_sources, 1):
            summary = src.get("sourceSummary")
            content = src.get("sourceContent") or ""
            label = src.get("sourceUrl") or f"document {i}"
            # Same rule as the opening source: the brief when there is one, the first
            # thousand characters only as a fallback.
            if summary:
                preview, ellipsis = summary, ""
            else:
                preview = content[:_EXTRA_SOURCE_PREVIEW_CHARS]
                ellipsis = "…" if len(content) > _EXTRA_SOURCE_PREVIEW_CHARS else ""
            instructions += f"\n[Source {i}] {label}\n{preview}{ellipsis}\n"

        instructions += (
            "\n"
            "CONTRAST FACILITATION:\n"
            "Monitor the discussion for moments when one of the additional sources above "
            "provides a contrasting or complementary perspective to what is being said. "
            "When such a moment arises (at most once every 2–3 minutes), introduce the "
            "contrasting information by explicitly citing its source, e.g. "
            "'According to [source label], ...' or 'In contrast, [source] argues that ...' "
            "This enriches the discussion without overwhelming participants.\n"
        )

    return instructions


class SalonAgent(Agent):
    """Voice discussion agent powered by xAI Grok."""

    def __init__(
        self,
        session_id: str | None = None,
        api_url: str | None = None,
        host_token: str | None = None,
        source_content: str | None = None,
        source_type: str | None = None,
        source_url: str | None = None,
        additional_sources: list[dict] | None = None,
        source_summary: str | None = None,
        room=None,
    ) -> None:
        instructions = _build_instructions(
            source_content=source_content,
            source_type=source_type,
            source_url=source_url,
            additional_sources=additional_sources,
            source_summary=source_summary,
        )
        super().__init__(instructions=instructions)
        self._session_id = session_id
        self._api_url = api_url
        self._host_token = host_token
        self._frequency_preference: str = "normal"
        self._room = room
        self._heartbeat_task: asyncio.Task | None = None
        self._heartbeat_interval: int = 30
        self._ending_announced: bool = False

    @function_tool
    async def set_intervention_frequency(
        self,
        direction: Annotated[
            str,
            "Desired frequency adjustment: 'less' to speak less often (once every 3 min), "
            "'more' to speak more often (every 30 s), 'normal' to reset to default (once/min)",
        ],
    ) -> str:
        """Adjust how often the agent intervenes in the conversation.

        Call this immediately when a participant requests a frequency change,
        then honor the new mode for the remainder of the session.
        Speak the returned confirmation message aloud so participants know their
        preference was registered.
        """
        if direction not in ("less", "normal", "more"):
            direction = "normal"
        self._frequency_preference = direction
        confirmations = {
            "less": "Bien sûr, je vais intervenir moins souvent et vous laisser plus d'espace.",
            "normal": "Je reviens à un rythme d'intervention normal, une fois par minute environ.",
            "more": "D'accord, je vais participer plus activement à la conversation.",
        }
        logger.info("Frequency preference set to: %s", direction)
        return confirmations[direction]

    async def _broadcast_translation_control(self, action: str) -> None:
        """Publish a translation control data message to all room participants."""
        if not self._room:
            return
        payload = json.dumps({"action": action}).encode()
        try:
            await self._room.local_participant.publish_data(payload, reliable=True)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to publish translation control '%s': %s", action, exc)

    @function_tool
    async def mute_translation_recipient(self) -> str:
        """Mute all remote participants' microphones before reading a translation.

        Call this immediately before speaking a translated utterance to prevent
        the recipient from echoing the translation audio back into the shared stream.
        After finishing the translation, call unmute_translation_recipient.
        """
        await self._broadcast_translation_control("translation_mute_start")
        logger.info("Translation mute signal sent")
        return "muted"

    @function_tool
    async def unmute_translation_recipient(self) -> str:
        """Unmute all remote participants' microphones after finishing a translation.

        Call this immediately after you have finished speaking the translated text.
        """
        await self._broadcast_translation_control("translation_mute_end")
        logger.info("Translation unmute signal sent")
        return "unmuted"

    @function_tool
    @function_tool
    async def search_source(
        self,
        query: Annotated[
            str,
            "What you are looking for, in the words the participant used. Keywords work "
            "better than a full question — the search matches vocabulary, not meaning.",
        ],
    ) -> str:
        """Look up a detail in the salon's sources that your summary does not carry.

        You hold a brief of the documents, not the documents. When someone asks about a
        figure, a name or a passage the brief does not mention, search for it here rather
        than guessing or saying the source does not cover it.

        Returns the matching passages, or nothing when the words do not appear. Nothing
        found is a real answer: say the source does not seem to address it.
        """
        if not self._session_id or not self._api_url or not self._host_token:
            return "no_session_context"

        url = f"{self._api_url}/sessions/{self._session_id}/search"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    url,
                    params={"q": query},
                    headers={"Authorization": f"Bearer {self._host_token}"},
                )
            if resp.status_code != 200:
                logger.warning("search_source returned %s", resp.status_code)
                return "no_results"
            excerpts = resp.json().get("excerpts") or []
            if not excerpts:
                return "no_results"
            return "\n\n---\n\n".join(excerpts)
        except Exception as exc:  # noqa: BLE001
            logger.warning("search_source failed: %s", exc)
            return "no_results"

    @function_tool
    async def is_first_salon(
        self,
        participant_identity: Annotated[
            str,
            "The LiveKit identity of the participant you are greeting, exactly as it "
            "appears in the room. Not their display name.",
        ],
    ) -> str:
        """Whether this is the participant's very first salon.

        Ask before mentioning sponsorship in a welcome: the aside is for newcomers, and
        someone on their fifth salon has heard it four times too many.

        Returns "first_salon" or "returning". On any doubt it answers "first_salon" —
        saying it once too often is a smaller failure than never saying it.
        """
        if not self._session_id or not self._api_url or not self._host_token:
            return "first_salon"

        url = f"{self._api_url}/sessions/{self._session_id}/participant-history"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    url,
                    params={"identity": participant_identity},
                    headers={"Authorization": f"Bearer {self._host_token}"},
                )
            if resp.status_code != 200:
                return "first_salon"
            return "first_salon" if resp.json().get("firstSalon") else "returning"
        except Exception as exc:  # noqa: BLE001
            logger.warning("is_first_salon failed: %s", exc)
            return "first_salon"

    @function_tool
    async def report_participant_language(
        self,
        participant_identity: Annotated[
            str,
            "The LiveKit identity of the participant, exactly as it appears in the room "
            "(a guest looks like 'guest-<uuid>'). Not their display name.",
        ],
        language_code: Annotated[
            str, "BCP-47 code of the first language you heard them speak, e.g. 'fr', 'en'"
        ],
    ) -> str:
        """Record the first language one participant spoke in this salon.

        Call once per participant, on first hearing them — guests included. Unlike
        report_detected_language, which sets a property of the host's account, this belongs
        to the participation: the same person may speak French here and English tomorrow.

        Reporting again is harmless; the first value is kept.
        """
        if not self._session_id or not self._api_url or not self._host_token:
            return "no_session_context"

        url = f"{self._api_url}/sessions/{self._session_id}/participant-language"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    url,
                    json={
                        "participantIdentity": participant_identity,
                        "language": language_code,
                    },
                    headers={"Authorization": f"Bearer {self._host_token}"},
                )
            if resp.status_code == 200:
                return f"language_recorded:{language_code}"
            logger.warning("report_participant_language returned %s", resp.status_code)
            return f"error:{resp.status_code}"
        except Exception as exc:  # noqa: BLE001
            logger.warning("report_participant_language failed: %s", exc)
            return "error:network"

    async def report_detected_language(
        self,
        language_code: Annotated[
            str,
            "BCP-47 language code detected from the host's speech, e.g. 'fr', 'en', 'es', 'pt'",
        ],
    ) -> str:
        """Persist the host's detected spoken language to the API.

        Call this once when you first identify the language the host is speaking.
        The mobile app reads this to display its interface in the detected language.
        """
        if not self._session_id or not self._api_url or not self._host_token:
            logger.warning("report_detected_language called but agent has no session context")
            return "no_session_context"

        url = f"{self._api_url}/me/language"
        headers = {"Authorization": f"Bearer {self._host_token}"}
        payload = {"language": language_code}

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.patch(url, json=payload, headers=headers)
            if resp.status_code == 200:
                logger.info("Detected language '%s' persisted for host", language_code)
                return f"language_reported:{language_code}"
            logger.warning("report_detected_language returned %s", resp.status_code)
            return f"error:{resp.status_code}"
        except Exception as exc:  # noqa: BLE001
            logger.exception("report_detected_language exception: %s", exc)
            return "error:network"

    @function_tool
    async def end_session(
        self,
        enjoyed: Annotated[
            bool | None,
            "Whether the participant said the conversation was a good experience. "
            "True for yes, False for no, and None when they did not answer — leave it "
            "None rather than guessing, since an unanswered question is not a complaint.",
        ] = None,
    ) -> str:
        """Mark the current session as ended in the API.

        Call this as the final step of the session exit flow — AFTER acknowledging
        the participant's departure and asking the satisfaction question.
        This closes the session and signals all clients to disconnect.

        Pass along the answer to the satisfaction question: the agent is the only party
        that hears it, so it is the only one that can record it.
        """
        if not self._session_id or not self._api_url or not self._host_token:
            logger.warning("end_session called but agent has no session context")
            return "no_session_context"

        url = f"{self._api_url}/sessions/{self._session_id}/end"
        headers = {"Authorization": f"Bearer {self._host_token}"}

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, headers=headers, json={"enjoyed": enjoyed})
            if resp.status_code == 200:
                logger.info("Session %s marked as ended", self._session_id)
                return "session_ended"
            detail = resp.json().get("detail", "unknown error")
            logger.error("end_session failed %s: %s", resp.status_code, detail)
            return f"error:{detail}"
        except Exception as exc:  # noqa: BLE001
            logger.exception("end_session exception: %s", exc)
            return "error:network"

    def start_heartbeat(self) -> None:
        """Start the 30-second metering heartbeat background task."""
        if self._heartbeat_task is None or self._heartbeat_task.done():
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
            logger.info("Heartbeat task started for session %s", self._session_id)

    def stop_heartbeat(self) -> None:
        """Cancel the metering heartbeat task."""
        if self._heartbeat_task and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()
            logger.info("Heartbeat task stopped for session %s", self._session_id)
        self._heartbeat_task = None

    async def _heartbeat_loop(self) -> None:
        """Send a heartbeat every `_heartbeat_interval` seconds until cancelled."""
        try:
            while True:
                await asyncio.sleep(self._heartbeat_interval)
                await self._send_heartbeat()
        except asyncio.CancelledError:
            pass

    async def _send_heartbeat(self) -> None:
        """POST elapsed seconds to the API heartbeat endpoint."""
        if not self._session_id or not self._api_url or not self._host_token:
            return
        url = f"{self._api_url}/sessions/{self._session_id}/heartbeat"
        headers = {"Authorization": f"Bearer {self._host_token}"}
        payload = {"seconds": self._heartbeat_interval}
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, json=payload, headers=headers)
            if resp.status_code != 200:
                logger.warning("Heartbeat returned %s for session %s", resp.status_code, self._session_id)
            else:
                logger.debug("Heartbeat sent for session %s", self._session_id)
                self._maybe_announce_ending(resp.json().get("secondsRemaining"))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Heartbeat failed for session %s: %s", self._session_id, exc)

    def _maybe_announce_ending(self, seconds_remaining: int | None) -> None:
        """Have the agent wind the conversation down before the session cap cuts it off.

        The cap closes the room server-side, mid-sentence, with no warning — correct as a
        spending guard, brutal as an experience. The API reports the time left on every
        heartbeat, so the agent can bring the conversation to a close on its own terms.

        Announced once, and phrased as instructions rather than a fixed sentence: the
        model picks the language each participant is speaking, which a hardcoded line
        could not do in a room where two people speak different ones.
        """
        if self._ending_announced or seconds_remaining is None:
            return
        if seconds_remaining > ENDING_WARNING_SECONDS:
            return

        self._ending_announced = True
        try:
            self.session.generate_reply(
                instructions=(
                    "The conversation must end in about a minute. Bring it to a natural "
                    "close: say briefly that little time is left, offer a short parting "
                    "thought on what was discussed, and thank the participants. Speak in "
                    "the language of the conversation. Do not mention timers, limits, "
                    "quotas or technical reasons."
                )
            )
            logger.info("Ending announced for session %s", self._session_id)
        except Exception as exc:  # noqa: BLE001
            # A failed announcement must not disturb a working conversation.
            logger.warning("Could not announce the ending: %s", exc)

    @function_tool
    async def invite_contact(
        self,
        email: Annotated[str, "Guest email address, e.g. ami@exemple.com"],
    ) -> str:
        """Invite a contact to the current session by email address.

        Returns a short status message describing the outcome.
        Call this when the host says 'invite [name]'.
        """
        if not self._session_id or not self._api_url or not self._host_token:
            logger.warning("invite_contact called but agent has no session context")
            return "no_session_context"

        url = f"{self._api_url}/sessions/{self._session_id}/invitations"
        headers = {"Authorization": f"Bearer {self._host_token}"}
        payload = {"guestEmail": email}

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, json=payload, headers=headers)
            if resp.status_code in (200, 201):
                data = resp.json()
                return data.get("invitationType", "invited")
            detail = resp.json().get("detail", "unknown error")
            logger.error("invite_contact failed %s: %s", resp.status_code, detail)
            return f"error:{detail}"
        except Exception as exc:  # noqa: BLE001
            logger.exception("invite_contact exception: %s", exc)
            return "error:network"


async def _fetch_session_detail(api_url: str, session_id: str, host_token: str) -> dict | None:
    """Fetch session content from the API so the agent can read it aloud."""
    url = f"{api_url}/sessions/{session_id}"
    headers = {"Authorization": f"Bearer {host_token}"}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers=headers)
        if resp.status_code == 200:
            return resp.json()
        logger.warning("_fetch_session_detail returned %s", resp.status_code)
    except Exception as exc:  # noqa: BLE001
        logger.exception("_fetch_session_detail failed: %s", exc)
    return None


async def entrypoint(ctx: agents.JobContext):
    await ctx.connect()

    # Parse session context injected by API when dispatching this job
    session_id: str | None = None
    api_url: str | None = None
    host_token: str | None = None

    raw_metadata = getattr(ctx.job, "metadata", None)
    if raw_metadata:
        try:
            meta = json.loads(raw_metadata)
            session_id = meta.get("session_id")
            api_url = meta.get("api_url")
            host_token = meta.get("host_token")
        except (json.JSONDecodeError, AttributeError):
            logger.warning("Could not parse job metadata: %r", raw_metadata)

    # Fetch session content so the agent can read it aloud and introduce contrast
    source_content: str | None = None
    source_summary: str | None = None
    source_type: str | None = None
    source_url: str | None = None
    additional_sources: list[dict] = []

    if session_id and api_url and host_token:
        detail = await _fetch_session_detail(api_url, session_id, host_token)
        if detail:
            source_content = detail.get("sourceContent")
            source_summary = detail.get("sourceSummary")
            source_type = detail.get("sourceType")
            source_url = detail.get("sourceUrl")
            additional_sources = detail.get("additionalSources") or []

    # The key is passed explicitly rather than left to the plugin's env lookup: the job
    # runs in a subprocess, and a missing key there surfaces only as an opaque 400 on the
    # realtime handshake. The fingerprint makes that visible in the log instead.
    xai_key = os.environ.get("XAI_API_KEY", "")
    logger.info(
        "xAI credentials: length=%d tail=%s",
        len(xai_key),
        xai_key[-4:] if xai_key else "ABSENT",
    )

    agent_session = AgentSession(
        # Per docs.x.ai speech-to-speech: `grok-voice-latest` is the current alias, and
        # the plugin still defaults to grok-voice-think-fast-1.0 ("previous generation").
        # Voice ids are lowercase — "Ara" is not a valid identifier.
        llm=xai.realtime.RealtimeModel(
            model="grok-voice-latest", voice="ara", api_key=xai_key or None
        ),
        vad=silero.VAD.load(),
        # The multilingual turn detector that used to sit here never actually ran: it
        # needs PyTorch, which is not installed, so every turn was decided by silence
        # alone — the logs showed `source: "vad"` and a null end-of-turn probability for
        # all of them. Semantic end-of-turn detection was configured but never obtained.
        #
        # inference.TurnDetector runs on LiveKit's service with the credentials the agent
        # already holds, so there is no local model and no PyTorch to install. It costs a
        # round trip per turn, which is the price of not cutting someone off mid-thought —
        # and it matters here, where participants may pause while switching language.
        #
        # turn_detection and allow_interruptions moved into turn_handling; passing them at
        # the top level still works but is deprecated.
        turn_handling={
            "turn_detection": inference.TurnDetector(),
            "interruption": {"enabled": True},   # participants can interrupt naturally
        },
    )

    salon_agent = SalonAgent(
        session_id=session_id,
        api_url=api_url,
        host_token=host_token,
        source_content=source_content,
        source_type=source_type,
        source_url=source_url,
        additional_sources=additional_sources,
        source_summary=source_summary,
        room=ctx.room,
    )

    # Sources added mid-conversation (FR3): the API publishes a data message, since the
    # session detail above is fetched once and would otherwise never be re-read.
    async def _reload_sources() -> None:
        detail = await _fetch_session_detail(api_url, session_id, host_token)
        if not detail:
            return
        await salon_agent.update_instructions(
            _build_instructions(
                source_content=detail.get("sourceContent"),
                source_type=detail.get("sourceType"),
                source_url=detail.get("sourceUrl"),
                additional_sources=detail.get("additionalSources") or [],
                source_summary=detail.get("sourceSummary"),
            )
        )
        logger.info(
            "Instructions rebuilt after source_added (%d additional sources)",
            len(detail.get("additionalSources") or []),
        )

    def _on_data(packet) -> None:
        if not (session_id and api_url and host_token):
            return
        try:
            msg = json.loads(bytes(packet.data).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return
        if isinstance(msg, dict) and msg.get("action") == "source_added":
            asyncio.create_task(_reload_sources())

    ctx.room.on("data_received", _on_data)

    # Closing the browser or killing the app ends no session by itself: the client simply
    # stops sending heartbeats, leaving the session active. The agent is the only party
    # always present server-side, so it closes the session when the room empties —
    # otherwise the host keeps an open session they believe they left (FR25).
    def _on_participant_disconnected(_participant) -> None:
        if len(ctx.room.remote_participants) == 0:
            logger.info("Last participant left; ending session %s", session_id)
            asyncio.create_task(salon_agent.end_session())

    ctx.room.on("participant_disconnected", _on_participant_disconnected)

    await agent_session.start(
        room=ctx.room,
        agent=salon_agent,
        # audio_input=False stops RoomIO from installing its own single-participant
        # input; ours replaces it below. Everything else about RoomIO — the shared audio
        # output, transcriptions, disconnect handling — is kept. (Formerly
        # RoomInputOptions(audio_enabled=False); the option classes were merged into
        # RoomOptions, where False on an input means the same thing.)
        room_options=RoomOptions(audio_input=False),
    )

    # RoomIO hears only the participant it linked to, so the agent was deaf to everyone
    # else in the room. This mixes every remote participant into one stream instead.
    mixed_input = MixedParticipantAudioInput(ctx.room)
    mixed_input.start()
    agent_session.input.audio = mixed_input

    # Mandatory, and easy to miss: room_input_options above turned audio input off, which
    # left AgentInput._audio_enabled False. The setter then calls on_detached() on our
    # mixer instead of on_attached(), so its frames are never consumed — the model
    # receives nothing and never speaks at all.
    agent_session.input.set_audio_enabled(True)

    async def _close_mixer() -> None:
        await mixed_input.aclose()

    ctx.add_shutdown_callback(_close_mixer)

    # ── Live captions ─────────────────────────────────────────────────────────
    # The realtime session already transcribes what it hears — input transcription is on
    # by default in the xAI plugin — and until now the agent received that text and threw
    # it away. Each finalised turn is now stored and published to the room, translated
    # into whatever language each participant says they are reading.
    if session_id and api_url and host_token:
        captions = CaptionPublisher(ctx.room, api_url, session_id, host_token)
        # Attribution comes from LiveKit, not from the model: every participant is mixed
        # into one audio stream, so the realtime model cannot say who spoke.
        captions.track_active_speakers()

        @agent_session.on("user_input_transcribed")
        def _on_user_transcript(event) -> None:
            # Finals only. The model revises a transcript as it hears more, and the
            # interim versions are half-sentences that were never true.
            if not event.is_final:
                return
            captions.publish_soon(
                text=event.transcript,
                # speaker_id is populated on the plugin's STT path and never on the
                # realtime one, so it is not worth reading here.
                identity=captions.attributed_speaker(),
                language=event.language,
            )

        @agent_session.on("conversation_item_added")
        def _on_agent_speech(event) -> None:
            # The same event carries both sides of the conversation; the user's half
            # already arrived above as a transcript, and posting it twice would double
            # every caption.
            item = getattr(event, "item", None)
            if item is None or getattr(item, "role", None) != "assistant":
                return
            captions.publish_soon(
                text=getattr(item, "text_content", None) or "",
                identity="agent",
            )

    # Start metering heartbeat — sends elapsed seconds every 30 s so trial time
    # is committed incrementally and survives unexpected disconnects.
    if session_id and api_url and host_token:
        salon_agent.start_heartbeat()

        @ctx.room.on("disconnected")
        def _on_room_disconnected(*_args):
            salon_agent.stop_heartbeat()


if __name__ == "__main__":
    # agent_name makes this worker dispatch-only: the API creates an explicit dispatch
    # carrying the session context (session id, API url, host token) in job metadata,
    # which participants cannot read. Without a name the worker would be dispatched
    # automatically and run context-free — unable to read sources or send invitations.
    agents.cli.run_app(
        agents.WorkerOptions(
            entrypoint_fnc=entrypoint,
            agent_name=AGENT_NAME,
        )
    )
