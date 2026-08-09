"""Paying more balance for a top-up taken outside the app stores (FR70).

The reasoning is arithmetic before it is strategy. A store takes between 5 % and 30 % of every
purchase made through it; a browser payment avoids that entirely. Handing part of the saving
back to the payer costs Vocaliz nothing it was going to keep, and moves people to the cheaper
channel by making it the better one for them too.

Five per cent is chosen because it is covered in *every* combination, including the least
favourable — Android in the United States under a million dollars of revenue, where only 5 %
is avoided. A rebate that worked on average and lost money in the worst case would be a
promotion that punished success.

Two things follow. The rate has to be adjustable per platform, region and revenue bracket
without a deploy, because the commissions themselves change — the litigation is not settled
until 2027 and crossing a million dollars doubles them overnight. And the extra balance is
never an *encaissement*: Stripe took one amount and the payer received a larger one, so the
difference is a commercial charge and the paid-balance journal has to say so.
"""
import uuid
from datetime import datetime, timezone

import pytest

from src.ledger import EventType, Pool, append
from src.paid_journal import paid_totals
from src.rebate import (
    WEB_REBATE_RATE,
    Platform,
    RebatePolicy,
    credited_cents,
    rebate_cents,
    store_commission_rate,
)

PERSON = uuid.uuid4()
NOW = datetime(2026, 3, 1, tzinfo=timezone.utc)
LATER = datetime(2026, 12, 31, tzinfo=timezone.utc)


# ── More balance for the same money ───────────────────────────────────────────


def test_the_web_rebate_is_five_per_cent():
    assert WEB_REBATE_RATE == 0.05


def test_a_browser_top_up_credits_more_than_it_collects():
    """The same debit, more balance. That is the whole offer."""
    assert credited_cents(1000, platform=Platform.WEB) == 1050


def test_the_rebate_is_the_difference():
    assert rebate_cents(1000, platform=Platform.WEB) == 50


def test_a_top_up_in_the_app_gets_nothing_extra():
    """There is no commission avoided, so there is nothing to hand back."""
    assert credited_cents(1000, platform=Platform.IOS) == 1000
    assert rebate_cents(1000, platform=Platform.ANDROID) == 0


def test_the_rebate_rounds_down_rather_than_up():
    """A rebate is a gift, and rounding a gift up costs money nobody decided to spend."""
    assert rebate_cents(999, platform=Platform.WEB) == 49


def test_nothing_paid_earns_nothing():
    assert rebate_cents(0, platform=Platform.WEB) == 0


# ── Covered in every combination, including the worst ─────────────────────────


def test_the_worst_case_is_android_in_the_united_states_under_a_million():
    """Five per cent avoided — the least a store ever takes, and the number the rebate has
    to survive."""
    rate = store_commission_rate(
        platform=Platform.ANDROID, region="US", annual_revenue_cents=50_000_00
    )

    assert rate == 0.05


def test_the_best_case_is_ios_outside_the_united_states_above_a_million():
    rate = store_commission_rate(
        platform=Platform.IOS, region="FR", annual_revenue_cents=2_000_000_00
    )

    assert rate == 0.30


def test_crossing_a_million_doubles_the_commission():
    """Which is why the rebate has to be raisable without a deploy: the gap between store and
    browser goes from 15 points to 30 overnight, and the web channel stops being an
    optimisation and becomes an economic necessity."""
    small = store_commission_rate(
        platform=Platform.IOS, region="FR", annual_revenue_cents=999_999_00
    )
    large = store_commission_rate(
        platform=Platform.IOS, region="FR", annual_revenue_cents=1_000_001_00
    )

    assert large > small


def test_five_per_cent_is_covered_everywhere():
    """The property that makes the default safe: in no combination does the rebate exceed
    what the browser actually saved."""
    for platform in (Platform.IOS, Platform.ANDROID):
        for region in ("US", "FR"):
            for revenue in (50_000_00, 2_000_000_00):
                avoided = store_commission_rate(
                    platform=platform, region=region, annual_revenue_cents=revenue
                )
                assert WEB_REBATE_RATE <= avoided


def test_the_web_channel_avoids_no_commission_of_its_own():
    assert store_commission_rate(
        platform=Platform.WEB, region="US", annual_revenue_cents=0
    ) == 0.0


# ── A rate that can move without a deploy ─────────────────────────────────────


def test_a_policy_can_raise_the_rate_per_platform_and_region():
    """FR54. The commissions themselves are in litigation until 2027, so the answer has to
    be a configuration change rather than a release."""
    policy = RebatePolicy(rates={(Platform.WEB, "FR"): 0.15})

    assert policy.rate_for(platform=Platform.WEB, region="FR") == 0.15


