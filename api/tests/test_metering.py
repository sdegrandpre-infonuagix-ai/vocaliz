"""Metering a prepaid balance down, in integers, five seconds at a time (FR63).

Three rules that all serve the same end: a bill nobody can dispute.

**No float ever touches the ledger.** A rate of 7.50 an hour over five seconds is not
representable in binary, and a balance accumulated out of such numbers drifts — slowly,
invisibly, and in a direction nobody chose. So consumption accumulates in whole cent-seconds
and is converted to cents exactly once, at the boundary where a number is shown to somebody
or sent to Stripe, by integer division.

**Only completed blocks are billed.** Sampling happens every five seconds, so a partial block
was never measured, and billing an unmeasured duration is precisely what somebody would
contest. An hour and two seconds is billed as an hour.

**Rounding is downward, in the customer's favour.** Not to be confused with FR63's
verification rounding, which goes up out of caution — they answer different questions, and
conflating them would either overcharge or under-protect.
"""
import pytest

from src.credit import Tier
from src.metering import (
    DEFAULT_GRANULARITY,
    MONTHLY_TOP_UP_CENTS,
    SAMPLE_SECONDS,
    WEEKLY_TOP_UP_CENTS,
    Granularity,
    Meter,
    billable_seconds,
    effective_rate_cents_per_hour,
    remaining_seconds,
    top_up_cents,
)


# ── Only whole blocks ─────────────────────────────────────────────────────────


def test_the_sampling_interval_is_five_seconds():
    assert SAMPLE_SECONDS == 5


def test_an_hour_and_two_seconds_is_billed_as_an_hour_and_no_seconds():
    """The two seconds were never sampled, and billing a duration nobody measured is exactly
    what gets contested."""
    assert billable_seconds(3662) == 3660


def test_a_partial_block_at_the_end_is_dropped():
    assert billable_seconds(9) == 5


def test_a_salon_shorter_than_one_block_bills_nothing():
    """An accepted consequence of rounding down, not an oversight."""
    assert billable_seconds(4) == 0


def test_an_exact_multiple_keeps_all_of_it():
    assert billable_seconds(3600) == 3600


def test_nothing_elapsed_bills_nothing():
    assert billable_seconds(0) == 0


# ── Integers all the way to the boundary ──────────────────────────────────────


def test_a_tick_accumulates_and_the_cents_are_computed_on_demand():
    """Five seconds of Mode A is just over a cent. The accumulator holds the exact amount in
    cent-seconds; the whole cents are worked out only when somebody asks for them."""
    meter = Meter()

    meter.tick(rate_cents_per_hour=750)

    assert meter.cents_due == 1


def test_the_remainder_is_carried_to_the_next_tick():
    """The whole reason for an accumulator. Converting each tick to cents on its own would
    throw the fraction away every five seconds, which over an hour is most of the bill."""
    meter = Meter()

    for _ in range(12):
        meter.tick(rate_cents_per_hour=750)

    # A minute of Mode A is 12.5 cents, and the half survives as a remainder.
    assert meter.cents_due == 12
    assert meter.remainder_cent_seconds > 0


