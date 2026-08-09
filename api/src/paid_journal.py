"""What is owed to users, folded out of the same event stream (FR68 / NFR7).

The mirror of `credit_journal`, and the distinction between the two is the point. A gifted
credit is a **charge** — money Vocaliz spent acquiring somebody. A paid balance is a **debt** —
money a user handed over that has not yet become service. Adding them together makes both
unreadable, so nothing here ever touches the gifted pool.

Collected, consumed, refunded and rebated describe what happened *during* a period;
outstanding describes what is still owed *at the end of it*. Each is kept apart for its own
reason. A refund is not consumption — money going back out is not money earned. And a rebate
(FR70) is not collection: Stripe took less than the balance credited, so the difference is a
commercial charge that still lands in the liability.

A paid balance never expires. Somebody who stops using Vocaliz is still owed what they put in,
indefinitely — which is why dormant balances must be isolatable by age, and why the holder is
written to every year for as long as the money is still theirs.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from src.ledger import EventType, Pool, as_utc
from src.models.ledger_event import LedgerEvent

# How long without activity before the holder is written to, and again each year after.
DORMANCY_YEARS = 1

# Every reminder is copied here, so the operator has the same trace the user does.
REMINDER_COPY_TO = "s.degrandpre@vocaliz.net"

_COLLECTS = {EventType.RECHARGED.value}
_CONSUMES = {EventType.DEBITED.value}
_REFUNDS = {EventType.REFUNDED.value}
# Balance the payer received without paying for it, out of an avoided commission.
# Never collection: Stripe took less than the balance credited.
_REBATES = {EventType.REBATE_GRANTED.value}


def _paid(db: Session, subject_id: uuid.UUID | None = None) -> list[LedgerEvent]:
    """Every event touching the paid pool, oldest first."""
    query = db.query(LedgerEvent).filter(LedgerEvent.pool == Pool.PAID.value)
    if subject_id is not None:
        query = query.filter(LedgerEvent.subject_id == subject_id)
    return sorted(query.all(), key=lambda row: (as_utc(row.occurred_at), str(row.id)))


@dataclass(frozen=True)
class PaidTotals:
    """One period. What moved through it, and what was still owed at the close."""

    collected_cents: int
    consumed_cents: int
    refunded_cents: int
    # Handed back out of an avoided store commission (FR70). Real balance, and therefore
    # part of what is owed — but never part of what was collected.
    rebated_cents: int
    outstanding_cents: int


def outstanding_cents(db: Session, *, as_of: datetime | None = None) -> int:
    """What is owed to users in total — the liability, client money held.

    A figure about Vocaliz rather than about one person, which is why it sums across
    everybody. Never includes gifted credit: that is a cost already incurred, not a debt.
    """
    return sum(
        row.amount_cents
        for row in _paid(db)
        if row.amount_cents is not None
        and (as_of is None or as_utc(row.occurred_at) <= as_of)
    )


def paid_totals(db: Session, *, since: datetime, until: datetime) -> PaidTotals:
    """The figures a period close needs, each kept apart from the others."""
    collected = consumed = refunded = rebated = 0

    for row in _paid(db):
        if row.amount_cents is None:
            continue
        if not since <= as_utc(row.occurred_at) <= until:
            continue
        if row.type in _COLLECTS:
            collected += row.amount_cents
        elif row.type in _CONSUMES:
            consumed += abs(row.amount_cents)
        elif row.type in _REFUNDS:
            refunded += abs(row.amount_cents)
        elif row.type in _REBATES:
            rebated += row.amount_cents

    return PaidTotals(
        collected_cents=collected,
        consumed_cents=consumed,
        refunded_cents=refunded,
        rebated_cents=rebated,
        outstanding_cents=outstanding_cents(db, as_of=until),
    )


@dataclass(frozen=True)
class DormantBalance:
    """Money still owed to somebody who has not been seen for a while."""

    subject_id: uuid.UUID
    balance_cents: int
    last_activity_at: datetime


def _last_activity(db: Session, subject_id: uuid.UUID) -> datetime | None:
    """When this person was last seen doing anything at all.

    Read off the whole stream rather than the paid pool alone: spending gifted credit is
    activity too, and a clock that ignored it would write to somebody who used Vocaliz
    yesterday.
    """
    rows = db.query(LedgerEvent).filter(LedgerEvent.subject_id == subject_id).all()
    return max((as_utc(row.occurred_at) for row in rows), default=None)


def _balance_of(db: Session, subject_id: uuid.UUID) -> int:
    return sum(
        row.amount_cents for row in _paid(db, subject_id) if row.amount_cents is not None
    )


def dormant_balances(
    db: Session, *, as_of: datetime, years: int = DORMANCY_YEARS
) -> list[DormantBalance]:
    """Everybody still owed money who has not been seen for `years`.

    An empty balance is never dormant — there is nothing to be owed, so there is nothing to
    isolate and nobody to write to.
    """
    cutoff = as_of - timedelta(days=365 * years)
    dormant: list[DormantBalance] = []

    for subject_id in {row.subject_id for row in _paid(db)}:
        balance = _balance_of(db, subject_id)
        if balance <= 0:
            continue
        last = _last_activity(db, subject_id)
        if last is None or last > cutoff:
            continue
        dormant.append(
            DormantBalance(
                subject_id=subject_id, balance_cents=balance, last_activity_at=last
            )
        )

    return sorted(dormant, key=lambda row: row.last_activity_at)


def reminder_due(
    db: Session, subject_id: uuid.UUID, *, as_of: datetime, years: int = DORMANCY_YEARS
) -> bool:
    """Whether to write to somebody about money of theirs sitting here.

    Renewed each anniversary for as long as the balance stays positive and untouched. Not
    sent at all on an empty balance: there is nothing to claim, and a letter saying so is a
    letter that should not have been sent.
    """
    if _balance_of(db, subject_id) <= 0:
        return False

    cutoff = as_of - timedelta(days=365 * years)
    last = _last_activity(db, subject_id)
    if last is None or last > cutoff:
        return False

    reminded = [
        as_utc(row.occurred_at)
        for row in db.query(LedgerEvent)
        .filter(
            LedgerEvent.subject_id == subject_id,
            LedgerEvent.type == EventType.DORMANT_REMINDED.value,
        )
        .all()
    ]
    return not reminded or max(reminded) <= cutoff


def reminder_text(*, balance_cents: int) -> str:
    """What the holder of a dormant balance is told: that it is theirs, and how much.

    The amount rather than an invitation to log in and look. Somebody who has not opened
    Vocaliz for a year will not open it to find out whether the letter was worth reading.
    """
    return (
        "Your Vocaliz.net account has been inactive for a year. "
        f"You still have {balance_cents / 100:.2f} on it, which remains yours."
    )
