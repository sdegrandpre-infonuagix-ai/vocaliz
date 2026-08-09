"""Billing each participant for their own mode, prepaid (FR22 / FR42).

The inherited billing worked the other way round: one rate, charged to the host after the
Salon had ended. Two things change here, and the second is the one with teeth.

Each person pays their own tier, prorated to the second. Somebody on Base beside somebody on
Mode C are billed differently for the same conversation, which is the entire point of letting
them choose one.

And it is **prepaid**. Nobody is charged past what they put in and no debt is ever created —
when the balance runs out, the Salon ends instead. That is a deliberate trade rather than a
limitation: a system able to invoice past the balance would collect more, and would also mean
somebody could walk away from a conversation owing money they never agreed to spend.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from src.credit import TIER_RATES_CENTS_PER_HOUR, Tier, balance, debit
from src.models.ledger_event import LedgerEvent

SECONDS_PER_HOUR = 3600

# What the host pays per head when covering the room. The same tier a guest is placed in, so
# the price they are quoted is the price of what those guests actually get.
HOST_PAYS_TIER = Tier.MODE_B


def cost_cents(tier: Tier, seconds: int) -> int:
    """What `seconds` of this tier costs, prorated to the second and rounded **down**.

    To the second because that is the unit somebody consumes: billing a started minute as a
    whole one is how a two-minute conversation costs an hour. Down because a bill should
    never exceed the thing it is for — the rounding difference is small, and the principle
    is the part worth keeping.
    """
    return TIER_RATES_CENTS_PER_HOUR[tier] * seconds // SECONDS_PER_HOUR


def affordable_seconds(db: Session, subject_id: uuid.UUID, tier: Tier) -> int:
    """How long this balance lasts at this tier — the number somebody actually wants."""
    available = max(0, balance(db, subject_id).total_cents)
    return available * SECONDS_PER_HOUR // TIER_RATES_CENTS_PER_HOUR[tier]


@dataclass(frozen=True)
class Charge:
    """What was taken, and what could not be."""

    owed_cents: int
    charged_cents: int
    movements: list[LedgerEvent]

    @property
    def shortfall_cents(self) -> int:
        """What the balance could not cover. Reported, never owed."""
        return self.owed_cents - self.charged_cents

    @property
    def exhausted(self) -> bool:
        return self.shortfall_cents > 0

    @property
    def ends_salon(self) -> bool:
        """FR55. Ending is the honest outcome — the alternative is a conversation carrying
        on while it accrues something nobody authorised."""
        return self.exhausted


def charge_for(
    db: Session,
    subject_id: uuid.UUID,
    *,
    tier: Tier,
    seconds: int,
    now: datetime,
    heads: int = 1,
) -> Charge:
    """Charge somebody for time at a tier, capped at what they have.

    `heads` is how the host covering the room is billed: one charge at Mode B per person,
    taken from the host's balance while every guest's own balance stays untouched —
    otherwise "the host pays" would quietly mean "the host pays as well".

    The cap is the whole design. What the balance cannot cover is *reported* rather than
    owed, and the caller ends the Salon.
    """
    if heads < 0:
        raise ValueError(f"heads is {heads}: a Salon cannot have a negative number of people.")

    owed = cost_cents(tier, seconds) * heads
    available = max(0, balance(db, subject_id).total_cents)
    taking = min(owed, available)

    movements = debit(db, subject_id, cents=taking, now=now) if taking else []
    return Charge(owed_cents=owed, charged_cents=taking, movements=movements)


@dataclass(frozen=True)
class HostPaysQuote:
    """What covering the room costs per hour, and the confirmation it needs first."""

    participants: int
    cents_per_hour: int
    active: bool = False

    @property
    def requires_confirmation(self) -> bool:
        """Always. "The host pays" without a number is an option somebody agrees to without
        knowing what they agreed to."""
        return not self.active

    @property
    def confirmation_text(self) -> str:
        """The **maximum** hourly cost, stated in money.

        The maximum rather than an estimate: it is what the hour costs if everybody stays for
        all of it, and a lower guess that people then exceeded would be worse than useless.
        """
        return (
            f"With {self.participants} taking part, paying for everybody costs a maximum of "
            f"{self.cents_per_hour / 100:.2f} an hour. Everybody is placed in "
            f"{HOST_PAYS_TIER.label}, without advertising."
        )

    def confirmed(self) -> HostPaysQuote:
        """Turning it on, which only an explicit confirmation does."""
        return HostPaysQuote(
            participants=self.participants, cents_per_hour=self.cents_per_hour, active=True
        )


def host_pays_quote(*, participants: int) -> HostPaysQuote:
    """What the host would pay per hour to cover a room of this size."""
    return HostPaysQuote(
        participants=participants,
        cents_per_hour=TIER_RATES_CENTS_PER_HOUR[HOST_PAYS_TIER] * max(0, participants),
    )
