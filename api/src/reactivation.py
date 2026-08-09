"""Granting a second credit by hand, as an explicit exception to the registry (FR67).

The burned-identifier registry stops somebody collecting the welcome credit over and over. It
also, unavoidably, stops Vocaliz running its own reactivation campaign — a cost of the design
rather than a flaw in it. This is the exception, and the word is exact: the registry is never
expired, cleared or weakened. One grant is allowed *through* it and the registry is precisely
as it was afterwards.

Two things stop the exception becoming a back door. Ninety days must have passed since the
last gift, so nobody can be handed the credit repeatedly by asking. And every grant carries
its author, its reason and its amount into the ledger — issuing money without a trace is the
one thing an audit never forgives.

There is no screen and no route. Access to the production environment *is* the access
control, which means there is no administrator authentication to build and therefore none to
get wrong.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from src.coverage import TOP_UP_CEILING_CENTS
from src.credit import Grant, expires_at
from src.ledger import Actor, EventType, Pool, append, as_utc
from src.models.ledger_event import LedgerEvent

# Three dollars. Bringing somebody back is worth less than getting them to try in the first
# place, which is why this is smaller than the welcome credit rather than equal to it.
REACTIVATION_CREDIT_CENTS = 300

# How long since the last gift before another may be given. The number is what keeps this an
# exception rather than a second, slower way of collecting credits.
MIN_DAYS_BETWEEN_GIFTS = 90


def _last_gift_at(db: Session, subject_id: uuid.UUID) -> datetime | None:
    rows = (
        db.query(LedgerEvent)
        .filter(
            LedgerEvent.subject_id == subject_id,
            LedgerEvent.type == EventType.CREDIT_GRANTED.value,
        )
        .all()
    )
    return max((as_utc(row.occurred_at) for row in rows), default=None)


def grant_second_credit(
    db: Session,
    *,
    subject_id: uuid.UUID,
    reason: str,
    operator_id: uuid.UUID,
    amount_cents: int | None = None,
    now: datetime,
) -> Grant:
    """Give somebody another credit, despite the registry, provided enough time has passed.

    The credit lands in the gifted balance and inherits every rule the welcome credit has:
    not refundable, spent before paid money, and gone thirty days later.
    """
    if not reason.strip():
        raise ValueError(
            "a manual grant needs a reason. Issuing money with no stated purpose is the "
            "entry an audit stops at."
        )

    amount = REACTIVATION_CREDIT_CENTS if amount_cents is None else amount_cents
    if amount <= 0:
        raise ValueError(
            f"a grant of {amount} cents is not a grant. A journal entry saying money moved "
            "when it did not is worse than no entry at all."
        )
    if amount > TOP_UP_CEILING_CENTS:
        raise ValueError(
            f"a grant of {amount / 100:.2f} is above the ceiling of "
            f"{TOP_UP_CEILING_CENTS / 100:.2f}."
        )

    db.flush()
    last = _last_gift_at(db, subject_id)
    if last is not None and now - last < timedelta(days=MIN_DAYS_BETWEEN_GIFTS):
        waited = (now - last).days
        return Grant(
            subject_id=subject_id,
            granted_cents=0,
            expires_at=None,
            refused_because=(
                f"the last credit was {waited} days ago, and {MIN_DAYS_BETWEEN_GIFTS} days "
                "must pass between gifts. Waiting is what keeps this an exception rather "
                "than a second way of collecting credits."
            ),
        )

    append(
        db,
        type=EventType.CREDIT_GRANTED,
        subject_id=subject_id,
        amount_cents=amount,
        pool=Pool.GIFTED,
        occurred_at=now,
        actor=Actor.OPERATOR,
        actor_id=operator_id,
        detail=f"manual grant: {reason.strip()}",
    )
    return Grant(
        subject_id=subject_id, granted_cents=amount, expires_at=expires_at(now)
    )


def grant_to_cohort(
    db: Session,
    *,
    subject_ids: list[uuid.UUID],
    reason: str,
    operator_id: uuid.UUID,
    amount_cents: int | None = None,
    now: datetime,
) -> list[Grant]:
    """One operation, one journal entry *per beneficiary*.

    Never an aggregated cohort row: a single person's grant has to remain answerable on its
    own, and "two hundred people were given three dollars" answers nobody's question about
    themselves.

    One refusal does not stop the rest. A campaign of two hundred should not fail because one
    of them was given a credit last month.
    """
    return [
        grant_second_credit(
            db,
            subject_id=subject_id,
            reason=reason,
            operator_id=operator_id,
            amount_cents=amount_cents,
            now=now,
        )
        for subject_id in subject_ids
    ]


def confirmation_text(*, beneficiaries: int, amount_cents: int) -> str:
    """What the operator is shown before anything is written.

    The total and the head count, in money. Somebody about to issue currency should see how
    much and to how many *before* the fact, rather than discovering it from the ledger.
    """
    total = beneficiaries * amount_cents
    return (
        f"About to grant {amount_cents / 100:.2f} each to {beneficiaries} people — "
        f"{total / 100:.2f} in total. Nothing has been written yet."
    )