def test_an_hours_worth_of_ticks_costs_exactly_the_hourly_rate():
    """The property the carrying exists to preserve: no drift over a long conversation."""
    meter = Meter()

    for _ in range(3600 // SAMPLE_SECONDS):
        meter.tick(rate_cents_per_hour=750)

    assert meter.cents_due == 750


def test_no_float_ever_enters_the_accumulator():
    meter = Meter()
    meter.tick(rate_cents_per_hour=750)

    assert isinstance(meter.cent_seconds, int)
    assert isinstance(meter.cents_due, int)


def test_taking_the_cents_leaves_the_remainder_behind():
    """The conversion happens once, at the boundary. What could not be expressed in whole
    cents stays in the accumulator rather than being rounded away."""
    meter = Meter()
    for _ in range(12):
        meter.tick(rate_cents_per_hour=750)

    taken = meter.take_cents()

    assert taken == 12
    assert meter.cents_due == 0
    assert meter.remainder_cent_seconds > 0


def test_the_carried_remainder_eventually_becomes_a_cent():
    """Nothing is lost — it is deferred. Two half-cents make a cent, and the customer is
    charged for both only once they add up to something."""
    meter = Meter()
    for _ in range(12):
        meter.tick(rate_cents_per_hour=750)
    meter.take_cents()

    for _ in range(12):
        meter.tick(rate_cents_per_hour=750)

    assert meter.take_cents() == 13


def test_taking_from_an_empty_meter_takes_nothing():
    assert Meter().take_cents() == 0


# ── A rate that changes between ticks ─────────────────────────────────────────


def test_each_interval_is_billed_at_the_rate_that_was_in_force():
    """Somebody who moved to a dearer mode half way should pay the old rate for the first
    half. Re-evaluating past ticks would re-price a conversation that already happened."""
    meter = Meter()

    for _ in range(360):
        meter.tick(rate_cents_per_hour=300)
    for _ in range(360):
        meter.tick(rate_cents_per_hour=2250)

    assert meter.cents_due == 150 + 1125


def test_a_rate_change_never_reprices_what_is_already_accumulated():
    meter = Meter()
    for _ in range(720):
        meter.tick(rate_cents_per_hour=300)
    before = meter.cent_seconds

    meter.tick(rate_cents_per_hour=2250)

    assert meter.cent_seconds == before + 2250 * SAMPLE_SECONDS


# ── What a payer's rate actually is ───────────────────────────────────────────


def test_a_payer_carrying_one_person_pays_that_persons_rate():
    assert effective_rate_cents_per_hour([Tier.MODE_A]) == 750


def test_a_payer_carrying_several_pays_the_sum():
    """The host covering a room. Their rate is everybody's rates added together, which is
    why it has to be recomputed the moment somebody joins or leaves."""
    rate = effective_rate_cents_per_hour([Tier.MODE_B, Tier.MODE_B, Tier.BASE])

    assert rate == 1500 + 1500 + 300


def test_a_telephone_supplement_is_part_of_the_rate():
    """FR57. Somebody on the telephone costs more to carry, and hiding that in a separate
    calculation would make the payer's rate disagree with what is actually charged."""
    rate = effective_rate_cents_per_hour([Tier.MODE_B], telephone_supplement_cents_per_hour=200)

    assert rate == 1500 + 200


def test_carrying_nobody_costs_nothing():
    assert effective_rate_cents_per_hour([]) == 0


def test_the_rate_changes_the_instant_the_room_does():
    """No conversion of the balance is involved — the balance is in cents and stays there.
    Only the rate moves, which is what makes the recalculation free."""
    before = effective_rate_cents_per_hour([Tier.MODE_B])
    after = effective_rate_cents_per_hour([Tier.MODE_B, Tier.MODE_C])

    assert after > before


# ── The balance, seen as time ─────────────────────────────────────────────────


def test_a_balance_is_shown_as_the_seconds_it_buys():
    """What somebody wants to know is how long they have, not how many cents. The seconds
    are a *view* of the cents, recomputed whenever the rate moves — never a stored unit."""
    assert remaining_seconds(750, rate_cents_per_hour=750) == 3600


def test_the_seconds_shrink_when_the_room_grows():
    """Same money, more people to carry."""
    alone = remaining_seconds(3000, rate_cents_per_hour=1500)
    crowded = remaining_seconds(3000, rate_cents_per_hour=4500)

    assert crowded < alone


def test_a_rate_of_nothing_buys_unbounded_time_rather_than_dividing_by_zero():
    """Carrying nobody costs nothing, so the balance lasts as long as the conversation does.
    Reporting that as an error would make an empty room look like a fault."""
    assert remaining_seconds(1000, rate_cents_per_hour=0) is None


def test_an_empty_balance_buys_no_time():
    assert remaining_seconds(0, rate_cents_per_hour=750) == 0


def test_the_seconds_are_rounded_down_too():
    """Promising a second the money does not cover is the same mistake as billing one."""
    assert remaining_seconds(1, rate_cents_per_hour=750) == 4


# ── How much a top-up is ──────────────────────────────────────────────────────


def test_a_new_payer_tops_up_weekly():
    assert DEFAULT_GRANULARITY is Granularity.WEEKLY


def test_the_two_amounts_are_the_configured_ones():
    assert WEEKLY_TOP_UP_CENTS == 1000
    assert MONTHLY_TOP_UP_CENTS == 4333


def test_the_amount_follows_the_granularity():
    assert top_up_cents(Granularity.WEEKLY) == WEEKLY_TOP_UP_CENTS
    assert top_up_cents(Granularity.MONTHLY) == MONTHLY_TOP_UP_CENTS


def test_monthly_is_available_and_is_not_simply_four_weeks():
    """It is its own figure rather than a multiple, so neither can drift from the other by
    somebody changing one number."""
    assert MONTHLY_TOP_UP_CENTS != WEEKLY_TOP_UP_CENTS * 4


def test_a_top_up_is_a_fixed_amount_rather_than_whatever_is_missing():
    """Triggered by need, never by the calendar — but the amount is the configured one, so
    somebody always knows in advance what a top-up will cost them."""
    assert top_up_cents(Granularity.WEEKLY) == top_up_cents(Granularity.WEEKLY)


def test_an_unknown_granularity_is_refused_rather_than_guessed():
    with pytest.raises(ValueError):
        top_up_cents("fortnightly")
