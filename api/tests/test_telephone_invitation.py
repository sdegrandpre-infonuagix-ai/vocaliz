"""Everything that has to be settled before a telephone rings (Story 10.5 / FR5, FR56).

The dialling itself does not exist — there is no SIP trunk and no dispatch rule, which the
front-desk code already says out loud. What *can* exist, and is the part with the decisions in
it, is everything the host and the agent have to agree on first: which number, at whose word,
at which tier, at whose expense, and whether there is even a seat.

The confirmation is the piece worth being careful about. Recognising a number from speech is
guesswork, and a wrong guess here does not produce a failed action — it produces a telephone
ringing in a stranger's house at the expense of a host who never asked for it. So the agent
reads the number back and waits for a plain yes. Nothing else in Vocaliz calls anybody.

A telephone participant is always at the host's charge. They chose nothing, they signed up for
nothing, and they must therefore spend nothing — not their credit, not their free minutes. That
is the same reasoning that makes the payment check independent of "the host pays all": that
option is about the *other* participants, and it being off says nothing about somebody the host
personally caused to be telephoned.
"""
import uuid

import pytest

from src.credit import Tier
from src.telephone_invitation import (
    DEFAULT_TELEPHONE_TIER,
    TELEPHONE_SUPPLEMENT_CENTS_PER_HOUR,
    TELEPHONE_TIERS,
    Refusal,
    confirmation_prompt,
    cost_cents,
    heard_confirmation,
    may_dial,
    charged_to,
    recognise_number,
    spends_own_quota,
    tier_from,
)


# ── Which number ──────────────────────────────────────────────────────────────


def test_a_number_is_recognised_from_the_spoken_invitation():
    assert recognise_number("invite le 514 555 0123") == "+15145550123"


def test_punctuation_and_words_around_it_are_not_part_of_the_number():
    assert recognise_number("appelle donc le (514) 555-0123, s'il te plaît") == "+15145550123"


def test_a_number_already_carrying_its_country_keeps_it():
    assert recognise_number("invite le +33 6 12 34 56 78") == "+33612345678"


def test_a_command_with_no_number_recognises_nothing():
    """Nothing is dialled on a maybe. The agent has to be able to say it did not catch one."""
    assert recognise_number("invite mon ami") is None


def test_too_few_digits_is_not_a_number():
    """Somebody said a year, or an amount. Dialling four digits is dialling something."""
    assert recognise_number("invite le 2026") is None


# ── At whose word ─────────────────────────────────────────────────────────────


def test_the_number_is_read_back_in_groups():
    """Read back digit by digit in small groups, because that is how somebody checks a
    number against the one in their head. A single run of eleven digits cannot be followed."""
    prompt = confirmation_prompt("+15145550123")

    assert "+1 514 555 0123" in prompt


def test_a_number_outside_north_america_is_grouped_too():
    assert "+33 612 345 678" in confirmation_prompt("+33612345678")


def test_a_stored_number_with_no_plus_is_still_readable():
    """`signup.normalise_phone` keeps a leading plus only when one was typed, so a number
    taken from an account may arrive bare. Reading it back as one unbroken run would defeat
    the check the read-back exists for."""
    from src.signup import normalise_phone

    stored = normalise_phone("514 555 0123")
    assert stored == "5145550123"

    assert "514 555 0123" in confirmation_prompt(stored)


def test_the_prompt_asks_for_a_yes():
    """An explicit confirmation and not an absence of objection. Silence is not consent when
    the consequence is a stranger's telephone ringing."""
    assert "?" in confirmation_prompt("+15145550123")


@pytest.mark.parametrize("answer", ["oui", "Oui, vas-y", "yes", "c'est ça", "exact"])
def test_a_plain_yes_is_a_yes(answer):
    assert heard_confirmation(answer) is True


@pytest.mark.parametrize("answer", ["non", "No", "pas du tout", "non, c'est faux"])
def test_a_plain_no_is_a_no(answer):
    assert heard_confirmation(answer) is False


@pytest.mark.parametrize("answer", ["", "euh", "attends", "le chat est sur la table"])
def test_anything_else_is_neither(answer):
    """`None` is "ask again", and it is not "no" either: treating an unclear answer as a
    refusal would make the agent give up on a host who simply coughed."""
    assert heard_confirmation(answer) is None


def test_a_refusal_dials_nothing_and_asks_again():
    """The host said the number was wrong. What follows is a question, not a retry of the
    same guess."""
    assert heard_confirmation("non") is False


# ── At which tier ─────────────────────────────────────────────────────────────


def test_the_tier_can_be_named_in_the_same_breath():
    assert tier_from("invite le 514 555 0123 en Mode C") is Tier.MODE_C


def test_saying_nothing_about_the_tier_takes_the_default():
    assert tier_from("invite le 514 555 0123") is DEFAULT_TELEPHONE_TIER
    assert DEFAULT_TELEPHONE_TIER is Tier.MODE_B


