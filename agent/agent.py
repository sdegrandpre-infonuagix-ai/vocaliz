"""
Salon – LiveKit Agent Worker
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
from livekit.agents import AgentSession, Agent, RoomInputOptions, function_tool
from livekit.plugins import xai, silero
from livekit.plugins.turn_detector.multilingual import MultilingualModel

# override=True is deliberate: load_dotenv() otherwise leaves pre-existing OS
# environment variables untouched, so a stale machine-wide XAI_API_KEY silently wins
# over agent/.env and the realtime handshake fails with an opaque 400.
load_dotenv(override=True)
logger = logging.getLogger("salon-agent")

# Must match SALON_AGENT_NAME in api/src/services/livekit_service.py — the API dispatches
# by this exact name, and a mismatch means the agent is simply never dispatched.
AGENT_NAME = "salon-agent"

_BASE_INSTRUCTIONS = (
    "You are Salon, a sophisticated voice discussion facilitator. "
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
    "INVITATION COMMANDS: When the host says 'invite [name or phone number]' or "
    "'invite [name] at [phone number]', call invite_contact with the phone number "
    "in E.164 format (e.g. +15141234567). "
    "If the host gives only a name with no phone number, politely ask: "
    "'Quel est le numéro de téléphone de [name] ?' before calling the tool. "
    "If the invitation succeeds for a Salon user, say: "
    "'J\\'ai envoyé une notification à [name] pour rejoindre le salon.' "
    "If via SMS, say: 'J\\'ai envoyé un lien SMS à [phone] pour rejoindre le salon.' "
    "If the call fails, say: 'Je n\\'ai pas pu inviter ce contact. Pouvez-vous vérifier "
    "le numéro de téléphone ?' "
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
    "   FR: 'Est-ce que votre conversation dans Salon a été une belle expérience ?'\n"
    "   EN: 'Was your conversation in Salon a wonderful experience?'\n"
    "   ES: '¿Fue tu conversación en Salon una bella experiencia?'\n"
    "   (use the participant's detected language; default to French if unknown)\n"
    "3. After they reply (or after a natural pause of ~3 seconds if no reply),\n"
    "   thank them briefly and call end_session to close the session.\n"
    "IMPORTANT: You MUST ask the satisfaction question before calling end_session.\n"
    "Do NOT skip directly to end_session — the question is mandatory.\n"
    "\n\n"
    "ANONYMOUS GUESTS (display name 'Invité'):\n"
    "Anonymous browser guests have no Salon account. Apply these rules for them:\n"
    "- Ask the satisfaction question exactly as you would for a registered user.\n"
    "  Their verbal response is valuable even without a profile.\n"
    "- Do NOT call report_detected_language for anonymous guests — they have no\n"
    "  profile to update. Language detection tools are for the host only.\n"
    "- Satisfaction responses from anonymous guests are purely conversational:\n"
    "  they are NOT saved to any database. Thank them warmly regardless.\n"
    "- An anonymous guest joining via browser will appear with identity 'Invité'.\n"
    "  Treat them as a full participant for facilitation and exit purposes.\n"
)

_CONTENT_PREVIEW_CHARS = 2500
_EXTRA_SOURCE_PREVIEW_CHARS = 1000


def _build_instructions(
    source_content: str | None = None,
    source_type: str | None = None,
    source_url: str | None = None,
    additional_sources: list[dict] | None = None,
) -> str:
    """Build agent instructions, injecting session content for facilitation and contrast."""
    instructions = _BASE_INSTRUCTIONS
    additional_sources = additional_sources or []

    if source_content:
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
            content = src.get("sourceContent") or ""
            label = src.get("sourceUrl") or f"document {i}"
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
        room=None,
    ) -> None:
        instructions = _build_instructions(
            source_content=source_content,
            source_type=source_type,
            source_url=source_url,
            additional_sources=additional_sources,
        )
        super().__init__(instructions=instructions)
        self._session_id = session_id
        self._api_url = api_url
        self._host_token = host_token
        self._frequency_preference: str = "normal"
        self._room = room
        self._heartbeat_task: asyncio.Task | None = None
        self._heartbeat_interval: int = 30

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
    async def end_session(self) -> str:
        """Mark the current session as ended in the API.

        Call this as the final step of the session exit flow — AFTER acknowledging
        the participant's departure and asking the satisfaction question.
        This closes the session and signals all clients to disconnect.
        """
        if not self._session_id or not self._api_url or not self._host_token:
            logger.warning("end_session called but agent has no session context")
            return "no_session_context"

        url = f"{self._api_url}/sessions/{self._session_id}/end"
        headers = {"Authorization": f"Bearer {self._host_token}"}

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, headers=headers)
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
        except Exception as exc:  # noqa: BLE001
            logger.warning("Heartbeat failed for session %s: %s", self._session_id, exc)

    @function_tool
    async def invite_contact(
        self,
        phone_number: Annotated[str, "Guest phone number in E.164 format, e.g. +15141234567"],
    ) -> str:
        """Invite a contact to the current session by phone number.

        Returns a short status message describing the outcome.
        Call this when the host says 'invite [name/phone]'.
        """
        if not self._session_id or not self._api_url or not self._host_token:
            logger.warning("invite_contact called but agent has no session context")
            return "no_session_context"

        url = f"{self._api_url}/sessions/{self._session_id}/invitations"
        headers = {"Authorization": f"Bearer {self._host_token}"}
        payload = {"guestPhoneNumber": phone_number}

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
    source_type: str | None = None
    source_url: str | None = None
    additional_sources: list[dict] = []

    if session_id and api_url and host_token:
        detail = await _fetch_session_detail(api_url, session_id, host_token)
        if detail:
            source_content = detail.get("sourceContent")
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
        # AgentSession takes `turn_detection`, not `turn_detector`, and EOUModel was
        # removed from the plugin — MultilingualModel is its replacement, and the right
        # one here since participants may speak different languages (FR12–FR17).
        turn_detection=MultilingualModel(),
        allow_interruptions=True,   # participants can interrupt the agent naturally
    )

    salon_agent = SalonAgent(
        session_id=session_id,
        api_url=api_url,
        host_token=host_token,
        source_content=source_content,
        source_type=source_type,
        source_url=source_url,
        additional_sources=additional_sources,
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

    await agent_session.start(
        room=ctx.room,
        agent=salon_agent,
        room_input_options=RoomInputOptions(),
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
