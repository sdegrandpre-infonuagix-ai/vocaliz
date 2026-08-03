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
from sqlalchemy import func
from sqlalchemy.orm import Session as DbSession

from src.database import get_db
from src.dependencies.auth import get_current_admin
from src.models.salon_event import SalonEvent
from src.models.user import User
from src.rate_limit import limiter
from src.schemas.admin import ParticipantRecord, ParticipantsResponse

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
    """Every email recorded in salon_events, one entry per person.

    Grouped by email rather than returned row by row: a person who held four salons is
    one participant, not four. The aggregation is done with count/min/max, which behave
    the same on Postgres and on the SQLite the tests run against — array_agg would not.
    """
    total = db.query(func.count(func.distinct(SalonEvent.email))).scalar() or 0

    grouped = (
        db.query(
            SalonEvent.email,
            func.count(func.distinct(SalonEvent.salon_name)).label("salons"),
            func.min(SalonEvent.entered_at).label("first_seen"),
            func.max(SalonEvent.entered_at).label("last_seen"),
        )
        .group_by(SalonEvent.email)
        # Most recent first: the useful end of the list when it grows.
        .order_by(func.max(SalonEvent.entered_at).desc())
        .limit(limit)
        .offset(offset)
        .all()
    )

    emails = [row.email for row in grouped]
    # Two small lookups instead of aggregating arrays in SQL. Restricted to the page's
    # emails, so their cost follows the page and not the size of the table.
    types: dict[str, set[str]] = {}
    languages: dict[str, set[str]] = {}
    if emails:
        for email, user_type in (
            db.query(SalonEvent.email, SalonEvent.user_type)
            .filter(SalonEvent.email.in_(emails))
            .distinct()
        ):
            types.setdefault(email, set()).add(user_type)
        for email, language in (
            db.query(SalonEvent.email, SalonEvent.first_spoken_language)
            .filter(
                SalonEvent.email.in_(emails),
                SalonEvent.first_spoken_language.isnot(None),
            )
            .distinct()
        ):
            languages.setdefault(email, set()).add(language)

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
                email=row.email,
                userTypes=sorted(types.get(row.email, set())),
                salonCount=row.salons,
                firstSeen=row.first_seen,
                lastSeen=row.last_seen,
                languages=sorted(languages.get(row.email, set())),
            )
            for row in grouped
        ],
    )
