"""The five-second tick: debit what elapsed, then judge whether the next block is covered.

One event does both, and the order is the whole point — **debit, then verify**. Verifying
first would promise a block that the debit about to happen makes impossible, which is the one
way this check can be wrong while looking right.

The two roundings in this system go in opposite directions on purpose. Billing rounds *down*,
in the customer's favour (`billing.cost_cents`). This check rounds *up*, out of caution: a
block that might not be covered is never allowed to start. Five seconds of Base is four
tenths of a cent and the check asks for a whole one — a fraction of a cent is not something a
balance can hold, so the conservative direction is the only coherent one.

And the debit is always for time that *actually elapsed*. At this cadence scheduling jitter
is not negligible, and charging a nominal five seconds when eight went by would bill for a
duration nobody measured.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import ceil

from src.metering import (
    SAMPLE_SECONDS,
    SECONDS_PER_HOUR,
    Granularity,
    remaining_seconds,
    top_up_cents,
)

# Under this much coverage, the payer is warned and one top-up is asked for. Three minutes is
# enough to ask a question, hear an answer and take a payment without anybody noticing.
ALERT_COVERAGE_SECONDS = 180

# How long a Salon may go unheard-from before consumption stops. A balance never decrements
# on a Salon nobody has heard from — charging on into silence bills for something we cannot
# say happened.
SILENT_WORKER_SECONDS = 60

# The most a top-up may be set to. Five hundred dollars.
TOP_UP_CEILING_CENTS = 50_000


def block_cost_cents(*, rate_cents_per_hour: int) -> int:
    """What one sampling block costs, **rounded up** to the cent.

    Up, always. Letting a block start on a fraction of a cent nobody has is precisely the
    situation this exists to prevent, and the cost of being wrong in the other direction is a
    conversation cut off owing money.
    """
    if rate_cents_per_hour <= 0:
        return 0
    return ceil(rate_cents_per_hour * SAMPLE_SECONDS / SECONDS_PER_HOUR)


@dataclass(frozen=True)
class Coverage:
    """What one tick did, and what should happen next."""

    charged_cents: int
    balance_after_cents: int
    covers_next_block: bool
    alert: bool
    request_top_up: bool
    ends_salon: bool
    stale: bool


def check_coverage(
    *,
    balance_cents: int,
    rate_cents_per_hour: int,
    elapsed_seconds: int,
    top_up_pending: bool = False,
    already_alerted: bool = False,
    since_last_signal_seconds: int = 0,
) -> Coverage:
    """Debit the elapsed time, then decide whether the next block can be allowed to start.

    Judged per *payer* rather than per participant: a host covering three people is evaluated
    once, on the aggregate rate, because the coverage required is everybody's and not their
    own tier's.
    """
    if since_last_signal_seconds > SILENT_WORKER_SECONDS:
        # Silence is a different problem from an empty balance, and treating it as one would
        # blame a network failure on somebody's budget. Nothing is charged and nothing ends.
        return Coverage(
            charged_cents=0,
            balance_after_cents=balance_cents,
            covers_next_block=True,
            alert=False,
            request_top_up=False,
            ends_salon=False,
            stale=True,
        )

    # Debit first — on what elapsed, never on the nominal cadence.
    owed = rate_cents_per_hour * max(0, elapsed_seconds) // SECONDS_PER_HOUR
    charged = min(owed, max(0, balance_cents))
    after = max(0, balance_cents - charged)

    # Then verify, against what is left.
    covers = after >= block_cost_cents(rate_cents_per_hour=rate_cents_per_hour)

    left = remaining_seconds(after, rate_cents_per_hour=rate_cents_per_hour)
    running_low = covers and left is not None and left < ALERT_COVERAGE_SECONDS

    return Coverage(
        charged_cents=charged,
        balance_after_cents=after,
        covers_next_block=covers,
        # Once, not on every tick. Somebody asked twelve times a minute stops hearing it.
        alert=running_low and not already_alerted,
        request_top_up=running_low and not top_up_pending,
        ends_salon=not covers,
        stale=False,
    )


def validate_top_up_cents(amount_cents: int, granularity: Granularity) -> int:
    """Check a chosen top-up against its floor and the ceiling.

    Refused explicitly, never silently pulled back into range: somebody who asked for 3.00 and
    was quietly given 10.00 has been charged something they did not agree to, and will find
    out from their statement rather than from us.
    """
    floor = top_up_cents(granularity)
    if amount_cents < floor:
        raise ValueError(
            f"a top-up of {amount_cents / 100:.2f} is below the {granularity.value} minimum "
            f"of {floor / 100:.2f}. Choose at least the minimum, or switch granularity."
        )
    if amount_cents > TOP_UP_CEILING_CENTS:
        raise ValueError(
            f"a top-up of {amount_cents / 100:.2f} is above the maximum of "
            f"{TOP_UP_CEILING_CENTS / 100:.2f}."
        )
    return amount_cents
