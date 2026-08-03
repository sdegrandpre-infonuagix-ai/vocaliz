"""Recording who took part in a salon, and how it went.

Every write here is best-effort. This is an observation record, not part of the
conversation: a failure to note that someone arrived must never keep them out of the
room, and a failure to note that they left must never block a session from closing.
"""
import logging
from datetime import datetime, timezone

from fastapi import Request
from sqlalchemy.orm import Session as DbSession

from src.models.invitation import Invitation
from src.models.salon_event import SalonEvent
from src.models.uploaded_data import UploadedData
from src.models.user import User
from src.services import summary_service

logger = logging.getLogger(__name__)


def client_ip(request: Request) -> str | None:
    """The caller's address as seen from outside.

    X-Forwarded-For comes first and its *first* entry is the one that matters: API Gateway
    appends to the list, so the leftmost value is the original client and everything after
    is infrastructure. request.client is the fallback, and behind the proxy it reports the
    hop rather than the caller.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        first = forwarded.split(",")[0].strip()
        if first:
            return first[:45]
    return request.client.host[:45] if request.client else None


def record_entry(
    db: DbSession,
    *,
    email: str,
    user_type: str,
    salon_name: str,
    ip: str | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
    first_spoken_language: str | None = None,
) -> None:
    """Note that someone joined a salon.

    Keyed on (email, user_type, salon_name), so re-entering the same salon updates the
    existing row instead of adding a second one. The entry time is not rewritten on a
    re-entry — the interesting figure is when the person first arrived, and overwriting it
    would erase exactly that. A position or an address learned late is still filled in,
    since the first attempt may have had neither.
    """
    try:
        row = db.get(SalonEvent, (email, user_type, salon_name))
        if row is None:
            db.add(
                SalonEvent(
                    email=email,
                    user_type=user_type,
                    salon_name=salon_name,
                    client_ip=ip,
                    gps_latitude=latitude,
                    gps_longitude=longitude,
                    first_spoken_language=first_spoken_language,
                    entered_at=datetime.now(tz=timezone.utc),
                )
            )
        else:
            row.client_ip = ip or row.client_ip
            row.gps_latitude = latitude if latitude is not None else row.gps_latitude
            row.gps_longitude = longitude if longitude is not None else row.gps_longitude
            # Write-once. A later report must not overwrite the first: the column says
            # "first spoken", and a second value would quietly make that false.
            if row.first_spoken_language is None:
                row.first_spoken_language = first_spoken_language
            # Coming back reopens the participation: an exit time left over from the
            # previous visit would claim they are gone while they are talking.
            row.exited_at = None
        db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()
        logger.warning("Could not record entry for %s in %s", user_type, salon_name, exc_info=True)


def record_salon_exit(db: DbSession, salon_name: str, *, enjoyed: bool | None = None) -> int:
    """Close every open participation in a salon, and record the closing answer.

    Called when the session ends, which is the only moment the API reliably learns that
    everyone is gone — a guest who closes their tab tells nobody. Rows already closed are
    left alone so a second call cannot move an exit time.

    Returns how many rows were closed.
    """
    try:
        rows = (
            db.query(SalonEvent)
            .filter(SalonEvent.salon_name == salon_name, SalonEvent.exited_at.is_(None))
            .all()
        )
        now = datetime.now(tz=timezone.utc)
        for row in rows:
            row.exited_at = now
            # Only overwrite when an answer was actually given. NULL means unknown, and
            # writing NULL over an existing answer would destroy it.
            if enjoyed is not None:
                row.enjoyed = enjoyed
        db.commit()
        return len(rows)
    except Exception:  # noqa: BLE001
        db.rollback()
        logger.warning("Could not close participations for %s", salon_name, exc_info=True)
        return 0


def record_first_language(
    db: DbSession, *, salon_name: str, participant_identity: str, language: str
) -> bool:
    """Note the first language heard from one participant of one salon.

    The identity is the LiveKit one, and it is the only handle the agent has. Two shapes
    resolve to an email: a guest joins as `guest-{invitation_id}`, which leads to the
    invitation and the address the host typed; anyone else joins under their user id.

    Write-once, and the row must already exist — a language reported for someone who never
    entered is noise. Returns whether anything was written.
    """
    try:
        email, user_type = _resolve_participant(db, participant_identity)
        if not email:
            return False

        row = db.get(SalonEvent, (email, user_type, salon_name))
        if row is None or row.first_spoken_language is not None:
            return False

        row.first_spoken_language = language
        db.commit()
        return True
    except Exception:  # noqa: BLE001
        db.rollback()
        logger.warning("Could not record language for %s", participant_identity, exc_info=True)
        return False


def is_first_salon(db: DbSession, *, salon_name: str, participant_identity: str) -> bool:
    """Whether this person has ever taken part in a salon other than this one.

    The row for the current salon already exists by the time anyone asks — entry is
    recorded when the participant joins — so the question is not "any rows" but "any rows
    elsewhere". Getting that wrong would make every salon look like a first.

    Unknown participants count as first-timers. The alternative is to stay silent about
    someone we cannot identify, and a greeting that skips its aside is a worse failure
    than one that repeats it.
    """
    try:
        email, _ = _resolve_participant(db, participant_identity)
        if not email:
            return True
        prior = (
            db.query(SalonEvent)
            .filter(SalonEvent.email == email, SalonEvent.salon_name != salon_name)
            .first()
        )
        return prior is None
    except Exception:  # noqa: BLE001
        logger.warning("Could not check salon history for %s", participant_identity, exc_info=True)
        return True


def _resolve_participant(db: DbSession, identity: str) -> tuple[str | None, str]:
    """LiveKit identity to (email, user_type)."""
    if identity.startswith("guest-"):
        invitation = (
            db.query(Invitation)
            .filter(Invitation.id == identity.removeprefix("guest-"))
            .first()
        )
        return (invitation.guest_email if invitation else None), "guest"

    user = db.query(User).filter(User.id == identity).first()
    return (user.email if user else None), "host"


def record_upload(
    db: DbSession,
    *,
    salon_id,
    uploaded_by: str,
    url: str | None = None,
    filename: str | None = None,
    content: str | None = None,
    tokens: int | None = None,
) -> None:
    """Note a source given to a salon's agent, and what it weighed.

    Accounting only: nothing reads this back during a conversation. It exists because the
    schema records sources in two places — the sessions row and session_sources — and
    measures them in neither.

    Best-effort. Failing to note a source must not stop the agent from receiving it.
    """
    try:
        db.add(
            UploadedData(
                salon_id=salon_id,
                uploaded_by=uploaded_by,
                url=url,
                filename=filename,
                # Measured, not estimated.
                content_size=len(content) if content else None,
                content_hash=summary_service.content_hash(content) if content else None,
                # Whatever the summariser reported spending. Null when it did not run.
                tokens=tokens,
            )
        )
        db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()
        logger.warning("Could not record upload for salon %s", salon_id, exc_info=True)
