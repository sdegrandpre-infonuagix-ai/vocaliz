"""Recording who took part in a salon, and how it went.

Every write here is best-effort. This is an observation record, not part of the
conversation: a failure to note that someone arrived must never keep them out of the
room, and a failure to note that they left must never block a session from closing.
"""
import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session as DbSession

from src.models.invitation import Invitation
from src.models.salon_event import SalonEvent
from src.models.uploaded_data import UploadedData
from src.models.user import User
from src.services import device_service, location_service, summary_service

logger = logging.getLogger(__name__)


def _country(value: str | None) -> str:
    """A two-letter region code, or nothing.

    Validated rather than trusted: the value comes from a browser locale and reaches us through
    a request body, so anything that is not two letters is not a country and is dropped instead
    of stored. Uppercased so a query never has to consider both cases.
    """
    code = (value or "").strip().upper()
    return code if len(code) == 2 and code.isalpha() else ""


def record_entry(
    db: DbSession,
    *,
    participant_identity: str,
    email: str = "",
    phone: str = "",
    user_type: str,
    salon_name: str,
    latitude: float | None = None,
    longitude: float | None = None,
    first_spoken_language: str | None = None,
    device_type: str = "",
    country: str = "",
    microphone_enabled: bool = False,
) -> None:
    """Note that someone joined a salon.

    Keyed on (participant_identity, salon_name), so re-entering the same salon updates
    the existing row instead of adding a second one. The absent half of the identity is an
    empty string, never None: it is part of a primary key, which cannot hold NULL.

    A participant with neither is not recorded at all. The database forbids it, and
    raising here would turn an observation into an obstacle — the point of this module is
    that failing to note something never keeps anyone out of a room.

    The entry time is not rewritten on a re-entry — the interesting figure is when the
    person first arrived, and overwriting it would erase exactly that. A position granted
    late is still filled in, since the first attempt may not have had one.

    A position is encoded to an Open Location Code before it is written — a cell a few
    kilometres across rather than a point. The precise coordinates never reach the disk.

    The device type is a category from a closed set, never the User-Agent header behind it,
    and it is written once for the same reason as the language: the interesting device is the
    one somebody arrived on. See device_service.
    """
    identity = (participant_identity or "").strip()
    email = email or ""
    phone = phone or ""
    code = location_service.plus_code(latitude, longitude)
    if not identity:
        # An address is no longer required — an anonymous guest has none, and refusing them is
        # what made them invisible. An identity is: without one there is no participant to
        # attribute anything to.
        logger.warning("Refusing to record a participation with no identity in %s", salon_name)
        return

    try:
        row = db.get(SalonEvent, (identity, salon_name))
        if row is None:
            db.add(
                SalonEvent(
                    participant_identity=identity,
                    email=email,
                    phone=phone,
                    user_type=user_type,
                    salon_name=salon_name,
                    plus_code=code,
                    device_type=device_service.normalise(device_type),
                    country=_country(country),
                    microphone_enabled=microphone_enabled,
                    first_spoken_language=first_spoken_language,
                    entered_at=datetime.now(tz=timezone.utc),
                )
            )
        else:
            # Filled in late when it was missing. Someone who refused the prompt on
            # arrival and granted it on re-entry is worth placing; someone who granted it
            # twice must not have the first reading replaced by a second.
            row.plus_code = row.plus_code or code
            # Filled in late when it was missing, and never replaced: somebody who rejoins from
            # a second device does not retroactively change the one they arrived on.
            row.device_type = row.device_type or device_service.normalise(device_type)
            # Filled in late when it was missing, never replaced: one participation, one
            # place, and the first reading is no less true than the second.
            row.country = row.country or _country(country)
            # Only ever set, never cleared: a microphone that worked once worked, and a
            # later call that happens not to mention it must not erase that.
            if microphone_enabled:
                row.microphone_enabled = True
            # Write-once. A later report must not overwrite the first: the column says
            # "first spoken", and a second value would quietly make that false.
            if row.first_spoken_language is None:
                row.first_spoken_language = first_spoken_language
            # Coming back reopens the participation: an exit time left over from the
            # previous visit would claim they are gone while they are talking.
            # Filled in late when they were missing: an anonymous guest who creates an
            # account mid-salon becomes reachable, and the row should say so. Never replaced —
            # one participation belongs to one person.
            row.email = row.email or email
            row.phone = row.phone or phone
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
        email, phone, user_type = _resolve_participant(db, participant_identity)
        if not email and not phone:
            return False

        row = db.get(SalonEvent, (email, phone, user_type, salon_name))
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
        email, phone, _ = _resolve_participant(db, participant_identity)
        if not email and not phone:
            return True
        # Matched on whichever half of the identity we hold. An empty string would match
        # every participant who lacks that half, so the absent one is never compared.
        identity = (
            (SalonEvent.email == email) if email else (SalonEvent.phone == phone)
        )
        prior = (
            db.query(SalonEvent)
            .filter(identity, SalonEvent.salon_name != salon_name)
            .first()
        )
        return prior is None
    except Exception:  # noqa: BLE001
        logger.warning("Could not check salon history for %s", participant_identity, exc_info=True)
        return True


