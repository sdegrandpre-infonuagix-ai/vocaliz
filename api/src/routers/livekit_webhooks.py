"""LiveKit's own webhooks — the one channel that says an agent left a room nobody told it to.

Configured in the LiveKit Cloud project dashboard, not here: webhooks are a project-level
setting with no API to point remotely, so this endpoint existing is only half the wiring.
The dashboard's webhook URL must be set to this deployment's `/webhooks/livekit`.

Answers every request it can parse and verify with 200, whether or not it acted — a webhook
provider that gets anything else retries the same event or disables the endpoint, and neither
is the right response to an event this chose not to act on.
"""
import logging
import time

import livekit.api as lk_api
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session as DbSession

from src.config import settings
from src.database import get_db
from src.services import agent_redispatch

logger = logging.getLogger(__name__)
router = APIRouter(tags=["webhooks"])

# Matches livekit_service._AGENT_KIND — LiveKit's ParticipantInfo.Kind.AGENT. Duplicated
# rather than imported: that constant is private to a module about provisioning rooms, and
# reaching into it from here would tie two unrelated reasons to change together.
_AGENT_KIND = 4

# A room whose agent keeps failing to speak and leaving would otherwise be redispatched into
# as fast as each attempt fails — the worst possible response to a realtime provider that is
# genuinely down, since every fresh agent pays the same failing connection forward. Best
# effort only: this is one warm container's memory, not a database row, so a cold start
# forgets it. That is an acceptable gap for a guard whose job is to slow down a storm within
# a container that is already spinning, not to bound one across the deployment's whole life.
_MIN_SECONDS_BETWEEN_REDISPATCHES = 30.0
_last_redispatch_at: dict[str, float] = {}

_receiver = lk_api.WebhookReceiver(
    lk_api.TokenVerifier(settings.livekit_api_key, settings.livekit_api_secret)
)


@router.post("/webhooks/livekit", include_in_schema=False)
async def livekit_webhook(request: Request, db: DbSession = Depends(get_db)):
    body = await request.body()
    try:
        event = _receiver.receive(
            body.decode("utf-8"), request.headers.get("Authorization", "")
        )
    except Exception:  # noqa: BLE001
        # Rejected rather than raised: an unverifiable request answers 200 too, so a webhook
        # provider that retries on anything else does not retry this — it was never going to
        # verify the second time either.
        logger.warning("Rejected an unverifiable LiveKit webhook", exc_info=True)
        return {"status": "rejected"}

    if event.event == "participant_left" and event.participant.kind == _AGENT_KIND:
        room_name = event.room.name
        last = _last_redispatch_at.get(room_name, 0.0)
        now = time.monotonic()
        if now - last < _MIN_SECONDS_BETWEEN_REDISPATCHES:
            logger.warning(
                "Skipping redispatch for room %s: one landed %.1fs ago",
                room_name,
                now - last,
            )
        else:
            _last_redispatch_at[room_name] = now
            try:
                await agent_redispatch.redispatch_for_room(db, room_name)
            except Exception:  # noqa: BLE001
                logger.error("Redispatch failed for room %s", room_name, exc_info=True)

    return {"status": "ok"}
