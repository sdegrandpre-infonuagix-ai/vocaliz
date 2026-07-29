"""
Salon – LiveKit Agent Worker
Entry point for the xAI-powered voice discussion agent.
"""

import json
import logging
from typing import Annotated

import httpx
from dotenv import load_dotenv
from livekit import agents
from livekit.agents import AgentSession, Agent, RoomInputOptions, function_tool
from livekit.plugins import xai, silero, turn_detector

load_dotenv()
logger = logging.getLogger("salon-agent")

_BASE_INSTRUCTIONS = (
    "You are Salon, a sophisticated voice discussion facilitator. "
    "Your role is to animate intellectually stimulating conversations "
    "between participants about documents, articles, or current events. "
    "Speak naturally without requiring a wake word. "
    "Intervene at most once per minute when participants share the same "
    "language, more frequently when actively translating. "
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
    "End sessions gracefully and ask a satisfaction question when a "
    "participant says they want to leave."
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

    agent_session = AgentSession(
        llm=xai.realtime.RealtimeModel(voice="Ara"),
        vad=silero.VAD.load(),
        turn_detector=turn_detector.EOUModel(),
    )

    await agent_session.start(
        room=ctx.room,
        agent=SalonAgent(
            session_id=session_id,
            api_url=api_url,
            host_token=host_token,
            source_content=source_content,
            source_type=source_type,
            source_url=source_url,
            additional_sources=additional_sources,
        ),
        room_input_options=RoomInputOptions(),
    )


if __name__ == "__main__":
    agents.cli.run_app(
        agents.WorkerOptions(entrypoint_fnc=entrypoint)
    )
