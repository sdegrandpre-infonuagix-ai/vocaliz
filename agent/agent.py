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

_INSTRUCTIONS = (
    "You are Salon, a sophisticated voice discussion facilitator. "
    "Your role is to animate intellectually stimulating conversations "
    "between participants about documents, articles, or current events. "
    "Speak naturally without requiring a wake word. "
    "Read source content aloud, ask engaging questions, introduce "
    "contrasting perspectives from other sources, and translate between "
    "languages when participants speak different languages. "
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


class SalonAgent(Agent):
    """Voice discussion agent powered by xAI Grok."""

    def __init__(
        self,
        session_id: str | None = None,
        api_url: str | None = None,
        host_token: str | None = None,
    ) -> None:
        super().__init__(instructions=_INSTRUCTIONS)
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
        ),
        room_input_options=RoomInputOptions(),
    )


if __name__ == "__main__":
    agents.cli.run_app(
        agents.WorkerOptions(entrypoint_fnc=entrypoint)
    )
