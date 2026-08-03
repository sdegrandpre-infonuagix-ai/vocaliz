"""The auction: who gets spoken in a salon, and what they pay.

Three variables. Language is a gate — a logical OR over what is spoken in the room — because an
ad nobody there could follow should not win at any price. Region and topics are the score, with
the bid distributed across them by two configurable coefficients.

Second price throughout: the winner pays the least it would have taken to beat the runner-up. A
first-price auction is played rather than bid, and the ranking stops meaning anything.
"""
import pytest

from src.config import settings
from src.models.ad import Ad
from src.models.ad_broadcast import AdBroadcast
from src.models.advertiser import Advertiser
from src.models.region import AdvertiserRegion, Region, RegionGooglePlusCode
from src.models.session import SessionModel
from src.models.user import User
from src.services import ad_auction_service, location_service

MONTREAL = location_service.plus_code(45.5019, -73.5674)
QUEBEC = location_service.plus_code(46.8139, -71.2080)


@pytest.fixture
def salon(db):
    user = User(email="auctionhost@example.com")
    db.add(user)
    db.commit()
    db.refresh(user)
    s = SessionModel(
        host_user_id=user.id,
        livekit_room_name="salon-auction",
        source_type="url",
        source_content="c",
        status="active",
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def _advertiser(db, name, *, cells=()):
    row = Advertiser(company=name, email=f"{name.lower()}@example.com")
    db.add(row)
    db.commit()
    db.refresh(row)

    if cells:
        region = Region(region_name=f"{name} region")
        db.add(region)
        db.commit()
        db.refresh(region)
        for cell in cells:
            db.add(RegionGooglePlusCode(region_id=region.region_id, google_plus_code=cell))
        db.add(
            AdvertiserRegion(advertiser_id=row.advertiser_id, region_id=region.region_id)
        )
        db.commit()
    return row


def _ad(db, advertiser, *, bid, topic="coffee", language="en", left=5):
    row = Ad(
        advertiser_id=advertiser.advertiser_id,
        sales_pitch=f"{advertiser.company} pitch.",
        bid_cents=bid,
        topic=topic,
        spoken_language=language,
        number_of_broadcasts_left=left,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


# ─── The language gate ────────────────────────────────────────────────────────

def test_a_language_nobody_speaks_is_excluded_at_any_price(db, salon):
    """Not a worse match — a wrong one. Weighting it would let a large enough bid in Vietnamese
    take a French salon."""
    rich = _ad(db, _advertiser(db, "Rich"), bid=10000, language="vi")
    assert rich is not None
    assert ad_auction_service.run_auction(db, salon_languages=["fr"]) is None


def test_one_matching_speaker_is_enough(db, salon):
    """A logical OR: the ad has to reach somebody, not everybody."""
    _ad(db, _advertiser(db, "English"), bid=100, language="en")
    outcome = ad_auction_service.run_auction(db, salon_languages=["fr", "en"])
    assert outcome is not None


def test_a_regional_variant_still_matches(db, salon):
    """fr-CA changes how something sounds, not whether it is understood."""
    _ad(db, _advertiser(db, "French"), bid=100, language="fr")
    assert ad_auction_service.run_auction(db, salon_languages=["fr-CA"]) is not None


def test_a_salon_with_no_recorded_language_admits_everything(db, salon):
    """Nothing has been heard yet. Excluding every ad would mean the opening minutes of every
    conversation are never monetised."""
    _ad(db, _advertiser(db, "Any"), bid=100, language="ko")
    assert ad_auction_service.run_auction(db, salon_languages=[]) is not None


# ─── Region and topics as fractions ───────────────────────────────────────────

def test_region_match_is_a_fraction_of_participants(db, salon):
    """A salon where everyone is local is worth more to a local business than one where a single
    person is. A boolean would throw that away."""
    local = _advertiser(db, "Local", cells=[MONTREAL])
    ad = _ad(db, local, bid=100)

    assert ad_auction_service.region_match(db, ad, [MONTREAL, MONTREAL]) == 1.0
    assert ad_auction_service.region_match(db, ad, [MONTREAL, QUEBEC]) == 0.5
    assert ad_auction_service.region_match(db, ad, [QUEBEC]) == 0.0


def test_a_participant_with_no_position_counts_against_the_ad(db, salon):
    """The honest reading: they are not inside the region. The alternative lets an advertiser
    pay for reach it cannot demonstrate."""
    local = _advertiser(db, "Local", cells=[MONTREAL])
    ad = _ad(db, local, bid=100)
    assert ad_auction_service.region_match(db, ad, [MONTREAL, ""]) == 0.5


def test_buying_no_region_means_everywhere(db, salon):
    """The same convention the rest of the targeting uses: no restriction is not no reach."""
    ad = _ad(db, _advertiser(db, "Global"), bid=100)
    assert ad_auction_service.region_match(db, ad, [QUEBEC]) == 1.0


def test_topic_match_is_a_fraction_of_the_salons_topics(db, salon):
    ad = _ad(db, _advertiser(db, "Coffee"), bid=100, topic="coffee")
    assert ad_auction_service.topic_match(ad, ["coffee", "pastry"]) == 0.5
    assert ad_auction_service.topic_match(ad, ["politics", "war"]) == 0.0


def test_topic_match_reaches_a_longer_phrase(db, salon):
    """An ad on "coffee" should reach a salon topic of "coffee roasting"."""
    ad = _ad(db, _advertiser(db, "Coffee"), bid=100, topic="coffee")
    assert ad_auction_service.topic_match(ad, ["coffee roasting"]) == 1.0


def test_an_ad_with_no_topic_matches_anything(db, salon):
    ad = _ad(db, _advertiser(db, "Anything"), bid=100, topic="")
    assert ad_auction_service.topic_match(ad, ["politics"]) == 1.0


# ─── The coefficients ─────────────────────────────────────────────────────────

def test_the_coefficients_shift_who_wins(db, salon):
    """The whole point of making them configurable: the same two bids produce different winners
    depending on whether geography or subject is valued more."""
    local = _ad(db, _advertiser(db, "Local", cells=[MONTREAL]), bid=100, topic="unrelated")
    # Given a region that does not match, deliberately. An advertiser who bought none scores a
    # full 1.0 on geography — "everywhere" — and would win under either weighting, which would
    # make the test prove nothing.
    relevant = _ad(db, _advertiser(db, "Relevant", cells=[QUEBEC]), bid=100, topic="coffee")

    original = (settings.bid_region_weight, settings.bid_topic_weight)
    try:
        settings.bid_region_weight, settings.bid_topic_weight = 10.0, 1.0
        by_region = ad_auction_service.run_auction(
            db, participant_codes=[MONTREAL], salon_topics=["coffee"]
        )
        settings.bid_region_weight, settings.bid_topic_weight = 1.0, 10.0
        by_topic = ad_auction_service.run_auction(
            db, participant_codes=[MONTREAL], salon_topics=["coffee"]
        )
    finally:
        settings.bid_region_weight, settings.bid_topic_weight = original

    assert by_region["ad"].ad_id == local.ad_id
    assert by_topic["ad"].ad_id == relevant.ad_id


def test_the_coefficients_are_normalised_by_their_ratio(db, salon):
    """3 and 1 means the same as 0.75 and 0.25. A configuration that happened not to sum to one
    would otherwise quietly scale every bid."""
    ad = _ad(db, _advertiser(db, "One"), bid=100, topic="coffee")
    original = (settings.bid_region_weight, settings.bid_topic_weight)
    try:
        settings.bid_region_weight, settings.bid_topic_weight = 3.0, 1.0
        a = ad_auction_service.relevance(db, ad, participant_codes=[MONTREAL], salon_topics=["coffee"])
        settings.bid_region_weight, settings.bid_topic_weight = 0.75, 0.25
        b = ad_auction_service.relevance(db, ad, participant_codes=[MONTREAL], salon_topics=["coffee"])
    finally:
        settings.bid_region_weight, settings.bid_topic_weight = original
    assert a == b


# ─── Second price ─────────────────────────────────────────────────────────────

def test_the_winner_pays_less_than_it_bid(db, salon):
    """The property that makes a bid worth setting honestly. A first-price auction is played
    rather than bid."""
    _ad(db, _advertiser(db, "High"), bid=500, topic="coffee")
    _ad(db, _advertiser(db, "Low"), bid=200, topic="coffee")

    outcome = ad_auction_service.run_auction(db, salon_topics=["coffee"])
    assert outcome["ad"].bid_cents == 500
    assert outcome["priceCents"] < 500
    assert outcome["priceCents"] >= 200


def test_the_highest_bid_wins_at_equal_relevance(db, salon):
    _ad(db, _advertiser(db, "High"), bid=500, topic="coffee")
    _ad(db, _advertiser(db, "Low"), bid=200, topic="coffee")
    assert ad_auction_service.run_auction(db, salon_topics=["coffee"])["ad"].bid_cents == 500


def test_a_lone_bidder_pays_the_reserve(db, salon):
    """Nobody to outbid, so there is no second price to compute — the floor is the price."""
    _ad(db, _advertiser(db, "Alone"), bid=900, topic="coffee")
    outcome = ad_auction_service.run_auction(db, salon_topics=["coffee"])
    assert outcome["priceCents"] == settings.ad_broadcast_rate_cents


def test_the_price_never_exceeds_the_bid(db, salon):
    """A ceiling is a ceiling. A relevance advantage must not turn into a charge above what the
    advertiser offered."""
    _ad(db, _advertiser(db, "Modest"), bid=30, topic="coffee")
    _ad(db, _advertiser(db, "Rival"), bid=29, topic="coffee")
    outcome = ad_auction_service.run_auction(db, salon_topics=["coffee"])
    assert outcome["priceCents"] <= outcome["ad"].bid_cents


# ─── Who is eligible at all ───────────────────────────────────────────────────

def test_a_bid_below_the_reserve_is_not_a_bidder(db, salon):
    _ad(db, _advertiser(db, "Cheap"), bid=settings.ad_broadcast_rate_cents - 1, topic="coffee")
    assert ad_auction_service.run_auction(db, salon_topics=["coffee"]) is None


def test_an_exhausted_ad_does_not_bid(db, salon):
    _ad(db, _advertiser(db, "Spent"), bid=500, topic="coffee", left=0)
    assert ad_auction_service.run_auction(db, salon_topics=["coffee"]) is None


def test_matching_neither_dimension_is_no_bid_at_all(db, salon):
    """Not a weak offer — nothing staked on this salon."""
    _ad(db, _advertiser(db, "Elsewhere", cells=[QUEBEC]), bid=900, topic="knitting")
    assert (
        ad_auction_service.run_auction(
            db, participant_codes=[MONTREAL], salon_topics=["coffee"]
        )
        is None
    )


def test_no_eligible_ad_is_an_ordinary_outcome(db, salon):
    """A salon with no suitable advertiser simply hears no advertising."""
    assert ad_auction_service.run_auction(db, salon_topics=["coffee"]) is None


# ─── Recording the winner ─────────────────────────────────────────────────────

def test_the_winner_is_recorded_at_the_price_it_won_for(db, salon):
    _ad(db, _advertiser(db, "High"), bid=500, topic="coffee")
    _ad(db, _advertiser(db, "Low"), bid=200, topic="coffee")

    row = ad_auction_service.broadcast_winner(
        db, session=salon, salon_topics=["coffee"], salon_languages=["en"]
    )
    assert row is not None
    assert row.amount_cents < 500, "the second price, not the bid"
    assert row.salon_name == "salon-auction"


def test_winning_reserves_without_spending(db, salon):
    """Winning sets the ad aside; it does not spend it. The salon may close before the greeting
    ends, and an advertiser must pay nothing — neither money nor one of their broadcasts — for a
    sentence nobody heard."""
    ad = _ad(db, _advertiser(db, "Alone"), bid=500, topic="coffee", left=2)
    row = ad_auction_service.broadcast_winner(db, session=salon, salon_topics=["coffee"])
    db.expire_all()
    assert db.get(Ad, ad.ad_id).number_of_broadcasts_left == 2
    assert db.get(AdBroadcast, row.id).delivered_at is None


def test_delivery_is_what_spends_the_allowance(db, salon):
    ad = _ad(db, _advertiser(db, "Alone"), bid=500, topic="coffee", left=2)
    row = ad_auction_service.broadcast_winner(db, session=salon, salon_topics=["coffee"])
    assert ad_auction_service.mark_delivered(db, row)
    db.expire_all()
    assert db.get(Ad, ad.ad_id).number_of_broadcasts_left == 1


def test_nothing_is_recorded_when_nobody_is_eligible(db, salon):
    assert ad_auction_service.broadcast_winner(db, session=salon, salon_topics=["x"]) is None
    assert db.query(AdBroadcast).count() == 0
