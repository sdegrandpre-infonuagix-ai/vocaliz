"""Metering a prepaid balance down, in integers, five seconds at a time (FR63).

Three rules, all serving the same end: a bill nobody can dispute.

**No float ever touches the ledger.** A rate of 7.50 an hour over five seconds is not
representable in binary, and a balance accumulated out of such numbers drifts — slowly,
invisibly, and in a direction nobody chose. Consumption therefore accumulates in whole
*cent-seconds* (rate per hour × seconds) and becomes cents exactly once, at the boundary
where a number is shown to somebody or sent to Stripe, by integer division.

**Only completed blocks are billed.** Sampling happens every five seconds, so a partial block
was never measured — and billing an unmeasured duration is precisely the thing somebody would
contest. An hour and two seconds is billed as an hour.

**Rounding is downward, in the customer's favour.** Deliberately not the same as the
verification rounding in FR63, which goes *up* out of caution: one asks "what do we charge?"
and the other asks "what might we need?", and conflating them would either overcharge or
under-protect.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable

from src.credit import TIER_RATES_CENTS_PER_HOUR, Tier

SECONDS_PER_HOUR = 3600

# How often consumption is sampled. Nothing shorter than this is ever measured, and so
# nothing shorter than this is ever charged.
SAMPLE_SECONDS = 5


def billable_seconds(elapsed_seconds: int) -> int:
    """The part of an elapsed duration that was actually sampled.

    Whole blocks only. A block that was started and not finished was never measured, and
    charging for it would mean charging for a number nobody can show the working of.
    """
    return elapsed_seconds // SAMPLE_SECONDS * SAMPLE_SECONDS


@dataclass
class Meter:
    """Consumption accumulating in cent-seconds, converted to cents only at the boundary.

    The carried remainder is the point. Converting each tick to cents on its own would throw
    away the fraction every five seconds — over an hour of Mode A that is most of the bill,
    lost a fraction at a time in the customer's favour, which is still wrong.
    """

    cent_seconds: int = field(default=0)

    def tick(self, *, rate_cents_per_hour: int, seconds: int = SAMPLE_SECONDS) -> None:
        """Charge one interval at the rate in force *during* it.

        Nothing already accumulated is ever re-evaluated. Somebody who moved to a dearer
        mode half way pays the old rate for the first half, because re-pricing past ticks
        would re-price a conversation that has already happened.
        """
        self.cent_seconds += rate_cents_per_hour * seconds

    @property
    def cents_due(self) -> int:
        """What has accumulated, in whole cents. The one place division happens."""
        return self.cent_seconds // SECONDS_PER_HOUR

    @property
    def remainder_cent_seconds(self) -> int:
        """What has accumulated but does not yet amount to a cent."""
        return self.cent_seconds % SECONDS_PER_HOUR

    def take_cents(self) -> int:
        """Hand over the whole cents and keep the remainder.

        Nothing is lost — it is deferred. Two half-cents make a cent, and somebody is charged
        for both only once they add up to something chargeable.
        """
        taking = self.cents_due
        self.cent_seconds -= taking * SECONDS_PER_HOUR
        return taking


def effective_rate_cents_per_hour(
    tiers: Iterable[Tier], *, telephone_supplement_cents_per_hour: int = 0
) -> int:
    """What a payer is consuming per hour, across everybody they are carrying.

    The sum, including any telephone supplement (FR57): somebody on the telephone costs more
    to carry, and computing that elsewhere would let the payer's stated rate disagree with
    what they are actually charged.

    Recomputed the instant somebody joins, leaves or changes tier — which is free, because
    the balance is in cents and stays in cents. Only the rate moves.
    """
    return (
        sum(TIER_RATES_CENTS_PER_HOUR[tier] for tier in tiers)
        + telephone_supplement_cents_per_hour
    )


def remaining_seconds(balance_cents: int, *, rate_cents_per_hour: int) -> int | None:
    """How long a balance lasts at the current rate.

    A *view* of the cents, recomputed whenever the rate moves — never a stored unit. What
    somebody wants to know is how long they have, and storing it would mean a second number
    that has to be kept in step with the first.

    `None` when nothing is being consumed: carrying nobody costs nothing, so the balance
    lasts as long as the conversation does. Reporting that as an error would make an empty
    room look like a fault.
    """
    if rate_cents_per_hour <= 0:
        return None
    return max(0, balance_cents) * SECONDS_PER_HOUR // rate_cents_per_hour


class Granularity(Enum):
    """How often a payer expects to top up. Weekly unless they say otherwise."""

    WEEKLY = "weekly"
    MONTHLY = "monthly"


DEFAULT_GRANULARITY = Granularity.WEEKLY

# Written out rather than derived from one another, so neither can drift when somebody
# adjusts the other. A month is not four weeks and the figures say so.
WEEKLY_TOP_UP_CENTS = 1000
MONTHLY_TOP_UP_CENTS = 4333

_AMOUNTS = {
    Granularity.WEEKLY: WEEKLY_TOP_UP_CENTS,
    Granularity.MONTHLY: MONTHLY_TOP_UP_CENTS,
}


def top_up_cents(granularity: Granularity) -> int:
    """What one top-up costs.

    A fixed amount rather than whatever happens to be missing, so somebody always knows in
    advance what agreeing will cost them. The top-up is triggered by *need* — a balance that
    has run low — and never by the calendar.
    """
    try:
        return _AMOUNTS[granularity]
    except (KeyError, TypeError):
        raise ValueError(
            f"unknown top-up granularity {granularity!r}. It is "
            f"{Granularity.WEEKLY.value} or {Granularity.MONTHLY.value}."
        ) from None
