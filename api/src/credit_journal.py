"""What every gifted credit cost, folded out of the event stream (FR67 / NFR7).

A derived view and never a parallel write. Story 8.1 established that two records of one fact
drift apart and that nothing can then say which is right; this is the first place somebody
would reasonably have reached for a second table, so there deliberately isn't one — and a test
reads this file to check that no `__tablename__` and no `db.add` ever appear in it.

Each credit carries four amounts, and every closed entry satisfies
`issued = consumed + expired + abandoned`. Three closing modes rather than two, because an
account deleted mid-credit is neither consumption nor expiry. Without `abandoned` as a state
of its own, every period total would be silently wrong from the first deletion onwards, which
is the worst kind of wrong: nothing looks broken.

Only what was **consumed** is an expense. It alone bought provider time. A credit that expired
untouched cost nothing, and booking it as spend would inflate the acquisition cost with money
that never left the building.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from sqlalchemy.orm import Session

from src.credit import WELCOME_CREDIT_LABEL, expires_at
from src.ledger import Actor, EventType, Pool, as_utc
from src.models.ledger_event import LedgerEvent


class CreditType(Enum):
    """Why a credit was given. Different campaigns with different economics."""

    WELCOME = "welcome"
    REACTIVATION = "reactivation"


@dataclass
class CreditEntry:
    """One credit, and what became of every cent of it."""

    subject_id: uuid.UUID
    credit_type: CreditType
    issued_cents: int
    issued_at: datetime
    expires_at: datetime
    author: str
    operator_id: uuid.UUID | None = None
    reason: str = ""
    consumed_cents: int = 0
    expired_cents: int = 0
    abandoned_cents: int = 0

    @property
    def remaining_cents(self) -> int:
        return self.issued_cents - self.consumed_cents - self.expired_cents - self.abandoned_cents

    @property
    def closed(self) -> bool:
        """Nothing left to account for, by whichever of the three routes."""
        return self.remaining_cents <= 0

    @property
    def balances(self) -> bool:
        """The invariant, available to anybody who wants to assert it."""
        return self.issued_cents == (
            self.consumed_cents + self.expired_cents + self.abandoned_cents
        )


def _type_of(row: LedgerEvent) -> CreditType:
    """Welcome or reactivation, read off the grant itself.

    From the detail the granting code wrote rather than from the amount: the reactivation
    amount is an operator's choice and could coincide with the welcome credit at any time.
    """
    return (
        CreditType.WELCOME
        if row.detail == WELCOME_CREDIT_LABEL
        else CreditType.REACTIVATION
    )


def _gifted(db: Session, subject_id: uuid.UUID | None) -> list[LedgerEvent]:
    query = db.query(LedgerEvent).filter(LedgerEvent.pool == Pool.GIFTED.value)
    if subject_id is not None:
        query = query.filter(LedgerEvent.subject_id == subject_id)
    # Grants first when two events share an instant. A draw can only exist because a grant
    # preceded it in reality, and letting the identifier break that tie would sometimes
    # process a debit before the credit funding it — which the fold would then silently
    # drop, leaving the consumed amount at zero and the invariant quietly broken.
    def order(row: LedgerEvent) -> tuple:
        grant_first = 0 if row.type == EventType.CREDIT_GRANTED.value else 1
        return (as_utc(row.occurred_at), grant_first, str(row.id))

    return sorted(query.all(), key=order)


# What each kind of outgoing event does to an entry.
_DRAWS: dict[str, str] = {
    EventType.DEBITED.value: "consumed_cents",
    EventType.EXPIRED.value: "expired_cents",
    EventType.ABANDONED.value: "abandoned_cents",
    # A compensating event takes credit back the same way a debit does; it is a correction of
    # something issued, not a use of it.
    EventType.CORRECTED.value: "abandoned_cents",
}


def credit_entries(
    db: Session, *, subject_id: uuid.UUID | None = None
) -> list[CreditEntry]:
    """Every gifted credit, with what became of it, in the order they were granted.

    Spending is attributed to the **oldest open credit first**. Somebody may hold two at
    once, and charging the wrong one would leave each entry's consumed amount wrong even
    while the total across them stayed right — which is exactly the error a per-campaign
    figure exists to catch.
    """
    per_subject: dict[uuid.UUID, list[CreditEntry]] = {}
    entries: list[CreditEntry] = []

    for row in _gifted(db, subject_id):
        if row.amount_cents is None:
            continue

        if row.type == EventType.CREDIT_GRANTED.value:
            granted_at = as_utc(row.occurred_at)
            entry = CreditEntry(
                subject_id=row.subject_id,
                credit_type=_type_of(row),
                issued_cents=row.amount_cents,
                issued_at=granted_at,
                expires_at=expires_at(granted_at),
                author=row.actor,
                operator_id=row.actor_id if row.actor == Actor.OPERATOR.value else None,
                reason=row.detail or "",
            )
            per_subject.setdefault(row.subject_id, []).append(entry)
            entries.append(entry)
            continue

        field_name = _DRAWS.get(row.type)
        if field_name is None:
            continue

        # Draw down the oldest credit that still has something in it.
        remaining = abs(row.amount_cents)
        for entry in per_subject.get(row.subject_id, []):
            if remaining <= 0:
                break
            taking = min(remaining, entry.remaining_cents)
            if taking <= 0:
                continue
            setattr(entry, field_name, getattr(entry, field_name) + taking)
            remaining -= taking

    return entries


@dataclass
class Totals:
    """One period, one credit type, three states kept apart."""

    issued_cents: int = 0
    consumed_cents: int = 0
    expired_cents: int = 0
    abandoned_cents: int = 0


def period_totals(
    db: Session, *, since: datetime, until: datetime
) -> dict[CreditType, Totals]:
    """What was issued, consumed, expired and abandoned in a period, by credit type.

    Every type appears, including the ones that issued nothing: a missing row reads as "none
    issued" when it means "the query found nothing", and those are different answers for
    somebody deciding whether a campaign ran at all.
    """
    totals = {credit_type: Totals() for credit_type in CreditType}

    for entry in credit_entries(db):
        if not since <= entry.issued_at <= until:
            continue
        row = totals[entry.credit_type]
        row.issued_cents += entry.issued_cents
        row.consumed_cents += entry.consumed_cents
        row.expired_cents += entry.expired_cents
        row.abandoned_cents += entry.abandoned_cents

    return totals


def acquisition_cost_cents(db: Session, *, subject_id: uuid.UUID | None = None) -> int:
    """What the gifted credits actually cost — the consumed part and nothing else.

    Only consumption bought provider time. Expired and abandoned credit never left, and
    counting either as spend would report an acquisition cost nobody paid.
    """
    return sum(entry.consumed_cents for entry in credit_entries(db, subject_id=subject_id))
