"""The platform's own advertising, and why it is free and last in line."""
import pytest

from src.config import settings
from src.models.ad import Ad
from src.models.ad_broadcast import AdBroadcast
from src.models.advertiser import Advertiser
from src.models.session import SessionModel
from src.models.user import User
from src.services import ad_auction_service, ad_billing_service, house_ads


@pytest.fixture
def salon(db):
    user = User(email="househost@example.com")
    db.add(user)
    db.commit()
    db.refresh(user)
    s = SessionModel(
        host_user_id=user.id,
        livekit_room_name="salon-house",
        source_type="url",
        source_content="c",
        status="active",
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


# ─── Seeding ──────────────────────────────────────────────────────────────────

def test_seeding_creates_one_advertiser_and_two_ads(db):
    house_ads.seed(db)
    assert db.query(Advertiser).filter(Advertiser.email == house_ads.HOUSE_EMAIL).count() == 1
    assert {ad.spoken_language for ad in db.query(Ad).all()} == {"en", "fr"}


def test_seeding_twice_changes_nothing(db):
    house_ads.seed(db)
    house_ads.seed(db)
    assert db.query(Advertiser).count() == 1
    assert db.query(Ad).count() == 2


def test_seeding_restores_edited_copy(db):
    """The function is the definition of what a house ad says, not a one-time insert somebody
    later has to remember editing."""
    house_ads.seed(db)
    ad = db.query(Ad).filter(Ad.spoken_language == "fr").one()
    ad.sales_pitch = "Something a human changed in the database."
    db.commit()

    house_ads.seed(db)
    db.expire_all()
    assert db.query(Ad).filter(Ad.spoken_language == "fr").one().sales_pitch == house_ads.PITCHES["fr"]


def test_both_pitches_name_the_website(db):
    for pitch in house_ads.PITCHES.values():
        assert "infonuagix.ai" in pitch.lower()


# ─── Never in the way of a paying advertiser ──────────────────────────────────

def test_a_house_ad_never_enters_the_auction(db, salon):
    """bid_cents is zero and the auction requires clearing the reserve, so a paying advertiser
    can never be outbid by the platform itself."""
    house_ads.seed(db)
    assert ad_auction_service.run_auction(db, salon_languages=["en"]) is None


def test_a_paying_ad_wins_over_the_house(db, salon):
    house_ads.seed(db)
    payer = Advertiser(company="Payer", email="payer@example.com")
    db.add(payer)
    db.commit()
    db.refresh(payer)
    db.add(
        Ad(
            advertiser_id=payer.advertiser_id,
            sales_pitch="A paying pitch.",
            bid_cents=500,
            topic="",
            spoken_language="en",
            number_of_broadcasts_left=5,
        )
    )
    db.commit()

    row = ad_auction_service.broadcast_winner(db, session=salon, salon_languages=["en"])
    assert row is not None
    assert row.advertiser_id == payer.advertiser_id
    assert row.amount_cents == settings.ad_broadcast_rate_cents


def test_the_house_ad_fills_the_silence_when_nobody_bids(db, salon):
    house_ads.seed(db)
    row = ad_auction_service.broadcast_winner(db, session=salon, salon_languages=["fr"])
    assert row is not None
    assert row.amount_cents == 0


def test_nothing_plays_when_the_house_ads_are_not_seeded(db, salon):
    """A salon then hears no advertising, which is what happened before they existed."""
    assert ad_auction_service.broadcast_winner(db, session=salon, salon_languages=["en"]) is None


# ─── Free means no Stripe object at all ───────────────────────────────────────

def test_a_house_broadcast_is_recorded_but_never_invoiced(db, salon):
    """Better than a 100%-discounted invoice: that would still cost an API call and leave a
    zero-dollar invoice in the history every single day."""
    house_ads.seed(db)
    ad_auction_service.broadcast_winner(db, session=salon, salon_languages=["en"])

    assert db.query(AdBroadcast).count() == 1, "the count and the reporting stay true"
    advertiser = db.query(Advertiser).filter(Advertiser.email == house_ads.HOUSE_EMAIL).one()
    result = ad_billing_service.invoice_advertiser(db, advertiser)
    assert result["status"] == "nothing_to_invoice"
    assert advertiser.stripe_customer_id is None, "no Stripe customer is ever created"


# ─── Which wording is chosen ──────────────────────────────────────────────────

def test_the_pitch_authored_for_the_language_present_is_chosen(db):
    house_ads.seed(db)
    assert house_ads.fallback_ad(db, salon_languages=["fr"]).spoken_language == "fr"
    assert house_ads.fallback_ad(db, salon_languages=["en"]).spoken_language == "en"


def test_a_regional_variant_still_finds_its_pitch(db):
    house_ads.seed(db)
    assert house_ads.fallback_ad(db, salon_languages=["fr-CA"]).spoken_language == "fr"


def test_an_unwritten_language_falls_back_to_english(db):
    """The agent renders any pitch in the listener's language anyway, so this is about which
    wording was authored for whom rather than about comprehension."""
    house_ads.seed(db)
    assert house_ads.fallback_ad(db, salon_languages=["ko"]).spoken_language == "en"
