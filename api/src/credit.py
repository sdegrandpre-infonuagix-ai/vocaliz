"""The welcome credit: giving it once, spending it first, and letting it lapse (FR67).

Everything here is written through the event stream from Story 8.1, so the balances are folds
rather than stored totals. That matters most at the point somebody disputes a charge: a
balance that was *computed* can be explained movement by movement, while a balance that was
*stored* can only be asserted.

Two parts, never one total. `gifted` was given by Vocaliz and expires; `paid` was handed over
by the person and does not. Keeping them apart is what makes a refund answerable at all —
from a single number, "how much of this is yours?" has no answer. And the gifted part is
spent first, which is not merely an ordering convention: it keeps the money somebody actually
paid intact for as long as possible.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum

from sqlalchemy.orm import Session

from src.ledger import EventType, Pool, append, as_utc, gifted_credits, paid_balance
from src.models.burned_identifier import BurnedIdentifier
from src.models.ledger_event import LedgerEvent

# Five dollars, once in a lifetime.
WELCOME_CREDIT_CENTS = 500

# Thirty calendar days, to the second. Seconds rather than a date arithmetic helper so that
# weekends, holidays and jurisdictions never enter into it — a promotion that expired
# differently in different countries would need a calendar per country, and the time of day
# is preserved for free.
EXPIRY_SECONDS = 2_592_000

# How long before the deadline somebody is told. A credit that evaporates in silence is an
# acquisition cost spent for nothing.
WARNING_DAYS = 7


class Tier(Enum):
    """The four tiers, cheapest first. Each adds exactly one thing to the one below it, so
    the price gap is always attributable to a single difference."""

    BASE = "Base"
    MODE_A = "Mode A"
    MODE_B = "Mode B"
    MODE_C = "Mode C"

    @property
    def label(self) -> str:
        return self.value


# No tier is free. Base is cheap and still costs money, because a free tier makes every
# other tier feel like a penalty rather than a choice.
TIER_RATES_CENTS_PER_HOUR: dict[Tier, int] = {
    Tier.BASE: 300,
    Tier.MODE_A: 750,
    Tier.MODE_B: 1500,
    Tier.MODE_C: 2250,
}

# Canonical English, like every other thing said to a participant. Configuration never holds
# a variant per language: these go through the same translation path as the journal, the ad
# creatives and the system notices, and a per-language table here would be a second path that
# quietly drifts from the first.
WELCOME_CREDIT_LABEL = "Vocaliz welcome credit"
PAID_BALANCE_LABEL = "Your topped-up balance"


@dataclass(frozen=True)
class Grant:
    """What happened when somebody signed up."""

    subject_id: uuid.UUID
    granted_cents: int
    expires_at: datetime | None
    refused_because: str | None = None


@dataclass(frozen=True)
class Balance:
    """Both parts, named, and never collapsed into one number."""

    gifted_cents: int
    paid_cents: int

    @property
    def total_cents(self) -> int:
        """A view, computed. Never the thing that is stored."""
        return self.gifted_cents + self.paid_cents

    @property
    def gifted_label(self) -> str:
        return WELCOME_CREDIT_LABEL

    @property
    def paid_label(self) -> str:
        return PAID_BALANCE_LABEL


def expires_at(granted_at: datetime) -> datetime:
    """The instant of the grant plus thirty calendar days, to the second."""
    return granted_at + timedelta(seconds=EXPIRY_SECONDS)


def grant_welcome_credit(
    db: Session,
    *,
    subject_id: uuid.UUID,
    identifiers: list[str],
    now: datetime,
) -> Grant:
    """Give the credit, unless one of these identifiers has already had it.

    A refusal burns nothing new. The fresh identifier in the list was never paid for, and
    burning it would spend somebody else's only chance on an attempt that was refused.

    What is refused is the gift and never the service: the caller goes on to create the
    account regardless, and the person can pay for any tier they like.
    """
    # Same reasoning as `debit`: a burn recorded earlier in this transaction has to be
    # visible, or two signups in one unit of work would both be granted.
    db.flush()
    already = (
        db.query(BurnedIdentifier)
        .filter(BurnedIdentifier.identifier.in_(identifiers))
        .first()
    )
    if already is not None:
        return Grant(
            subject_id=subject_id,
            granted_cents=0,
            expires_at=None,
            refused_because=(
                f"{already.identifier} has already had a welcome credit. The account is "
                "created and any tier can be paid for — only the gift is refused."
            ),
        )

    append(
        db,
        type=EventType.CREDIT_GRANTED,
        subject_id=subject_id,
        amount_cents=WELCOME_CREDIT_CENTS,
        pool=Pool.GIFTED,
        occurred_at=now,
        detail=WELCOME_CREDIT_LABEL,
    )
    for identifier in identifiers:
        db.add(
            BurnedIdentifier(identifier=identifier, burned_at=now, granted_to=subject_id)
        )

    return Grant(
        subject_id=subject_id,
        granted_cents=WELCOME_CREDIT_CENTS,
        expires_at=expires_at(now),
    )


def balance(db: Session, subject_id: uuid.UUID) -> Balance:
    """Both parts, folded out of the stream."""
    return Balance(
        gifted_cents=gifted_credits(db, subject_id).balance_cents,
        paid_cents=paid_balance(db, subject_id).balance_cents,
    )


def debit(
    db: Session, subject_id: uuid.UUID, *, cents: int, now: datetime
) -> list[LedgerEvent]:
    """Spend, gifted part first, recording which part each movement came from.

    A debit spanning both parts is written as *two* movements rather than one naming two
    pools — one movement covering both would be a single number again, and the audit trail
    exists precisely to answer which part was touched.
    """
    # Flush first. The split is decided by reading the balance back, so anything written
    # earlier in this transaction and not yet sent would be invisible — and a debit would
    # silently come out of the wrong part. Correct whatever the session's autoflush setting
    # happens to be, rather than correct only when it is on.
    db.flush()

    moves: list[LedgerEvent] = []
    remaining = cents

    from_gifted = min(remaining, max(0, balance(db, subject_id).gifted_cents))
    if from_gifted:
        moves.append(
            append(
                db,
                type=EventType.DEBITED,
                subject_id=subject_id,
                amount_cents=-from_gifted,
                pool=Pool.GIFTED,
                occurred_at=now,
            )
        )
        remaining -= from_gifted

    if remaining > 0:
        moves.append(
            append(
                db,
                type=EventType.DEBITED,
                subject_id=subject_id,
                amount_cents=-remaining,
                pool=Pool.PAID,
                occurred_at=now,
            )
        )

    return moves


def expire_credit(db: Session, subject_id: uuid.UUID, *, now: datetime) -> LedgerEvent | None:
    """Take back whatever gifted credit is left, and nothing else.

    The paid balance and the cumulative total are untouched: the gift lapses, money somebody
    handed over does not. An already-empty credit writes nothing — an event for a movement of
    zero is noise in a stream that has to stay readable.
    """
    db.flush()
    remaining = balance(db, subject_id).gifted_cents
    if remaining <= 0:
        return None

    return append(
        db,
        type=EventType.EXPIRED,
        subject_id=subject_id,
        amount_cents=-remaining,
        pool=Pool.GIFTED,
        occurred_at=now,
        detail=WELCOME_CREDIT_LABEL,
    )


def _granted_at(db: Session, subject_id: uuid.UUID) -> datetime | None:
    row = (
        db.query(LedgerEvent)
        .filter(
            LedgerEvent.subject_id == subject_id,
            LedgerEvent.type == EventType.CREDIT_GRANTED.value,
        )
        .order_by(LedgerEvent.occurred_at)
        .first()
    )
    return None if row is None else as_utc(row.occurred_at)


def warning_due(db: Session, subject_id: uuid.UUID, *, now: datetime) -> bool:
    """Whether to warn somebody that their credit is about to lapse.

    Three ways to answer no, and each is a decision rather than an omission. Too early, and
    the message arrives while nothing is at stake. Nothing left, and it tells somebody they
    are about to lose nothing — which is how a message teaches people to ignore the next one.
    Already sent, because a daily reminder until the deadline is the same lesson repeated.
    """
    if balance(db, subject_id).gifted_cents <= 0:
        return False

    granted = _granted_at(db, subject_id)
    if granted is None:
        return False

    if now < expires_at(granted) - timedelta(days=WARNING_DAYS):
        return False

    already = (
        db.query(LedgerEvent)
        .filter(
            LedgerEvent.subject_id == subject_id,
            LedgerEvent.type == EventType.EXPIRY_WARNED.value,
        )
        .first()
    )
    return already is None


def warning_text(remaining_cents: int) -> str:
    """What the warning says: the amount, and what it buys in each tier.

    A date on its own asks somebody to do the arithmetic that decides whether they care, and
    most people will decline. "1 h 36 in Base" is the same fact already answered.
    """
    parts = []
    for tier in Tier:
        minutes = round(remaining_cents / TIER_RATES_CENTS_PER_HOUR[tier] * 60)
        parts.append(f"{tier.label}: {minutes // 60} h {minutes % 60:02d}")
    return (
        f"You have {remaining_cents / 100:.2f} left of your {WELCOME_CREDIT_LABEL}. "
        + " · ".join(parts)
    )


def refundable_cents(db: Session, subject_id: uuid.UUID) -> int:
    """What can be refunded: the paid part, and never the gift.

    Somebody who only ever spent the welcome credit is owed nothing, and the honest reply
    says so in those words rather than quoting a zero — they did not lose a refund, they
    never paid anything.
    """
    return max(0, balance(db, subject_id).paid_cents)


def refund_explanation(db: Session, subject_id: uuid.UUID) -> str:
    amount = refundable_cents(db, subject_id)
    if amount == 0:
        return (
            "There is nothing to refund: no money was ever paid in. The "
            f"{WELCOME_CREDIT_LABEL} was given by Vocaliz and is not refundable."
        )
    return f"{amount / 100:.2f} of {PAID_BALANCE_LABEL} can be refunded."
