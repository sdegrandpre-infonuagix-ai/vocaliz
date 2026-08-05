"""Closing a session: metering, billing, follow-up, and room teardown.

Extracted so POST /sessions/{id}/end and the cleanup that runs before a host opens a new
session behave identically. Two copies of this would drift, and the metering clamp is
exactly the kind of detail that gets fixed in one and forgotten in the other.
"""
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session as DbSession

from src.config import settings
from src.models.invitation import Invitation
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

    # Closed before the codes go back, and that order is the whole point.
    #
    # A pending invitation holds its code under a partial unique index — one pending row per
    # code. Releasing the code without closing the invitation put a free code in the pool that
    # a pending row still owned, so the next host to invite anybody was handed it and their
    # INSERT violated the index. Worse than a one-off: the pool hands out its oldest free code
    # first, so the same poisoned value came back every time and *every* invitation in the
    # system failed with a 500 from then on.
    expired = (
        db.query(Invitation)
        .filter(Invitation.session_id == session.id, Invitation.status == "pending")
        .update({Invitation.status: "expired"}, synchronize_session=False)
    )
    if expired:
        db.commit()
        logger.info("Expired %d unused invitation(s) for salon %s", expired, session.id)

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


async def close_expired_sessions(db: DbSession) -> list[str]:
    """End every session that has outlived the per-session cap, whatever its heartbeats say.

    The cap was previously enforced only when a heartbeat arrived, which meant it was not
    enforced at all in the most ordinary failure: a host closes their laptop, or the agent
    worker dies. No heartbeat, no evaluation, and the session stays active for good. That
    leaked three things at once — an open session in the data, a telephone code reserved for
    a conversation that was over, and a span of metered time never settled.

    Driven by created_at rather than last_heartbeat_at, deliberately. A session's ceiling is
    its age, not its silence: one that has been running eleven minutes is over whether or
    not somebody was still talking a second ago.

    Returns the ids closed, so the caller can log what it did rather than only how much.
    """
    cutoff = datetime.now(tz=timezone.utc) - timedelta(seconds=settings.max_session_seconds)

    expired = (
        db.query(SessionModel)
        .filter(SessionModel.status == "active", SessionModel.created_at < cutoff)
        .all()
    )

    closed: list[str] = []
    for session in expired:
        room_name = session.livekit_room_name
        try:
            finalize_session(session, db)
            # After finalizing, as everywhere else: the accounting is settled even if
            # deleting the room fails, and a room LiveKit already collected is not an error.
            await livekit_service.delete_room(room_name)
            closed.append(str(session.id))
            logger.info("Closed expired session %s (room %s)", session.id, room_name)
        except Exception:  # noqa: BLE001
            # One session that refuses to close must not stop the sweep from reaching the
            # rest. A sweep that aborts halfway is worse than no sweep, because the
            # remainder is silently skipped every run.
            db.rollback()
            logger.warning("Could not close expired session %s", session.id, exc_info=True)

    return closed