def _resolve_participant(db: DbSession, identity: str) -> tuple[str, str, str]:
    """LiveKit identity to (email, phone, user_type).

    Empty strings rather than None throughout, because these values go straight into a
    primary key. A guest invited by text message alone has an empty email, and that is a
    complete identity — not a missing one.
    """
    if identity.startswith("guest-"):
        invitation = (
            db.query(Invitation)
            .filter(Invitation.id == identity.removeprefix("guest-"))
            .first()
        )
        if invitation is None:
            return "", "", "guest"
        return (invitation.guest_email or ""), (invitation.guest_phone or ""), "guest"

    user = db.query(User).filter(User.id == identity).first()
    if user is None:
        return "", "", "host"
    return (user.email or ""), (user.phone_number or ""), "host"


def record_upload(
    db: DbSession,
    *,
    salon_id,
    uploaded_by: str,
    url: str | None = None,
    filename: str | None = None,
    content: str | None = None,
    tokens: int | None = None,
    article_date=None,
    author: str = "",
    publisher: str = "",
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
                # Provenance, when the page said so. All three are absent for an uploaded
                # file, and often absent for a page too — a personal blog names no
                # publisher and plenty of articles carry no date.
                article_date=article_date,
                author=(author or "")[:200],
                publisher=(publisher or "")[:200],
            )
        )
        db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()
        logger.warning("Could not record upload for salon %s", salon_id, exc_info=True)


def purge_silent_participations(db: DbSession, *, confirm: bool = False) -> dict:
    """Remove participations where the agent never heard the person speak.

    A row with no first_spoken_language means somebody entered a salon and said nothing that was
    transcribed — a blocked microphone, or a departure within seconds. As test noise it is worth
    clearing; as data it is a record that they were there at all, so this is destructive and
    irreversible.

    Dry run unless confirm is True. The count matters more than the request: the admin listing
    aggregates languages across a person's salons, so somebody shown as speaking French may still
    have four silent rows out of five. Seeing the number before deleting is the difference between
    clearing noise and quietly halving a history.

    Returns what would be, or was, removed — broken down by role, because a silent guest is the
    expected case and a silent host is not.
    """
    try:
        doomed = (
            db.query(SalonEvent)
            .filter(SalonEvent.first_spoken_language.is_(None))
            .all()
        )
    except Exception:  # noqa: BLE001
        logger.warning("Could not list silent participations", exc_info=True)
        return {"status": "error", "matched": 0, "deleted": 0}

    by_role: dict[str, int] = {}
    for row in doomed:
        by_role[row.user_type] = by_role.get(row.user_type, 0) + 1

    summary = {
        "matched": len(doomed),
        "byRole": by_role,
        # Named, because the point of the dry run is to recognise whose history is at stake.
        "contacts": sorted({(row.email or row.phone) for row in doomed}),
    }

    if not confirm:
        return {"status": "dry_run", "deleted": 0, **summary}

    try:
        for row in doomed:
            db.delete(row)
        db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()
        logger.warning("Could not purge silent participations", exc_info=True)
        return {"status": "error", "deleted": 0, **summary}

    logger.info("Purged %d silent participation(s): %s", len(doomed), by_role)
    return {"status": "purged", "deleted": len(doomed), **summary}