def test_an_unconfigured_combination_falls_back_to_the_default():
    policy = RebatePolicy(rates={(Platform.WEB, "FR"): 0.15})

    assert policy.rate_for(platform=Platform.WEB, region="US") == WEB_REBATE_RATE


def test_the_app_stays_at_nothing_whatever_the_policy_says_about_the_web():
    policy = RebatePolicy(rates={(Platform.WEB, "FR"): 0.15})

    assert policy.rate_for(platform=Platform.IOS, region="FR") == 0.0


def test_a_rebate_above_what_was_avoided_is_accepted_but_flagged():
    """An acquisition decision, not an error — but not one to be taken inadvertently either.
    Accepting silently would let somebody spend money by typing a number."""
    policy = RebatePolicy(rates={(Platform.WEB, "US"): 0.20})

    warnings = policy.warnings(region="US", annual_revenue_cents=50_000_00)

    assert warnings != []
    assert "20" in warnings[0]


def test_a_rebate_within_the_commission_is_not_flagged():
    policy = RebatePolicy()

    assert policy.warnings(region="US", annual_revenue_cents=50_000_00) == []


def test_a_flagged_policy_still_applies():
    """Flagged is not refused. Somebody may well decide a 20 % rebate is worth it."""
    policy = RebatePolicy(rates={(Platform.WEB, "US"): 0.20})

    assert policy.rate_for(platform=Platform.WEB, region="US") == 0.20


# ── What the payer is told ────────────────────────────────────────────────────


def test_the_difference_is_stated_explicitly():
    """A rebate nobody knows about steers nobody. If it is not on the screen it is simply a
    cost Vocaliz absorbed for no behavioural change at all."""
    from src.rebate import channel_offer_text

    text = channel_offer_text(1000, platform=Platform.WEB)

    assert "10.50" in text
    assert "10.00" in text


def test_the_app_offer_says_what_it_is_without_pretending(db=None):
    from src.rebate import channel_offer_text

    text = channel_offer_text(1000, platform=Platform.IOS)

    assert "10.00" in text
    assert "10.50" not in text


# ── The journal keeps the two apart ───────────────────────────────────────────


def test_what_stripe_took_is_what_is_collected(db):
    """The rebate is not an encaissement. Stripe took ten dollars and the payer received
    ten-fifty; counting the difference as collected would report revenue nobody paid."""
    append(
        db,
        type=EventType.RECHARGED,
        subject_id=PERSON,
        amount_cents=1000,
        pool=Pool.PAID,
        occurred_at=NOW,
    )
    append(
        db,
        type=EventType.REBATE_GRANTED,
        subject_id=PERSON,
        amount_cents=50,
        pool=Pool.PAID,
        occurred_at=NOW,
    )
    db.flush()

    totals = paid_totals(db, since=NOW, until=LATER)

    assert totals.collected_cents == 1000


def test_the_rebate_is_reported_as_its_own_movement(db):
    append(
        db,
        type=EventType.REBATE_GRANTED,
        subject_id=PERSON,
        amount_cents=50,
        pool=Pool.PAID,
        occurred_at=NOW,
    )
    db.flush()

    totals = paid_totals(db, since=NOW, until=LATER)

    assert totals.rebated_cents == 50


def test_the_rebate_still_increases_what_is_owed(db):
    """It is real balance. The payer can spend it, so it is a debt like any other — it just
    was not collected."""
    append(
        db,
        type=EventType.RECHARGED,
        subject_id=PERSON,
        amount_cents=1000,
        pool=Pool.PAID,
        occurred_at=NOW,
    )
    append(
        db,
        type=EventType.REBATE_GRANTED,
        subject_id=PERSON,
        amount_cents=50,
        pool=Pool.PAID,
        occurred_at=NOW,
    )
    db.flush()

    totals = paid_totals(db, since=NOW, until=LATER)

    assert totals.outstanding_cents == 1050


def test_a_rebate_is_never_a_gifted_credit(db):
    """It came from a payment, so it belongs to the paid pool and to the liability — not to
    the acquisition charge of FR67."""
    from src.credit_journal import credit_entries

    append(
        db,
        type=EventType.REBATE_GRANTED,
        subject_id=PERSON,
        amount_cents=50,
        pool=Pool.PAID,
        occurred_at=NOW,
    )
    db.flush()

    assert credit_entries(db, subject_id=PERSON) == []


def test_an_unknown_platform_is_refused_rather_than_given_the_rebate():
    """Defaulting an unrecognised client to the web rate would let anybody claim it by
    sending a string nobody recognises."""
    with pytest.raises(ValueError):
        credited_cents(1000, platform="playstation")
