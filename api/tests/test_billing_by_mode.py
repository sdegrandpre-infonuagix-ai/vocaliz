"""Each participant billed for their own mode, and the host's offer to cover everybody (FR22).

The inherited billing worked the other way round: one rate, charged to the host after the
Salon. Two things change here and the second is the one with teeth.

Each person pays their own tier, prorated to the second. Somebody on Base beside somebody on
Mode C are billed differently for the same conversation, which is the entire point of letting
them choose.

And it is **prepaid**. Nobody is ever charged past what they put in, and no debt is ever
created — when the balance runs out the Salon ends instead. That is a deliberate trade: a
system that could invoice past the balance would collect more, and would also mean somebody
could leave a conversation owing money they never agreed to spend.
"""
import uuid
from datetime import datetime, timezone

import pytest

from src.billing import (
    HOST_PAYS_TIER,
    HostPaysQuote,
    affordable_seconds,
    charge_for,
    cost_cents,
    host_pays_quote,
)
from src.credit import Tier, balance, grant_welcome_credit
from src.ledger import EventType, Pool, append

PERSON = uuid.uuid4()
NOW = datetime(2026, 3, 1, tzinfo=timezone.utc)


def _topped_up(db, cents, person=PERSON):
    append(
        db,
        type=EventType.RECHARGED,
        subject_id=person,
        amount_cents=cents,
        pool=Pool.PAID,
        occurred_at=NOW,
    )
    db.flush()


# ── The price of a mode, by the second ────────────────────────────────────────


def test_an_hour_of_a_mode_costs_its_hourly_rate():
    assert cost_cents(Tier.MODE_A, 3600) == 750
    assert cost_cents(Tier.BASE, 3600) == 300


def test_half_an_hour_costs_half():
    assert cost_cents(Tier.MODE_A, 1800) == 375


def test_it_is_prorated_rather_than_rounded_up_to_a_block():
    """Billing a started hour as a whole one is how a one-minute conversation costs 15.00.
    A minute of Mode B is 25 cents, and that is what it costs."""
    assert cost_cents(Tier.MODE_B, 60) == 25


def test_every_second_counts_towards_the_price():
    """Not by the minute either: 90 seconds costs more than 60, rather than both landing on
    the same rounded block."""
    assert cost_cents(Tier.MODE_B, 90) > cost_cents(Tier.MODE_B, 60)


def test_a_fraction_of_a_cent_is_never_rounded_up():
    """Rounding up charges for something nobody consumed. Over a long enough history the
    difference is small; the principle is that a bill never exceeds the thing it is for."""
    assert cost_cents(Tier.BASE, 1) == 0


def test_two_people_on_two_modes_pay_two_different_prices():
    """The point of letting somebody choose. The same conversation costs them differently."""
    assert cost_cents(Tier.BASE, 3600) != cost_cents(Tier.MODE_C, 3600)


def test_nothing_consumed_costs_nothing():
    assert cost_cents(Tier.MODE_C, 0) == 0


# ── Charged against their own balance ─────────────────────────────────────────


def test_somebody_is_charged_at_their_own_modes_rate(db):
    _topped_up(db, 2000)

    charge_for(db, PERSON, tier=Tier.MODE_A, seconds=3600, now=NOW)
    db.flush()

    assert balance(db, PERSON).paid_cents == 2000 - 750


def test_the_welcome_credit_is_spent_before_the_money(db):
    grant_welcome_credit(db, subject_id=PERSON, identifiers=["a@example.com"], now=NOW)
    _topped_up(db, 2000)

    charge_for(db, PERSON, tier=Tier.MODE_A, seconds=3600, now=NOW)
    db.flush()

    view = balance(db, PERSON)
    assert (view.gifted_cents, view.paid_cents) == (0, 2000 - 250)


def test_a_charge_records_which_part_it_came_from(db):
    _topped_up(db, 2000)

    charged = charge_for(db, PERSON, tier=Tier.MODE_A, seconds=3600, now=NOW)
    db.flush()

    assert [move.pool for move in charged.movements] == [Pool.PAID.value]


# ── Never past the balance, never a debt ──────────────────────────────────────


def test_nobody_is_charged_more_than_they_put_in(db):
    """The whole shape of a prepaid system. A bill larger than the balance would be a debt
    somebody never agreed to, arriving after a conversation they thought was paid for."""
    _topped_up(db, 100)

    charged = charge_for(db, PERSON, tier=Tier.MODE_C, seconds=3600, now=NOW)
    db.flush()

    assert charged.charged_cents == 100
    assert balance(db, PERSON).total_cents == 0


def test_the_shortfall_is_reported_rather_than_owed(db):
    _topped_up(db, 100)

    charged = charge_for(db, PERSON, tier=Tier.MODE_C, seconds=3600, now=NOW)

    assert charged.shortfall_cents == 2250 - 100
    assert charged.exhausted is True