def test_the_default_is_named_in_english_too():
    assert tier_from("invite 514 555 0123 in mode a") is Tier.MODE_A


def test_base_is_not_offered_by_telephone():
    """The host pays the supplement and the interpreter either way, so the cheapest tier
    buys them nothing and costs the person on the line a worse conversation."""
    assert Tier.BASE not in TELEPHONE_TIERS
    assert TELEPHONE_TIERS == (Tier.MODE_A, Tier.MODE_B, Tier.MODE_C)


def test_asking_for_base_by_telephone_falls_to_the_default_rather_than_the_floor():
    """Not silently the cheapest thing available. The host asked for something that is not
    on offer here, and the offer is what they get."""
    assert tier_from("invite le 514 555 0123 en Base") is DEFAULT_TELEPHONE_TIER


# ── At whose expense ──────────────────────────────────────────────────────────


def test_nothing_is_dialled_without_a_registered_payment_method():
    refusal = may_dial(payment_method=False, present=1, cap=3)

    assert isinstance(refusal, Refusal)
    assert "payment" in refusal.spoken.lower()


def test_the_payment_check_does_not_depend_on_the_host_paying_all():
    """FR42's option is about the *other* participants. It being off says nothing about
    somebody the host personally caused to be telephoned."""
    assert may_dial(payment_method=False, present=1, cap=3, host_pays_all=True) is not None
    assert may_dial(payment_method=True, present=1, cap=3, host_pays_all=False) is None


def test_a_full_salon_takes_no_telephone_participant_either():
    """The cap is about people in the room, and somebody on a telephone is a person in the
    room. Dialling first and refusing at the door would ring a stranger for nothing."""
    refusal = may_dial(payment_method=True, present=3, cap=3)

    assert isinstance(refusal, Refusal)
    assert "3" in refusal.spoken


def test_the_last_seat_may_be_telephoned():
    assert may_dial(payment_method=True, present=2, cap=3) is None


def test_the_refusal_is_something_the_host_hears():
    """Spoken, because the host is in a conversation and not looking at a screen (NFR3)."""
    refusal = may_dial(payment_method=True, present=3, cap=3)

    assert refusal.spoken.endswith(".")
    assert len(refusal.spoken.split()) > 3


def test_the_seat_is_checked_before_the_payment_method():
    """A host whose Salon is full does not need to be told to add a card for a call that
    could not happen anyway. One refusal, and it is the one that is actually in the way."""
    refusal = may_dial(payment_method=False, present=3, cap=3)

    assert "3" in refusal.spoken


# ── What it costs ─────────────────────────────────────────────────────────────


def test_the_supplement_is_a_dollar_an_hour():
    assert TELEPHONE_SUPPLEMENT_CENTS_PER_HOUR == 100


def test_an_hour_costs_the_tier_plus_the_supplement():
    """Mode B is 1500 an hour, and the telephone adds 100."""
    assert cost_cents(Tier.MODE_B, 3600) == 1600


def test_it_is_prorated_to_the_second():
    """Billing a started minute as a whole one is how a two-minute call costs an hour."""
    assert cost_cents(Tier.MODE_B, 1800) == 800


def test_it_rounds_down():
    """A bill never exceeds the thing it is for."""
    assert cost_cents(Tier.MODE_A, 1) == 0
    assert cost_cents(Tier.MODE_C, 3600) == 2350


def test_a_call_that_never_connected_costs_nothing():
    assert cost_cents(Tier.MODE_B, 0) == 0


def test_the_supplement_applies_at_every_offered_tier():
    """It pays for the SIP minutes and the PSTN termination, which do not get cheaper
    because the interpreter got better."""
    from src.credit import TIER_RATES_CENTS_PER_HOUR

    for tier in TELEPHONE_TIERS:
        assert (
            cost_cents(tier, 3600)
            == TIER_RATES_CENTS_PER_HOUR[tier] + TELEPHONE_SUPPLEMENT_CENTS_PER_HOUR
        )


# ── Whose allowance pays ──────────────────────────────────────────────────────


def test_a_telephone_guest_spends_none_of_their_own_quota():
    """They decided nothing, so they spend nothing. Somebody whose telephone rang did not
    choose a tier, did not sign up, and did not agree to a price — charging their ten free
    minutes for a conversation they were called into would be the one participant with no
    say paying for everybody's convenience."""
    assert spends_own_quota() is False


def test_every_cost_is_the_host_s():
    """The interpreter, the SIP minutes, the PSTN termination and the supplement, all of it.
    Splitting the bill would mean asking the guest to hold an account they never made."""
    host = uuid.uuid4()
    guest = uuid.uuid4()

    assert charged_to(host_id=host, participant_id=guest) == host


def test_the_host_pays_even_for_themselves():
    """A host who telephones their own second line is still the host. The rule is about the
    seat, not about who happens to be sitting in it."""
    host = uuid.uuid4()

    assert charged_to(host_id=host, participant_id=host) == host
