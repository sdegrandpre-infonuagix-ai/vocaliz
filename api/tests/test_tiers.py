"""The four tiers as they are offered, and what a credit buys in each (FR69).

Two things this has to get right, and both are about what somebody can work out from the
screen in front of them.

The first is that each tier adds exactly *one* thing to the one below it — a natural voice,
then the absence of advertising, then a premium model. A price gap that corresponds to two
changes at once is a gap nobody can evaluate: they cannot tell which half they are paying
for, so they cannot tell whether it is worth it.

The second is that a rate per hour is not what somebody with credit wants to know. "7.50 an
hour" and "your credit covers 40 minutes here" are the same fact, and only the second one
answers the question actually being asked. It is computed on what is *left*, never on the
five dollars originally given — a screen quoting the original after half of it is gone is
quoting a number that stopped being true.
"""
import uuid
from datetime import datetime, timezone

from src.credit import TIER_RATES_CENTS_PER_HOUR, Tier, debit, grant_welcome_credit
from src.tiers import (
    SPEECH_TO_SPEECH_ALWAYS_OFFERED,
    HOST_CONFIGURABLE_TIERS,
    TierOffer,
    covers_minutes,
    offer_for,
)

PERSON = uuid.uuid4()
NOW = datetime(2026, 3, 1, tzinfo=timezone.utc)


def _with_credit(db, *, spent=0):
    grant_welcome_credit(
        db, subject_id=PERSON, identifiers=[f"{uuid.uuid4()}@example.com"], now=NOW
    )
    db.flush()
    if spent:
        debit(db, PERSON, cents=spent, now=NOW)
        db.flush()


# ── One difference at a time ──────────────────────────────────────────────────


def test_each_tier_adds_exactly_one_thing_to_the_one_below():
    """A gap that corresponds to two changes at once cannot be evaluated: somebody cannot
    tell which half they are paying for, so they cannot tell whether it is worth it."""
    ordered = list(Tier)
    for lower, higher in zip(ordered, ordered[1:]):
        differences = TierOffer.of(lower).differences_from(TierOffer.of(higher))
        assert len(differences) == 1, f"{lower.label} → {higher.label}: {differences}"


def test_the_first_step_up_is_the_natural_voice():
    assert TierOffer.of(Tier.BASE).natural_voice is False
    assert TierOffer.of(Tier.MODE_A).natural_voice is True


def test_the_second_step_up_is_the_absence_of_advertising():
    assert TierOffer.of(Tier.MODE_A).advertising is True
    assert TierOffer.of(Tier.MODE_B).advertising is False


def test_the_third_step_up_is_the_premium_model():
    assert TierOffer.of(Tier.MODE_B).premium_voice is False
    assert TierOffer.of(Tier.MODE_C).premium_voice is True


def test_no_tier_is_free_and_every_rate_is_visible():
    for tier in Tier:
        offer = TierOffer.of(tier)
        assert offer.cents_per_hour > 0
        assert offer.rate_label


def test_the_three_the_host_configures_are_the_paid_modes():
    """Base is the floor rather than an option: it is what applies when nothing is chosen."""
    assert HOST_CONFIGURABLE_TIERS == (Tier.MODE_A, Tier.MODE_B, Tier.MODE_C)


def test_the_rates_are_the_ones_on_the_screen():
    assert TierOffer.of(Tier.MODE_A).cents_per_hour == 750
    assert TierOffer.of(Tier.MODE_B).cents_per_hour == 1500
    assert TierOffer.of(Tier.MODE_C).cents_per_hour == 2250


def test_speech_to_speech_is_always_offered():
    """Whatever the context. A capability that appears and disappears depending on
    circumstances is one nobody learns to rely on."""
    assert SPEECH_TO_SPEECH_ALWAYS_OFFERED is True


# ── What the credit covers ────────────────────────────────────────────────────


