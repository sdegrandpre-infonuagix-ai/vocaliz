"""The orchestrator's HTTP surface: text in, text out, and never a byte of audio.

The other half of the boundary. `script.py` made the conductor able to write down what it
would have said; this is what hands that writing to the agent holding the microphone.

The shape follows from the topology rather than from taste. A Salon is created by the API in
the same breath as the host's LiveKit room, so hosting one here is a `PUT` — the API says
which Salon this instance is responsible for, and says it again without consequence if the
request is retried. The host may then add two more humans, each arriving with their own
interpreter in their own room, which is what `POST /participants` records.

Two calls carry the conversation itself, and there are only two because of where the reading
position moves:

    GET  …/script       what this participant is owed, in their language
    POST …/utterances   what their human just said

There is no third call confirming what was spoken. The cursor advances when the script is
handed over, because in this topology a room holds one human and their agent — an agent that
dies takes the room with it, and there is nobody left to have missed anything. Delivering
twice, which the alternative risks, is the failure a listener can actually notice.

Nothing here accepts or returns audio, and a test in `test_no_audio.py` fails the build if
anything under `src/` so much as imports a library that could decode it.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from src.interprete import Participant
from src.lifecycle import DrainingError
from src.salon import HistoryAccess, Salon
from src.tiers import Tier

logger = logging.getLogger("orchestrator")


# ── What the API and the agent send ───────────────────────────────────────────


class HostRequest(BaseModel):
    """Which Salon this instance takes responsibility for.

    `livekitRoomName` is the host's own room, created by the API a moment earlier. Recorded
    rather than used: room names are derived from the Salon and the participant, so nothing
    here needs it to work — it is what makes a log line about this Salon joinable to a log
    line about that room when something goes wrong at three in the morning.
    """

    livekit_room_name: str = Field(default="", alias="livekitRoomName")
    host_id: str = Field(default="", alias="hostId")

    model_config = {"populate_by_name": True}


class JoinRequest(BaseModel):
    """A human arriving, and the language they will be spoken to in.

    No interpreter is named and none can be: theirs lives in their own agent, beside their
    audio. What this Salon needs is the one thing the agent cannot decide for it — where in
    the journal this person starts reading.
    """

    participant_id: str = Field(alias="participantId")
    language: str
    name: str | None = None
    by_telephone: bool = Field(default=False, alias="byTelephone")
    tier: str = Tier.BASE.value
    history: str = HistoryAccess.UNSPECIFIED.value
    covered: bool = False

    model_config = {"populate_by_name": True}


class UtteranceRequest(BaseModel):
    """What one human just said, as their own interpreter transcribed it.

    `durationSeconds` is how long they took to say it, which the journal uses to decide when
    a listener has fallen far enough behind to be given the substance instead of the whole.
    Left out, it is estimated from the text — worse, but never absent.
    """

    text: str
    language: str
    duration_seconds: float | None = Field(default=None, alias="durationSeconds")

    model_config = {"populate_by_name": True}


# ── The routes ────────────────────────────────────────────────────────────────


def _registry(request: Request):
    return request.app.state.registry


def _salon(request: Request, salon_id: str) -> Salon:
    salon = _registry(request).get(salon_id)
    if salon is None:
        # 404 rather than 409. From the caller's side "not hosted here" and "hosted but not
        # built" are the same fact — there is nothing to serve — and telling them apart
        # would leak which instance holds what without giving anybody a different action.
        raise HTTPException(status_code=404, detail=f"salon {salon_id} is not here")
    return salon


def build_router() -> APIRouter:
    router = APIRouter(prefix="/salons", tags=["salons"])

    @router.put("/{salon_id}")
    async def host(salon_id: str, body: HostRequest, request: Request) -> dict:
        """Take responsibility for a Salon. Idempotent, and that matters more than it looks.

        The API calls this while creating the host's room, so a retried request is ordinary
        rather than exceptional. Accepting twice keeps the conversation that is already
        running — building a second one over it would silently drop everything said so far.
        """
        registry = _registry(request)
        try:
            registry.accept(salon_id, request.app.state.build_salon(salon_id))
        except DrainingError:
            # 503, so the API tries another instance. This one is on its way out and taking
            # a new Salon would mean dropping it minutes later.
            raise HTTPException(
                status_code=503, detail="this instance is draining"
            ) from None

        logger.info(
            "hosting salon=%s room=%s host=%s",
            salon_id,
            body.livekit_room_name,
            body.host_id,
        )
        return {"salonId": salon_id, "hosted": True}

    @router.post("/{salon_id}/participants", status_code=201)
    async def join(salon_id: str, body: JoinRequest, request: Request) -> dict:
        """A human takes a seat. Their interpreter stays where it is, in their agent."""
        salon = _salon(request, salon_id)

        participant = Participant(
            id=body.participant_id,
            language=body.language,
            name=body.name,
            by_telephone=body.by_telephone,
        )
        room = await salon.join(
            participant,
            history=HistoryAccess(body.history),
            tier=Tier(body.tier),
            covered=body.covered,
        )
        return {
            "salonId": salon_id,
            "participantId": participant.id,
            "roomName": room.name,
        }

    @router.get("/{salon_id}/participants/{participant_id}/script")
    async def script(salon_id: str, participant_id: str, request: Request) -> dict:
        """What this participant is owed, in their language, in order.

        The reading position moves here. See the module docstring for why that is the right
        place and not one call later.
        """
        salon = _salon(request, salon_id)
        written = await salon.script_for(participant_id)
        return {
            "salonId": salon_id,
            "participantId": participant_id,
            "lines": written.as_json(),
        }

    @router.post("/{salon_id}/participants/{participant_id}/utterances")
    async def report(
        salon_id: str, participant_id: str, body: UtteranceRequest, request: Request
    ) -> dict:
        """What this participant's human just said, for the journal.

        `recorded` is how many messages it became: a long intervention is cut into several
        so that a listener is not made to wait for the end of it, and nothing is recorded at
        all from somebody whose microphone the host has cut or whose room has saturated.
        """
        salon = _salon(request, salon_id)
        entries = await salon.ingest(
            participant_id,
            body.text,
            language=body.language,
            duration_seconds=body.duration_seconds,
        )
        return {
            "salonId": salon_id,
            "participantId": participant_id,
            "recorded": len(entries),
            "sequences": [entry.sequence for entry in entries],
        }

    @router.delete("/{salon_id}/participants/{participant_id}")
    async def leave(salon_id: str, participant_id: str, request: Request) -> dict:
        """Somebody left. Their room closes and nothing else does.

        Silent about somebody who was never here: a connection that dies is often reported
        twice, and neither report may fail. What they said stays in the journal — leaving is
        not a reason for everybody else to lose half the conversation.
        """
        salon = _salon(request, salon_id)
        await salon.leave(participant_id)
        return {"salonId": salon_id, "participantId": participant_id, "left": True}

    @router.delete("/{salon_id}")
    async def end(salon_id: str, request: Request) -> dict:
        """The Salon is over. Every room closes; the journal stays where it is (NFR8)."""
        salon = _registry(request).get(salon_id)
        if salon is not None:
            await salon.aclose()
        _registry(request).release(salon_id)
        return {"salonId": salon_id, "ended": True}

    return router
