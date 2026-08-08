"""Claiming and releasing the six-digit codes guests dial to join a salon.

The pool answers one question — is a code free? Which salon a code reaches is read from the
invitation that carries it, so there is only ever one copy of that mapping.

The pool is filled lazily. Pre-generating a million rows to hand out a handful would be
storage spent on nothing; a claim takes a free row when one exists and inserts a fresh code
when none does. The table therefore holds only codes actually issued, and is bounded by
concurrent use rather than by total use.
"""
import logging
import secrets
from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

from src.models.invitation import Invitation
from src.models.salon_code import CODE_DIGITS, CodeAvailable

logger = logging.getLogger(__name__)

# How many times a fresh code is attempted before giving up. With a million values and a few
# thousand in circulation the first attempt almost always succeeds; the retries exist for the
# collision that will eventually happen, not for a saturated pool.
INSERT_ATTEMPTS = 8


def _random_code() -> str:
    """Six random digits, from secrets rather than random.

    Six digits from the ordinary generator are predictable from a handful of observed codes,
    and this code is what stands between a caller and somebody else's conversation.
    """
    return f"{secrets.randbelow(10 ** CODE_DIGITS):0{CODE_DIGITS}d}"


def claim(db: DbSession) -> str | None:
    """Reserve a free code and return it.

    Returns None when none could be obtained. Not fatal: the guest simply cannot join by
    telephone, and the join link still works. Refusing the invitation over a missing code
    would cost the conversation to save a channel.

    A free row is preferred over a fresh code so the pool is reused.
    """
    now = datetime.now(tz=timezone.utc)

    try:
        # Free in the pool *and* not still held by a pending invitation. The two can disagree:
        # a code returned to the pool while its invitation was left pending is free here and
        # spoken for there, and handing it out breaks the partial unique index on an INSERT
        # the caller has no way to anticipate — a 500 on inviting somebody.
        #
        # The lifecycle now closes those invitations, so this should find nothing. It stays
        # because the failure it prevents is not proportionate to its cost: the pool hands out
        # its oldest free code first, so one stale row does not fail one invitation, it fails
        # every invitation in the system until somebody notices.
        held = db.query(Invitation.phone_pin).filter(
            Invitation.status == "pending", Invitation.phone_pin.isnot(None)
        )
        free = (
            db.query(CodeAvailable)
            .filter(CodeAvailable.available.is_(True), CodeAvailable.code.notin_(held))
            .order_by(CodeAvailable.created_at)
            .first()
        )
        if free is not None:
            free.available = False
            free.claimed_at = now
            db.commit()
            return free.code
    except Exception:  # noqa: BLE001
        db.rollback()
        logger.warning("Could not claim a free telephone code", exc_info=True)

    # Nothing free: mint one. The primary key settles a race — two requests generating the
    # same value cannot both insert it, and the loser tries again.
    for _ in range(INSERT_ATTEMPTS):
        try:
            row = CodeAvailable(code=_random_code(), available=False, claimed_at=now)
            db.add(row)
            db.commit()
            return row.code
        except IntegrityError:
            db.rollback()
        except Exception:  # noqa: BLE001
            db.rollback()
            logger.warning("Could not mint a telephone code", exc_info=True)
            return None

    logger.warning("Could not mint a free telephone code after %d attempts", INSERT_ATTEMPTS)
    return None


def release(db: DbSession, codes) -> int:
    """Return the given codes to the pool. Returns how many changed."""
    wanted = [c for c in codes if c]
    if not wanted:
        return 0
    try:
        rows = (
            db.query(CodeAvailable)
            .filter(CodeAvailable.code.in_(wanted), CodeAvailable.available.is_(False))
            .all()
        )
        for row in rows:
            row.available = True
            row.claimed_at = None
        db.commit()
        return len(rows)
    except Exception:  # noqa: BLE001
        db.rollback()
        logger.warning("Could not release telephone codes", exc_info=True)
        return 0


def release_for_salon(db: DbSession, salon_id) -> int:
    """Return every code issued for one salon's invitations to the pool.

    Called when the salon ends. Without it a code stays reserved for a conversation that
    is over, and the pool drains one salon at a time.

    The codes are found through the invitations rather than stored against the salon,
    because that is where the mapping already lives — duplicating it here is what would
    eventually let the two disagree.
    """
    try:
        codes = [
            row.phone_pin
            for row in db.query(Invitation.phone_pin)
            .filter(Invitation.salon_id == salon_id, Invitation.phone_pin.isnot(None))
            .all()
        ]
    except Exception:  # noqa: BLE001
        logger.warning("Could not list codes for salon %s", salon_id, exc_info=True)
        return 0
    return release(db, codes)


def invitation_for_code(db: DbSession, code: str):
    """The pending invitation a dialled code belongs to, or None.

    This is what makes a telephone caller identifiable: the invitation carries the address
    and number the host typed, so the participation can be recorded like anyone else's.

    Only a reserved code resolves, and only to an invitation still pending. A free code
    points nowhere, and an accepted one has already been used.
    """
    code = (code or "").strip()
    if len(code) != CODE_DIGITS:
        return None
    try:
        reservation = db.get(CodeAvailable, code)
        if reservation is None or reservation.available:
            return None
        return (
            db.query(Invitation)
            .filter(Invitation.phone_pin == code, Invitation.status == "pending")
            .first()
        )
    except Exception:  # noqa: BLE001
        logger.warning("Could not look up telephone code", exc_info=True)
        return None
