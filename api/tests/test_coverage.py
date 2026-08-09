"""The five-second tick that debits, then checks whether the next block is covered (FR56).

One event does both, and the order is the whole point: **debit, then verify**. Verifying
first would promise a block that the debit about to happen makes impossible.

The two roundings in this system go in opposite directions, deliberately. Billing rounds
*down*, in the customer's favour — Story 8.7. This check rounds *up*, out of caution: a block
that might not be covered is never allowed to start. Five seconds of Base is four tenths of a
cent, and the check asks for a whole one, because a fraction of a cent is not something a
balance can hold.

And the debit is for time that actually elapsed. At this cadence scheduling jitter is not
negligible, and charging the nominal five seconds when eight went by would quietly bill for a
duration nobody measured — the same mistake `billable_seconds` exists to avoid.
"""
import pytest

from src.coverage import (
    ALERT_COVERAGE_SECONDS,
    SILENT_WORKER_SECONDS,
    TOP_UP_CEILING_CENTS,
    block_cost_cents,
    check_coverage,
    validate_top_up_cents,
)
from src.metering import SAMPLE_SECONDS, Granularity, WEEKLY_TOP_UP_CENTS


# ── The verification rounds up ────────────────────────────────────────────────


def test_a_block_costs_at_least_a_cent_at_any_rate():
    """Rounded up, always. Letting a block start on a fraction of a cent nobody has is
    exactly the situation this check exists to prevent."""
    assert block_cost_cents(rate_cents_per_hour=300) == 1


def test_the_check_never_demands_less_than_the_billing_will_take():
    """The property that makes rounding up the right direction: whatever the tick ends up
    charging, the check insisted on at least that much being there first. The reverse would
    let a block start that the debit cannot cover."""
    from src.billing import cost_cents
    from src.credit import TIER_RATES_CENTS_PER_HOUR, Tier

    for tier in Tier:
        rate = TIER_RATES_CENTS_PER_HOUR[tier]
        assert block_cost_cents(rate_cents_per_hour=rate) >= cost_cents(tier, SAMPLE_SECONDS)


def test_the_cheapest_tiers_are_rounded_up_to_a_whole_cent():
    """Five seconds of Base is four tenths of a cent. A check working in whole cents has to
    ask for one, because a fraction of a cent is not something a balance can hold."""
    assert block_cost_cents(rate_cents_per_hour=300) == 1


def test_a_dearer_rate_eventually_demands_more():
    assert block_cost_cents(rate_cents_per_hour=100_000) > block_cost_cents(
        rate_cents_per_hour=300
    )


def test_the_two_roundings_go_opposite_ways():
    """Billing rounds down in the customer's favour; this rounds up out of caution. They
    answer different questions, and making them agree would either overcharge or let a block
    start that nothing covers."""
    from src.billing import cost_cents
    from src.credit import Tier

    assert cost_cents(Tier.BASE, SAMPLE_SECONDS) == 0
    assert block_cost_cents(rate_cents_per_hour=300) == 1


def test_carrying_nobody_demands_nothing():
    assert block_cost_cents(rate_cents_per_hour=0) == 0


# ── Debit first, then verify ──────────────────────────────────────────────────


def test_the_elapsed_time_is_debited_before_coverage_is_judged():
    """Verifying first would promise a block that the debit about to happen makes
    impossible."""
    outcome = check_coverage(
        balance_cents=1, rate_cents_per_hour=300, elapsed_seconds=SAMPLE_SECONDS
    )

    assert outcome.charged_cents >= 0
    assert outcome.balance_after_cents == 1 - outcome.charged_cents


def test_a_balance_that_covers_the_next_block_carries_on():
    outcome = check_coverage(
        balance_cents=5000, rate_cents_per_hour=1500, elapsed_seconds=SAMPLE_SECONDS
    )

    assert outcome.covers_next_block is True
    assert outcome.ends_salon is False


def test_a_balance_that_cannot_cover_the_next_block_ends_the_salon():
    """Never letting a balance start a block it does not cover is the rule; ending is what
    happens when it cannot."""
    outcome = check_coverage(
        balance_cents=0, rate_cents_per_hour=1500, elapsed_seconds=SAMPLE_SECONDS
    )

    assert outcome.covers_next_block is False
    assert outcome.ends_salon is True


def test_the_debit_is_what_can_tip_it_over():
    """A balance covering the next block *before* the debit and not after must end. This is
    the case that ordering the two operations wrongly would get wrong."""
    outcome = check_coverage(
        balance_cents=1, rate_cents_per_hour=1500, elapsed_seconds=3600
    )

    assert outcome.ends_salon is True


# ── Jitter ────────────────────────────────────────────────────────────────────


def test_a_late_tick_debits_the_time_that_actually_passed():
    """Not the nominal cadence. At five seconds, scheduling jitter is not negligible, and
    billing five when eight went by charges for a duration nobody measured."""
    prompt = check_coverage(balance_cents=100_000, rate_cents_per_hour=360_000, elapsed_seconds=5)
    late = check_coverage(balance_cents=100_000, rate_cents_per_hour=360_000, elapsed_seconds=10)

    assert late.charged_cents > prompt.charged_cents


def test_a_tick_that_arrives_early_charges_less():
    early = check_coverage(balance_cents=100_000, rate_cents_per_hour=360_000, elapsed_seconds=2)
    prompt = check_coverage(balance_cents=100_000, rate_cents_per_hour=360_000, elapsed_seconds=5)

    assert early.charged_cents < prompt.charged_cents


