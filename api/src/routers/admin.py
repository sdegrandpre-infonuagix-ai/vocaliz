"""Administration router — reading the participation records.

Everything here is behind get_current_admin, and everything here returns personal data.
Two consequences shape the code below: the responses are paginated so that no single
call can quietly become a full export, and each call is written to the log with the
administrator who made it, because a read of this kind should leave a trace.

The emails are stored in clear. Aurora encrypts its storage, snapshots and backups with
KMS, but that is transparent to SQL — there is no column-level cipher and so nothing to
decrypt on the way out.
"""
import logging

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, tuple_
from sqlalchemy.orm import Session as DbSession

from src.database import get_db
from src.dependencies.auth import get_current_admin
from src.models.salon_event import SalonEvent
from src.models.user import User
from src.rate_limit import limiter
from src.schemas.admin import (
    ParticipantRecord,
    ParticipantsResponse,
    ReportResponse,
)
from src.services import participant_report

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/participants", response_model=ParticipantsResponse)
@limiter.limit("30/minute")
def list_participants(
    request: Request,
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: DbSession = Depends(get_db),
    admin: User = Depends(get_current_admin),
) -> ParticipantsResponse:
    """Every contact recorded in salon_events, one entry per person.

    Grouped rather than returned row by row: a person who held four salons is one
    participant, not four. Identity is the (email, phone) pair, since a guest invited by
    text alone has no address — grouping on email would collapse all of them into one row
    keyed on the empty string.

    The aggregation uses count/min/max, which behave the same on Postgres and on the
    SQLite the tests run against; array_agg would not.
    """
    # Counted on the same thing the page groups on, or "returned of total" compares two
    # different quantities: a truncated list would look complete, or a complete one truncated.
    #
    # Contact details cannot serve here. Two anonymous guests share an empty address and an
    # empty number, so counting distinct pairs reported one participant where there were two —
    # and the more anonymous guests arrived, the further off it got.
    total = (
        db.query(func.count(func.distinct(SalonEvent.participant_identity))).scalar() or 0
    )

    # Grouped on the LiveKit identity rather than on contact details, and that matters as soon
    # as anonymous guests exist: they have neither an address nor a number, so grouping on those
    # folded every one of them into a single line labelled with nothing. The identity is present
    # for everybody, whether or not anyone knows who they are.
    grouped = (
        db.query(
            SalonEvent.participant_identity,
            func.max(SalonEvent.email).label("email"),
            func.max(SalonEvent.phone).label("phone"),
            func.count(func.distinct(SalonEvent.salon_name)).label("salons"),
            func.min(SalonEvent.entered_at).label("first_seen"),
            func.max(SalonEvent.entered_at).label("last_seen"),
        )
        .group_by(SalonEvent.participant_identity)
        # Most recent first: the useful end of the list when it grows.
        .order_by(func.max(SalonEvent.entered_at).desc())
        .limit(limit)
        .offset(offset)
        .all()
    )

    people = [row.participant_identity for row in grouped]
    # Two small lookups instead of aggregating arrays in SQL. Restricted to the page's
    # emails, so their cost follows the page and not the size of the table.
    types: dict[str, set[str]] = {}
    languages: dict[str, set[str]] = {}
    devices: dict[str, set[str]] = {}
    if people:
        # One column now, so the old caveat about two independent IN clauses matching
        # combinations that are not on this page no longer applies: an identity is exact.
        on_page = SalonEvent.participant_identity.in_(people)
        for identity, user_type in (
            db.query(SalonEvent.participant_identity, SalonEvent.user_type)
            .filter(on_page)
            .distinct()
        ):
            types.setdefault(identity, set()).add(user_type)
        for identity, language in (
            db.query(SalonEvent.participant_identity, SalonEvent.first_spoken_language)
            .filter(on_page, SalonEvent.first_spoken_language.isnot(None))
            .distinct()
        ):
            languages.setdefault(identity, set()).add(language)
        # Every device a person has been seen on, not the last one: somebody who hosts from a
        # laptop and joins from a phone is both, and keeping only one would answer a question
        # nobody asked.
        for identity, device in (
            db.query(SalonEvent.participant_identity, SalonEvent.device_type)
            .filter(on_page, SalonEvent.device_type != "")
            .distinct()
        ):
            devices.setdefault(identity, set()).add(device)

    # Who read what, and how much of it. Not the addresses themselves: writing the list
    # to CloudWatch would copy the personal data into a second store with its own
    # retention, which is the opposite of what this endpoint is trying to keep contained.
    logger.info(
        "Administrator %s listed participants (returned=%d of total=%d, offset=%d)",
        admin.email,
        len(grouped),
        total,
        offset,
    )

    return ParticipantsResponse(
        total=total,
        returned=len(grouped),
        participants=[
            ParticipantRecord(
                participantIdentity=row.participant_identity,
                email=row.email,
                phone=row.phone,
                userTypes=sorted(types.get(row.participant_identity, set())),
                salonCount=row.salons,
                firstSeen=row.first_seen,
                lastSeen=row.last_seen,
                languages=sorted(languages.get(row.participant_identity, set())),
                devices=sorted(devices.get(row.participant_identity, set())),
            )
            for row in grouped
        ],
    )


@router.get("/report", response_model=ReportResponse)
@limiter.limit("30/minute")
def participant_report_now(
    request: Request,
    db: DbSession = Depends(get_db),
    admin: User = Depends(get_current_admin),
) -> ReportResponse:
    """The hourly participant report, on demand and in the browser.

    The same rows the email carries, built by the same function. Two readings of one table
    that could disagree would be worse than having only the email: the report is what
    decisions get made from, and "the page said something else" is not a footnote.

    The caveats travel with the rows rather than being written into the page. Several columns
    are weaker than they look — a device token measures browsers and not people, and metered
    seconds belong to the account rather than to the participations listed beside them — and a
    reader who sees the numbers without the qualifications draws conclusions the data does not
    support. Sending them together is what makes that impossible to skip.
    """
    rows = participant_report.collect(db)
    logger.info("Admin %s read the participant report (%d contacts)", admin.email, len(rows))
    return ReportResponse(
        columns=participant_report.COLUMNS,
        rows=rows,
        caveats=participant_report.caveat_lines(),
        contacts=len(rows),
    )
