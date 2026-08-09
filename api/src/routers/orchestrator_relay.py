"""The API, standing between an agent and the orchestrator that holds its Salon.

**Why this exists.** The orchestrator answers inside the VPC and nowhere else, deliberately:
it holds the text of every live conversation. The agent worker runs on LiveKit Cloud, outside
that VPC, so the address the API reaches it at is unreachable from where the agent is.

Three ways out were weighed in Story 11.1. Exposing the orchestrator publicly is the only one
that creates a surface to defend, and what would go outside is the service holding every
conversation. Moving the agent worker into the VPC removes the problem instead of arbitrating
it, and is the right place to end up — but it means operating a component LiveKit runs today.
This is the third: the agent talks to `app.vocaliz.net`, which is already public and already
authenticated, and the API forwards.

**The price, stated plainly.** One extra network hop per turn of speech — precisely what
descending the interpreter into the agent was meant to avoid. It is paid here because it buys
back the whole of the authentication problem, and because nothing about it forecloses moving
the worker into the VPC later: the agent changes one base URL and this router is deleted.

**The paths mirror the orchestrator's exactly**, under one prefix. That is not tidiness — it
means the agent's client is the same code whichever address it is pointed at, so the day this
router goes away, nothing on the agent side has to be rewritten to prove it still works.

**Which orchestrator.** Never the configured one: the one written on this Salon's row when it
was created. A Salon is stateful — the journal, every reader's position — and any other
instance would answer with a second, emptier version of the same conversation.

**Who may call this.** Not a Vocaliz sign-in — a guest's agent has no account to sign in as,
and even the host's account proves an identity, not a Salon. Every route here is guarded by a
token from `relay_token`, scoped to exactly one participant's one Salon: it authorises
speaking as that participant in that Salon, and nothing else. The first version of this file
accepted any signed-in user's token for any Salon at all, which nothing had yet exploited only
because nothing yet minted a token that told two Salons apart.
"""
import logging
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session as DbSession

from src.database import get_db
from src.models.salon import Salon
from src.services import relay_token

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/orchestrator", tags=["orchestrator"])

_bearer = HTTPBearer()

# Short, for the same reason as everywhere else on this path: each of these sits between one
# person speaking and another hearing it, so a slow answer is worse than no answer.
TIMEOUT_SECONDS = 5.0


def _authorised(
    salon_id: str,
    participant_id: str,
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
) -> None:
    """Refuse unless this token was minted for exactly this participant in this Salon.

    A wrong participant id in an otherwise valid token is refused here rather than reported —
    it is the shape a bug takes, not an attack, and 403 says so without a stack trace.
    """
    scope = relay_token.scope_of(credentials.credentials)
    if scope is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token.")
    if scope != (salon_id, participant_id):
        raise HTTPException(
            status_code=403, detail="This token is not scoped to this participant."
        )


def _salon(db: DbSession, salon_id: str) -> Salon:
    try:
        key = UUID(salon_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="No such salon.") from None

    salon = db.query(Salon).filter(Salon.id == key).first()
    if salon is None:
        raise HTTPException(status_code=404, detail="No such salon.")
    if not salon.orchestrator_url:
        # 503 rather than 404: the Salon exists and is perfectly usable, it simply has no
        # orchestrator holding its text — which is what happens when none was reachable at
        # creation. The conversation runs without translation, and saying so is honest.
        raise HTTPException(
            status_code=503, detail="No orchestrator is holding this salon."
        )
    return salon


async def _forward(
    salon: Salon, method: str, suffix: str, body: dict | None = None
) -> dict:
    """One call to the orchestrator that holds this Salon, and its answer, unchanged.

    The status is passed through rather than flattened. A 404 from the orchestrator means it
    is no longer holding this Salon — a real answer the agent can act on by stopping — and
    turning that into a 502 would tell it the network broke instead.
    """
    url = f"{salon.orchestrator_url.rstrip('/')}/salons/{salon.id}{suffix}"
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
            response = await client.request(method, url, json=body)
    except Exception as exc:  # noqa: BLE001
        # The class as well as the message: a connect timeout stringifies to nothing at all,
        # and whether it was DNS, a closed port or a slow answer is the entire question.
        logger.warning(
            "orchestrator unreachable for salon %s: %s(%s)",
            salon.id,
            type(exc).__name__,
            exc,
        )
        raise HTTPException(
            status_code=503, detail="The orchestrator did not answer."
        ) from exc

    if response.status_code >= 400:
        raise HTTPException(
            status_code=response.status_code,
            detail="The orchestrator refused this request.",
        )
    return response.json()


@router.post("/salons/{salon_id}/participants", status_code=201)
async def join(
    salon_id: str,
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
    db: DbSession = Depends(get_db),
):
    """A human takes a seat. Their interpreter stays in their agent, beside their audio.

    The one route here where the participant's identity is not in the path — it is in the
    body, because this is the call that announces it. Authorised against the body rather
    than a path segment, which is why this cannot share `_authorised`'s signature with the
    other three.
    """
    body = await request.json()
    participant_id = body.get("participantId", "")
    scope = relay_token.scope_of(credentials.credentials)
    if scope is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token.")
    if scope != (salon_id, participant_id):
        raise HTTPException(
            status_code=403, detail="This token is not scoped to this participant."
        )
    return await _forward(_salon(db, salon_id), "POST", "/participants", body)


@router.get("/salons/{salon_id}/participants/{participant_id}/script")
async def script(
    salon_id: str,
    participant_id: str,
    db: DbSession = Depends(get_db),
    _: None = Depends(_authorised),
):
    """What this participant is owed, in their language, in order.

    The reading position moves at the orchestrator when this answers, so a line that reaches
    the agent is a line the agent is responsible for saying.
    """
    return await _forward(
        _salon(db, salon_id), "GET", f"/participants/{participant_id}/script"
    )


@router.post("/salons/{salon_id}/participants/{participant_id}/utterances")
async def report(
    salon_id: str,
    participant_id: str,
    request: Request,
    db: DbSession = Depends(get_db),
    _: None = Depends(_authorised),
):
    """What this participant's human just said, for the journal."""
    return await _forward(
        _salon(db, salon_id),
        "POST",
        f"/participants/{participant_id}/utterances",
        await request.json(),
    )


@router.delete("/salons/{salon_id}/participants/{participant_id}")
async def leave(
    salon_id: str,
    participant_id: str,
    db: DbSession = Depends(get_db),
    _: None = Depends(_authorised),
):
    """Somebody left. Their room closes and nothing else does — what they said stays in the
    journal, because leaving is not a reason for everybody else to lose half the
    conversation."""
    return await _forward(
        _salon(db, salon_id), "DELETE", f"/participants/{participant_id}"
    )