def test_an_exhausted_balance_ends_the_salon_rather_than_billing_on(db):
    """FR55. Ending is the honest outcome: the alternative is a conversation that carries on
    accruing something nobody authorised."""
    _topped_up(db, 100)

    charged = charge_for(db, PERSON, tier=Tier.MODE_C, seconds=3600, now=NOW)

    assert charged.ends_salon is True


def test_a_covered_charge_ends_nothing(db):
    _topped_up(db, 2000)

    charged = charge_for(db, PERSON, tier=Tier.MODE_A, seconds=3600, now=NOW)

    assert charged.exhausted is False
    assert charged.ends_salon is False
    assert charged.shortfall_cents == 0


def test_somebody_with_nothing_at_all_is_charged_nothing(db):
    charged = charge_for(db, PERSON, tier=Tier.MODE_A, seconds=3600, now=NOW)
    db.flush()

    assert charged.charged_cents == 0
    assert balance(db, PERSON).total_cents == 0


def test_a_balance_never_goes_below_zero(db):
    _topped_up(db, 50)

    charge_for(db, PERSON, tier=Tier.MODE_C, seconds=7200, now=NOW)
    db.flush()

    assert balance(db, PERSON).total_cents == 0


# ── How long the money lasts ──────────────────────────────────────────────────


def test_the_balance_is_reported_as_seconds_of_the_chosen_mode(db):
    _topped_up(db, 750)

    assert affordable_seconds(db, PERSON, Tier.MODE_A) == 3600


def test_a_dearer_mode_buys_fewer_seconds(db):
    _topped_up(db, 2250)

    assert affordable_seconds(db, PERSON, Tier.MODE_C) < affordable_seconds(
        db, PERSON, Tier.BASE
    )


def test_an_empty_balance_buys_no_time(db):
    assert affordable_seconds(db, PERSON, Tier.BASE) == 0


# ── The host covering everybody ───────────────────────────────────────────────


def test_the_host_pays_at_mode_b_for_each_participant():
    assert HOST_PAYS_TIER is Tier.MODE_B

    quote = host_pays_quote(participants=3)

    assert quote.cents_per_hour == 1500 * 3


def test_the_quote_grows_with_the_room():
    assert host_pays_quote(participants=5).cents_per_hour > host_pays_quote(
        participants=2
    ).cents_per_hour


def test_the_worst_hourly_cost_is_stated_before_the_option_turns_on():
    """Explicitly, and in money. "The host pays" without a number is an option somebody
    agrees to without knowing what they agreed to."""
    quote = host_pays_quote(participants=4)

    assert isinstance(quote, HostPaysQuote)
    assert "60.00" in quote.confirmation_text


def test_the_option_does_not_activate_without_confirmation():
    quote = host_pays_quote(participants=4)

    assert quote.requires_confirmation is True
    assert quote.active is False


def test_confirming_is_what_turns_it_on():
    quote = host_pays_quote(participants=4).confirmed()

    assert quote.active is True


def test_the_quote_is_for_the_maximum_rather_than_a_guess():
    """It is what the hour costs if everybody stays the whole hour. A lower estimate that
    people then exceeded would be worse than useless."""
    quote = host_pays_quote(participants=2)

    assert quote.cents_per_hour == 1500 * 2
    assert "maximum" in quote.confirmation_text.lower()


def test_a_salon_of_one_still_quotes_a_price():
    assert host_pays_quote(participants=1).cents_per_hour == 1500


def test_a_host_paying_for_nobody_is_quoted_nothing(db):
    assert host_pays_quote(participants=0).cents_per_hour == 0


def test_the_host_is_charged_for_everybody(db):
    """One charge covering the room, at Mode B per head."""
    _topped_up(db, 10_000)

    charged = charge_for(db, PERSON, tier=Tier.MODE_B, seconds=3600, now=NOW, heads=3)
    db.flush()

    assert charged.charged_cents == 1500 * 3


def test_a_guest_the_host_pays_for_is_charged_nothing_themselves(db):
    """They are in Mode B and their own balance is untouched — otherwise "the host pays"
    would mean "the host pays as well"."""
    guest = uuid.uuid4()
    _topped_up(db, 5000, person=PERSON)
    _topped_up(db, 5000, person=guest)

    charge_for(db, PERSON, tier=Tier.MODE_B, seconds=3600, now=NOW, heads=2)
    db.flush()

    assert balance(db, guest).paid_cents == 5000


def test_one_head_is_the_ordinary_case(db):
    _topped_up(db, 5000)

    charged = charge_for(db, PERSON, tier=Tier.MODE_B, seconds=3600, now=NOW)

    assert charged.charged_cents == 1500


def test_a_negative_head_count_is_refused(db):
    with pytest.raises(ValueError):
        charge_for(db, PERSON, tier=Tier.MODE_B, seconds=3600, now=NOW, heads=-1)
