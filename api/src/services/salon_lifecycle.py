"""Closing a salon: metering, billing, follow-up, and room teardown.

Extracted so POST /salons/{id}/end and the cleanup that runs before a host opens a new
salon behave identically. Two copies of this would drift, and the metering clamp is
exactly the kind of detail that gets fixed in one and forgotten in the other.
"""
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session as DbSession

from src.config import settings
from src.models.invitation import Invitation
from src.models.salon import Salon
from src.models.user import User
from src.services import (
    invitation_service,
    livekit_service,
    salon_code_service,
    salon_event_service,
    stripe_service,
)

logger = logging.getLogger(__name__)


def accrue_remaining_host_time(salon: Salon, db: DbSession) -> int:
    """Add the span since the last heartbeat to the host's metered time.

    Clamped to metering_grace_seconds: an unbounded gap means nobody was there to send
    heartbeats, so billing it would charge the host for a salon already abandoned.
    Returns the number of seconds actually added.
    """
    reference = salon.last_heartbeat_at or salon.created_at
    ref = reference if reference.tzinfo else reference.replace(tzinfo=timezone.utc)
    ended = salon.ended_at if salon.ended_at.tzinfo else salon.ended_at.replace(
        tzinfo=timezone.utc
    )

    elapsed = max(0, int((ended - ref).total_seconds()))
    seconds = min(elapsed, settings.metering_grace_seconds)

    host = db.query(User).filter(User.id == salon.host_user_id).first()
    if seconds > 0 and host is not None:
        host.trial_seconds_used = host.trial_seconds_used + seconds
        db.commit()
    return seconds


def finalize_salon(
    salon: Salon, db: DbSession, *, enjoyed: bool | None = None
) -> dict | None:
    """Mark a salon ended, meter it, bill it, and notify its guests.

    Returns the billing summary when a charge was made. Billing and notification errors
    are swallowed: neither may block a salon from closing, and an unbilled span is
    retried on the host's next salon.

    `enjoyed` carries the closing satisfaction answer when the agent obtained one. It is
    recorded against every participation in the salon, since the question is asked of the
    room rather than of one person.
    """
    salon.status = "ended"
    salon.ended_at = datetime.now(tz=timezone.utc)
    db.commit()
    db.refresh(salon)

    accrue_remaining_host_time(salon, db)

    billing_summary = None
    host = db.query(User).filter(User.id == salon.host_user_id).first()
    if host is not None:
        try:
            billing_summary = stripe_service.bill_host_for_usage(host, salon, db)
        except Exception:  # noqa: BLE001 — never let billing break salon teardown
            billing_summary = None

    # Closing the participations here rather than per-participant: nobody tells the API
    # when a guest shuts their tab, so the end of the salon is the only moment their
    # departure is reliably known.
    salon_event_service.record_salon_exit(db, salon.livekit_room_name, enjoyed=enjoyed)

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
        .filter(Invitation.salon_id == salon.id, Invitation.status == "pending")
        .update({Invitation.status: "expired"}, synchronize_session=False)
    )
    if expired:
        db.commit()
        logger.info("Expired %d unused invitation(s) for salon %s", expired, salon.id)

    # Back to the pool. Without this a code stays pointed at a conversation that is
    # over, and someone dialling an old code would be placed in an empty room.
    released = salon_code_service.release_for_salon(db, salon.id)
    if released:
        logger.info("Released %d telephone code(s) for salon %s", released, salon.id)

    invitation_service.send_followup_email_to_guests(str(salon.id), db)
    return billing_summary


async def close_previous_host_salons(host: User, db: DbSession) -> int:
    """End every salon this host still has open, and delete their LiveKit rooms.

    A host opening a new salon must never leave an older one running: its agent stays
    alive and keeps talking, so joining the new room can surface the *previous* agent —
    which is exactly what happened in testing. Deleting the room is what actually stops
    that agent; marking the row ended only settles the accounting.

    Returns the number of salons closed.
    """
    stale = (
        db.query(Salon)
        .filter(
            Salon.host_user_id == host.id,
            Salon.status == "active",
        )
        .all()
    )

    for salon in stale:
        room_name = salon.livekit_room_name
        finalize_salon(salon, db)
        # After finalizing: the accounting is settled even if room deletion fails.
        await livekit_service.delete_room(room_name)
        logger.info("Closed stale salon %s (room %s)", salon.id, room_name)

    return len(stale)


async def close_expired_salons(db: DbSession) -> list[str]:
    """End every salon that has outlived the per-salon cap, whatever its heartbeats say.

    The cap was previously enforced only when a heartbeat arrived, which meant it was not
    enforced at all in the most ordinary failure: a host closes their laptop, or the agent
    worker dies. No heartbeat, no evaluation, and the salon stays active for good. That
    leaked three things at once — an open salon in the data, a telephone code reserved for
    a conversation that was over, and a span of metered time never settled.

    Driven by created_at rather than last_heartbeat_at, deliberately. A salon's ceiling is
    its age, not its silence: one that has been running eleven minutes is over whether or
    not somebody was still talking a second ago.

    Returns the ids closed, so the caller can log what it did rather than only how much.
    """
    now = datetime.now(tz=timezone.utc)
    cutoff = now - timedelta(seconds=settings.max_salon_seconds)

    expired = (
        db.query(Salon)
        .filter(Salon.status == "active", Salon.created_at < cutoff)
        .all()
    )

    # A call nobody answered has a shorter fuse than a conversation.
    #
    # Ringing the front desk opens a Salon and mails the desk an invitation. If nobody clicks
    # it, the caller sits alone with an agent for the full ten minutes — realtime-model time
    # billed for a call that was never picked up. Five minutes is long enough for somebody to
    # notice an email and short enough that an unanswered call is not the most expensive kind.
    #
    # "Answered" is the invitation no longer being pending, which is what clicking the link
    # does. Deliberately not "somebody is in the room": the caller is in the room, and a check
    # on occupancy would find the Salon busy precisely when it is most abandoned.
    unanswered_cutoff = now - timedelta(seconds=settings.unanswered_call_seconds)
    unanswered = (
        db.query(Salon)
        .join(Invitation, Invitation.salon_id == Salon.id)
        .filter(
            Salon.status == "active",
            Salon.created_at < unanswered_cutoff,
            Invitation.guest_email == settings.front_desk_email,
            Invitation.status == "pending",
        )
        .all()
    )
    # Merged on id rather than concatenated: a Salon old enough to be in both lists would
    # otherwise be finalised twice, and the second pass would bill a salon already closed.
    seen = {salon.id for salon in expired}
    expired.extend(salon for salon in unanswered if salon.id not in seen)

    closed: list[str] = []
    for salon in expired:
        room_name = salon.livekit_room_name
        try:
            finalize_salon(salon, db)
            # After finalizing, as everywhere else: the accounting is settled even if
            # deleting the room fails, and a room LiveKit already collected is not an error.
            await livekit_service.delete_room(room_name)
            closed.append(str(salon.id))
            logger.info("Closed expired salon %s (room %s)", salon.id, room_name)
        except Exception:  # noqa: BLE001
            # One salon that refuses to close must not stop the sweep from reaching the
            # rest. A sweep that aborts halfway is worse than no sweep, because the
            # remainder is silently skipped every run.
            db.rollback()
            logger.warning("Could not close expired salon %s", salon.id, exc_info=True)

    return closed
