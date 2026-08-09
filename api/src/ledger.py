"""Writing to the event stream, and folding the views back out of it (NFR7).

Every view here is a fold. That is the whole design: a derived view cannot contradict the
stream, while a view written alongside it eventually will — and once two records of the same
fact disagree, nothing in the system is able to say which one to believe.

So the grant audit (FR66), the gifted-credit entries (FR67), the paid-balance journal (FR68)
and the metrics (NFR4) are all computed from `ledger_events` and never stored beside it. When
a cached view and the stream disagree, the view is thrown away and rebuilt; the events are
never touched.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum

from sqlalchemy.orm import Session

from src.models.ledger_event import LedgerEvent


def as_utc(moment: datetime) -> datetime:
    """Put the timezone back on a timestamp that lost it in the database.

    Postgres keeps it; SQLite has no timezone type and hands back a naive value. Attaching
    UTC is not a guess — every writer here stamps an aware instant — but leaving it naive
    would be, and comparing a naive timestamp to an aware one raises rather than being
    quietly wrong. Which is the only reason this has a name instead of being forgotten.
    """
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=timezone.utc)


class EventType(Enum):
    """Every fact the stream records — financial and operational alike."""

    CREDIT_GRANTED = "credit_granted"
    RECHARGED = "recharged"
    DEBITED = "debited"
    REFUNDED = "refunded"
    EXPIRED = "expired"
    ABANDONED = "abandoned"
    # Operational rather than financial: the person was told their credit is about to
    # lapse. In the same stream because "was he warned?" is a question a dispute asks,
    # and a second log of it would be the two-log mistake again.
    EXPIRY_WARNED = "expiry_warned"
    # A compensating event. Never a rewrite: it points at what it corrects and both survive.
    CORRECTED = "corrected"


class Pool(Enum):
    """Which balance a fact moved.

    Two pools because the money is different: gifted credit was given and expires, paid
    credit was bought and does not.
    """

    GIFTED = "gifted"
    PAID = "paid"


class Actor(Enum):
    SYSTEM = "system"
    OPERATOR = "operator"


def append(
    db: Session,
    *,
    type: EventType,
    subject_id: uuid.UUID,
    amount_cents: int | None = None,
    pool: Pool | None = None,
    occurred_at: datetime | None = None,
    actor: Actor = Actor.SYSTEM,
    actor_id: uuid.UUID | None = None,
    corrects_id: uuid.UUID | None = None,
    subject_type: str = "user",
    currency: str = "usd",
    detail: str | None = None,
) -> LedgerEvent:
    """Write one fact. The only way anything enters the stream.

    There is deliberately no `update` or `remove` beside it: the absence is the guarantee,
    and the model refuses both at the ORM level in case somebody reaches past this function.
    """
    row = LedgerEvent(
        id=uuid.uuid4(),
        type=type.value,
        subject_id=subject_id,
        subject_type=subject_type,
        amount_cents=amount_cents,
        currency=currency,
        pool=None if pool is None else pool.value,
        actor=actor.value,
        actor_id=actor_id,
        corrects_id=corrects_id,
        detail=detail,
    )
    if occurred_at is not None:
        row.occurred_at = occurred_at
    db.add(row)
    return row


def _events_for(
    db: Session, subject_id: uuid.UUID, kinds: tuple[EventType, ...] | None = None
) -> list[LedgerEvent]:
    """One subject's events, in the order they happened.

    Ordered by `occurred_at` and then by `id`. Two facts stamped at the same instant need a
    settled order or a rebuild is not actually reproducible, and the identifier is the only
    tie-break available that does not depend on how the rows happened to be inserted.
    """
    query = db.query(LedgerEvent).filter(LedgerEvent.subject_id == subject_id)
    if kinds:
        query = query.filter(LedgerEvent.type.in_([kind.value for kind in kinds]))
    return sorted(query.all(), key=lambda row: (as_utc(row.occurred_at), str(row.id)))


@dataclass(frozen=True)
class Balance:
    """One pool, folded out of the stream."""

    pool: str
    balance_cents: int
    events: int


def _balance(db: Session, subject_id: uuid.UUID, pool: Pool) -> Balance:
    rows = [
        row
        for row in _events_for(db, subject_id)
        if row.pool == pool.value and row.amount_cents is not None
    ]
    return Balance(
        pool=pool.value,
        balance_cents=sum(row.amount_cents for row in rows),
        events=len(rows),
    )


def gifted_credits(db: Session, subject_id: uuid.UUID) -> Balance:
    """FR67. Credit that was given, and therefore expires."""
    return _balance(db, subject_id, Pool.GIFTED)


def paid_balance(db: Session, subject_id: uuid.UUID) -> Balance:
    """FR68. Credit that was bought, and therefore does not."""
    return _balance(db, subject_id, Pool.PAID)


def grant_audit(
    db: Session, subject_id: uuid.UUID, kinds: tuple[EventType, ...] = (EventType.CREDIT_GRANTED,)
) -> list[LedgerEvent]:
    """FR66. What was granted to somebody, in the order it happened and by whom."""
    return _events_for(db, subject_id, kinds)


@dataclass(frozen=True)
class LedgerMetrics:
    """NFR4, folded out of the same stream so a metric can never disagree with a balance."""

    events: int
    granted_cents: int
    recharged_cents: int
    debited_cents: int
    refunded_cents: int
    expired_cents: int


def ledger_metrics(db: Session) -> LedgerMetrics:
    rows = db.query(LedgerEvent).all()

    def total(kind: EventType) -> int:
        return sum(
            abs(row.amount_cents)
            for row in rows
            if row.type == kind.value and row.amount_cents is not None
        )

    return LedgerMetrics(
        events=len(rows),
        granted_cents=total(EventType.CREDIT_GRANTED),
        recharged_cents=total(EventType.RECHARGED),
        debited_cents=total(EventType.DEBITED),
        refunded_cents=total(EventType.REFUNDED),
        expired_cents=total(EventType.EXPIRED),
    )


@dataclass(frozen=True)
class SubjectView:
    """Everything one subject's stream folds into.

    Comparable by value on purpose: rebuilding it twice must produce something equal, and
    that equality is the property that makes the stream verifiable rather than merely
    trusted.
    """

    subject_id: uuid.UUID
    gifted: Balance
    paid: Balance
    events: int


def rebuild(db: Session, subject_id: uuid.UUID) -> SubjectView:
    """Fold one subject's whole stream from the beginning.

    Used both to build a view and to check one: a cached view that differs from this is
    stale, and it is the view that gets thrown away. Choosing the other way round would mean
    choosing which record to believe, and nothing in the system is able to make that choice.
    """
    return SubjectView(
        subject_id=subject_id,
        gifted=gifted_credits(db, subject_id),
        paid=paid_balance(db, subject_id),
        events=len(_events_for(db, subject_id)),
    )