# ── One payer, whatever they carry ────────────────────────────────────────────


def test_a_payer_is_judged_on_the_rate_they_actually_carry():
    """A host covering three people is evaluated once, on the aggregate — the coverage
    required is everybody's, not their own tier's."""
    alone = check_coverage(balance_cents=200, rate_cents_per_hour=1500, elapsed_seconds=5)
    carrying = check_coverage(balance_cents=200, rate_cents_per_hour=4500, elapsed_seconds=5)

    assert carrying.balance_after_cents <= alone.balance_after_cents


# ── The alert, and exactly one top-up request ─────────────────────────────────


def test_the_alert_threshold_is_three_minutes_of_coverage():
    assert ALERT_COVERAGE_SECONDS == 180


def test_dropping_under_the_threshold_raises_the_alert():
    # 1500/hour is 25 cents a minute, so three minutes is 75 cents.
    outcome = check_coverage(balance_cents=70, rate_cents_per_hour=1500, elapsed_seconds=5)

    assert outcome.alert is True


def test_a_comfortable_balance_raises_nothing():
    outcome = check_coverage(balance_cents=5000, rate_cents_per_hour=1500, elapsed_seconds=5)

    assert outcome.alert is False
    assert outcome.request_top_up is False


def test_the_alert_asks_for_exactly_one_top_up():
    outcome = check_coverage(balance_cents=70, rate_cents_per_hour=1500, elapsed_seconds=5)

    assert outcome.request_top_up is True


def test_a_top_up_already_awaiting_an_answer_is_not_asked_for_again():
    """A periodic mechanism must not produce a request every five seconds. Somebody being
    asked twelve times a minute would stop hearing the question."""
    outcome = check_coverage(
        balance_cents=70, rate_cents_per_hour=1500, elapsed_seconds=5, top_up_pending=True
    )

    assert outcome.request_top_up is False


def test_an_alert_already_given_is_not_repeated_every_tick():
    outcome = check_coverage(
        balance_cents=70, rate_cents_per_hour=1500, elapsed_seconds=5, already_alerted=True
    )

    assert outcome.alert is False


def test_the_conversation_carries_on_while_the_top_up_is_pending():
    """The balance is not exhausted yet — that is precisely what the early alert buys. No
    mode changes and nothing is interrupted."""
    outcome = check_coverage(balance_cents=70, rate_cents_per_hour=1500, elapsed_seconds=5)

    assert outcome.ends_salon is False
    assert outcome.covers_next_block is True


# ── A worker that has gone quiet ──────────────────────────────────────────────


def test_a_minute_without_a_signal_stops_the_consumption():
    """A balance never decrements on a Salon nobody has heard from. Charging on into silence
    is billing for something we cannot say happened."""
    assert SILENT_WORKER_SECONDS == 60

    outcome = check_coverage(
        balance_cents=5000,
        rate_cents_per_hour=1500,
        elapsed_seconds=5,
        since_last_signal_seconds=61,
    )

    assert outcome.stale is True
    assert outcome.charged_cents == 0


def test_a_stale_salon_is_not_ended_by_the_coverage_check():
    """Silence is a different problem from an empty balance, and conflating them would blame
    a network failure on somebody's budget."""
    outcome = check_coverage(
        balance_cents=0,
        rate_cents_per_hour=1500,
        elapsed_seconds=5,
        since_last_signal_seconds=61,
    )

    assert outcome.stale is True
    assert outcome.ends_salon is False


def test_a_recent_signal_consumes_normally():
    outcome = check_coverage(
        balance_cents=5000,
        rate_cents_per_hour=1500,
        elapsed_seconds=5,
        since_last_signal_seconds=30,
    )

    assert outcome.stale is False
    assert outcome.charged_cents > 0


# ── The top-up amount somebody chooses ────────────────────────────────────────


def test_the_ceiling_is_five_hundred_dollars():
    assert TOP_UP_CEILING_CENTS == 50_000


def test_an_amount_above_the_floor_is_accepted():
    """Somebody covering a room needs a larger top-up than the weekly floor, and raising it
    is theirs to do."""
    assert validate_top_up_cents(5000, Granularity.WEEKLY) == 5000


def test_the_floor_itself_is_accepted():
    assert validate_top_up_cents(WEEKLY_TOP_UP_CENTS, Granularity.WEEKLY) == WEEKLY_TOP_UP_CENTS


def test_below_the_floor_is_refused_explicitly():
    """Never silently pulled back into range. Somebody who asked for 3.00 and was given 10.00
    without being told has been charged something they did not agree to."""
    with pytest.raises(ValueError) as raised:
        validate_top_up_cents(300, Granularity.WEEKLY)

    assert "300" in str(raised.value) or "3.00" in str(raised.value)


def test_above_the_ceiling_is_refused_explicitly():
    with pytest.raises(ValueError) as raised:
        validate_top_up_cents(60_000, Granularity.WEEKLY)

    assert "500" in str(raised.value)


def test_the_ceiling_itself_is_accepted():
    assert validate_top_up_cents(TOP_UP_CEILING_CENTS, Granularity.WEEKLY) == TOP_UP_CEILING_CENTS


def test_the_monthly_floor_is_higher_than_the_weekly_one():
    """So an amount valid weekly can be refused monthly, which is why the granularity is
    part of the question."""
    with pytest.raises(ValueError):
        validate_top_up_cents(WEEKLY_TOP_UP_CENTS, Granularity.MONTHLY)