def test_a_credit_is_shown_as_a_duration_not_only_a_rate(db):
    _with_credit(db)

    offers = offer_for(db, PERSON)

    assert all(offer.covers_minutes is not None for offer in offers)


def test_the_duration_is_what_the_money_actually_buys(db):
    _with_credit(db)

    offers = {offer.tier: offer for offer in offer_for(db, PERSON)}

    # 500 cents at 750/hour is 40 minutes.
    assert offers[Tier.MODE_A].covers_minutes == 40
    # And at 300/hour, an hour and forty.
    assert offers[Tier.BASE].covers_minutes == 100


def test_a_dearer_tier_buys_less_time(db):
    _with_credit(db)

    offers = {offer.tier: offer for offer in offer_for(db, PERSON)}

    assert offers[Tier.MODE_C].covers_minutes < offers[Tier.MODE_A].covers_minutes


def test_the_duration_is_computed_on_what_is_left(db):
    """Never on the five dollars originally given. A screen quoting the original after half
    of it is gone is quoting a number that stopped being true."""
    _with_credit(db, spent=250)

    offers = {offer.tier: offer for offer in offer_for(db, PERSON)}

    assert offers[Tier.MODE_A].covers_minutes == 20


def test_an_exhausted_credit_shows_the_rate_alone(db):
    """No mention of credit at all. "Your credit covers 0 minutes" is a sentence that
    advertises a disappointment."""
    _with_credit(db, spent=500)

    offers = offer_for(db, PERSON)

    assert all(offer.covers_minutes is None for offer in offers)


def test_somebody_who_never_had_credit_shows_the_rate_alone(db):
    offers = offer_for(db, uuid.uuid4())

    assert all(offer.covers_minutes is None for offer in offers)


def test_the_rate_is_shown_whether_or_not_there_is_credit(db):
    _with_credit(db, spent=500)

    for offer in offer_for(db, PERSON):
        assert offer.cents_per_hour == TIER_RATES_CENTS_PER_HOUR[offer.tier]


def test_covering_less_than_a_minute_is_not_rounded_up_to_one(db):
    """Rounding a few seconds up to "1 min" promises something the money does not buy."""
    assert covers_minutes(10, Tier.MODE_C) == 0


def test_a_duration_of_zero_is_not_offered_as_a_duration(db):
    """Which is why an exhausted credit falls back to the rate rather than showing zero."""
    _with_credit(db, spent=495)

    offers = {offer.tier: offer for offer in offer_for(db, PERSON)}

    assert offers[Tier.MODE_C].covers_minutes is None


# ── The host's choice is the host's alone ─────────────────────────────────────


def test_the_offer_is_the_same_shape_for_everybody(db):
    """The screen is personal, not the catalogue. What differs between two people is their
    credit, never which tiers exist."""
    _with_credit(db)

    mine = [offer.tier for offer in offer_for(db, PERSON)]
    theirs = [offer.tier for offer in offer_for(db, uuid.uuid4())]

    assert mine == theirs


def test_one_persons_credit_never_shows_on_anothers_offer(db):
    _with_credit(db)

    offers = offer_for(db, uuid.uuid4())

    assert all(offer.covers_minutes is None for offer in offers)


def test_the_hosts_choice_is_recorded_against_the_host_alone(db):
    """A Salon does not have a mode. Each participant has one, and a column on the Salon
    named for the *host* is what keeps that true — anything called `mode` would assert the
    opposite by its name alone."""
    from src.models.salon import Salon

    assert "host_tier" in Salon.__table__.c
    assert "mode" not in Salon.__table__.c


def test_choosing_nothing_is_not_the_same_as_choosing_base(db):
    """Null means the floor applies. A default of "Base" would be indistinguishable from
    somebody actively picking it, and those are different facts."""
    from src.models.salon import Salon

    assert Salon.__table__.c.host_tier.nullable is True
    assert Salon.__table__.c.host_tier.default is None
