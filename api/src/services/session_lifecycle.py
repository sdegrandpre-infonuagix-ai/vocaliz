"""Closing a session: metering, billing, follow-up, and room teardown.

Extracted so POST /sessions/{id}/end and the cleanup that runs before a host opens a new
session behave identically. Two copies of this would drift, and the metering clamp is
exactly the kind of detail that gets fixed in one and forgotten in the other.
"""
import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session as DbSession

from src.config import settings
from src.models.session import SessionModel
from src.models.user import User
from src.services import (
    invitation_service,
    livekit_service,
    salon_code_service,
    salon_event_service,
    stripe_service,
)

logger = logging.getLogger(__name__)


def accrue_remaining_host_time(session: SessionModel, db: DbSession) -> int:
    """Add the span since the last heartbeat to the host's metered time.

    Clamped to metering_grace_seconds: an unbounded gap means nobody was there to send
    heartbeats, so billing it would charge the host for a session already abandoned.
    Returns the number of seconds actually added.
    """
    reference = session.last_heartbeat_at or session.created_at
    ref = reference if reference.tzinfo else reference.replace(tzinfo=timezone.utc)
    ended = session.ended_at if session.ended_at.tzinfo else session.ended_at.replace(
        tzinfo=timezone.utc
    )

    elapsed = max(0, int((ended - ref).total_seconds()))
    seconds = min(elapsed, settings.metering_grace_seconds)

    host = db.query(User).filter(User.id == session.host_user_id).first()
    if seconds > 0 and host is not None:
        host.trial_seconds_used = host.trial_seconds_used + seconds
        db.commit()
    return seconds


def finalize_session(
    session: SessionModel, db: DbSession, *, enjoyed: bool | None = None
) -> dict | None:
    """Mark a session ended, meter it, bill it, and notify its guests.

    Returns the billing summary when a charge was made. Billing and notification errors
    are swallowed: neither may block a session from closing, and an unbilled span is
    retried on the host's next session.

    `enjoyed` carries the closing satisfaction answer when the agent obtained one. It is
    recorded against every participation in the salon, since the question is asked of the
    room rather than of one person.
    """
    session.status = "ended"
    session.ended_at = datetime.now(tz=timezone.utc)
    db.commit()
    db.refresh(session)

    accrue_remaining_host_time(session, db)

    billing_summary = None
    host = db.query(User).filter(User.id == session.host_user_id).first()
    if host is not None:
        try:
            billing_summary = stripe_service.bill_host_for_usage(host, session, db)
        except Exception:  # noqa: BLE001 — never let billing break session teardown
            billing_summary = None

    # Closing the participations here rather than per-participant: nobody tells the API
    # when a guest shuts their tab, so the end of the session is the only moment their
    # departure is reliably known.
    salon_event_service.record_salon_exit(db, session.livekit_room_name, enjoyed=enjoyed)

    # Back to the pool. Without this a code stays pointed at a conversation that is
    # over, and someone dialling an old code would be placed in an empty room.
    released = salon_code_service.release_for_session(db, session.id)
    if released:
        logger.info("Released %d telephone code(s) for salon %s", released, session.id)

    invitation_service.send_followup_email_to_guests(str(session.id), db)
    return billing_summary


async def close_previous_host_sessions(host: User, db: DbSession) -> int:
    """End every session this host still has open, and delete their LiveKit rooms.

    A host opening a new session must never leave an older one running: its agent stays
    alive and keeps talking, so joining the new room can surface the *previous* agent —
    which is exactly what happened in testing. Deleting the room is what actually stops
    that agent; marking the row ended only settles the accounting.

    Returns the number of sessions closed.
    """
    stale = (
        db.query(SessionModel)
        .filter(
            SessionModel.host_user_id == host.id,
            SessionModel.status == "active",
        )
        .all()
    )

    for session in stale:
        room_name = session.livekit_room_name
        finalize_session(session, db)
        # After finalizing: the accounting is settled even if room deletion fails.
        await livekit_service.delete_room(room_name)
        logger.info("Closed stale session %s (room %s)", session.id, room_name)

    return len(stale)
