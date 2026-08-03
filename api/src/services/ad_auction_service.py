"""Choosing which ad is spoken in a salon, and what its advertiser pays for it.

THREE VARIABLES, TWO OF THEM WEIGHTED.

Language is a gate, not a score. An ad whose language matches nobody in the room should not win
at any price, so it is a logical OR over the languages present: eligible if any participant
speaks the one the ad was written in. Weighting it instead would let a large enough bid in
Vietnamese take a French salon, which is not a worse match but a wrong one.

Region and topics are the score. The ad's bid is distributed across them by two configurable
coefficients, and the product is what ranks the bidders:

    score = bid × (Wr × region_match + Wt × topic_match) / (Wr + Wt)

Both matches are fractions rather than booleans. A salon where every participant is inside the
ad's region is worth more than one where a single person is, and an ad sharing four of a
salon's ten topics is a better fit than one sharing a single topic. Booleans would throw that
away and produce a great many ties.

SECOND PRICE. The winner pays the least it would have taken to beat the runner-up, never its
full bid. A first-price auction is played rather than bid: everyone shades their offer downwards
guessing at the others, and the ranking stops reflecting who values the salon most. This is why
AdWords is built this way, and it is the difference between a bid that means something and a
number nobody sets honestly.
"""
import logging

from sqlalchemy.orm import Session as DbSession

from src.config import settings
from src.models.ad import Ad
from src.models.ad_broadcast import AdBroadcast
from src.models.advertiser import Advertiser
from src.models.region import AdvertiserRegion, RegionGooglePlusCode
from src.services import translation_service

logger = logging.getLogger(__name__)


def language_admits(ad_language: str, salon_languages) -> bool:
    """Whether anyone in the room speaks the language this ad was written in.

    A logical OR: one match is enough. Compared on the primary subtag, so an ad written in "fr"
    fits a participant recorded as "fr-CA" — the regional variant changes how something sounds,
    not whether it is understood.

    A salon with no recorded language admits everything. Nothing has been heard yet, and
    excluding every ad from a conversation that has just started would mean the first minutes
    are never monetised at all.
    """
    languages = [lang for lang in (salon_languages or []) if lang]
    if not languages:
        return True
    return any(translation_service.same_language(ad_language, lang) for lang in languages)


def region_match(db: DbSession, ad: Ad, participant_codes) -> float:
    """The fraction of participants inside the regions this ad's advertiser bought.

    A fraction, not a boolean: a salon where everyone is local is worth more to a local business
    than one where a single person is, and collapsing that to true/false would produce ties the
    auction then breaks arbitrarily.

    Participants with no recorded position count against the ad. They are not inside the region
    — that is the honest reading, and the alternative would let an advertiser pay for reach it
    cannot demonstrate.

    Returns 1.0 when the advertiser bought no region at all: no restriction means everywhere,
    which is the same convention the rest of the targeting uses.
    """
    # The advertiser's cells come first, because buying no region settles the answer whatever
    # is known about the participants. Testing the codes first returned zero for an advertiser
    # who had bought nothing — the opposite of "no restriction means everywhere".
    try:
        owned = {
            row[0]
            for row in db.query(RegionGooglePlusCode.google_plus_code)
            .join(
                AdvertiserRegion,
                AdvertiserRegion.region_id == RegionGooglePlusCode.region_id,
            )
            .filter(AdvertiserRegion.advertiser_id == ad.advertiser_id)
            .all()
        }
    except Exception:  # noqa: BLE001
        logger.warning("Could not read regions for advertiser %s", ad.advertiser_id, exc_info=True)
        return 0.0

    if not owned:
        return 1.0

    # Not filtered. A participant with no recorded position counts in the denominator and never
    # in the numerator: they are not inside the region, and dropping them would let an
    # advertiser be credited for reach it cannot demonstrate.
    codes = list(participant_codes or [])
    if not codes:
        return 0.0

    inside = sum(1 for code in codes if code and code in owned)
    return inside / len(codes)


def topic_match(ad: Ad, salon_topics) -> float:
    """How much of what the salon is about this ad is about.

    The ad carries one topic; the salon carries up to ten. The fraction is therefore small by
    construction — an ad matching one of ten topics scores 0.1 — and that is fine, because every
    bidder is scaled the same way and only the ranking matters.

    Substring matching in both directions, so an ad on "coffee" reaches a salon topic of
    "coffee roasting". Crude, and the alternative is an embedding model in the path of a
    conversation.

    Returns 1.0 when the ad names no topic: no restriction means anything, as elsewhere. A salon
    with no topics returns 0.0 for every ad, so the auction falls back to region alone.
    """
    wanted = (ad.topic or "").strip().lower()
    if not wanted:
        return 1.0

    topics = [t.strip().lower() for t in (salon_topics or []) if t and t.strip()]
    if not topics:
        return 0.0

    hits = sum(1 for topic in topics if wanted in topic or topic in wanted)
    return hits / len(topics)


def relevance(db: DbSession, ad: Ad, *, participant_codes, salon_topics) -> float:
    """The share of its bid this ad is actually staking on this salon, between 0 and 1.

    The coefficients are normalised rather than assumed to sum to one, so 3 and 1 means the same
    as 0.75 and 0.25. What matters is their ratio, and a configuration that happened not to add
    up would otherwise quietly scale every bid.
    """
    weight_region = max(settings.bid_region_weight, 0.0)
    weight_topic = max(settings.bid_topic_weight, 0.0)
    total = weight_region + weight_topic
    if total <= 0:
        # Both coefficients zeroed. Treated as "relevance does not matter", which turns the
        # auction into a plain highest-bid contest rather than dividing by zero.
        return 1.0

    return (
        weight_region * region_match(db, ad, participant_codes)
        + weight_topic * topic_match(ad, salon_topics)
    ) / total


def run_auction(
    db: DbSession,
    *,
    participant_codes=None,
    salon_topics=None,
    salon_languages=None,
) -> dict | None:
    """Decide which ad is spoken in this salon, and what it costs.

    Returns the winning ad and the price, or None when nothing is eligible — no bidder, none
    clearing the reserve, or none in a language anyone here speaks. None is an ordinary outcome:
    a salon with no suitable advertiser simply hears no advertising.

    The price is the second-price one. The runner-up's score is the bar the winner had to clear,
    so the winner pays what its own relevance makes that bar cost, plus a cent — and never more
    than it offered, nor less than the reserve.
    """
    reserve = settings.ad_broadcast_rate_cents

    try:
        candidates = (
            db.query(Ad)
            .filter(Ad.number_of_broadcasts_left > 0, Ad.bid_cents >= reserve)
            .all()
        )
    except Exception:  # noqa: BLE001
        logger.warning("Could not read the ad candidates", exc_info=True)
        return None

    scored = []
    for ad in candidates:
        # The language gate first: it is the cheapest test and it discards outright rather than
        # ranking low, so there is no point scoring an ad nobody in the room could follow.
        if not language_admits(ad.spoken_language, salon_languages):
            continue
        share = relevance(
            db, ad, participant_codes=participant_codes, salon_topics=salon_topics
        )
        if share <= 0:
            # Matched on neither dimension. Not a weak bid — no bid at all for this salon.
            continue
        scored.append((ad, share, ad.bid_cents * share))

    if not scored:
        return None

    scored.sort(key=lambda entry: entry[2], reverse=True)
    winner, winner_share, winner_score = scored[0]

    if len(scored) > 1:
        runner_up_score = scored[1][2]
        # What the winner would have had to bid to produce that score, given its own relevance.
        # A cent more than the bar, because matching it exactly is a tie rather than a win.
        price = int(runner_up_score / winner_share) + 1
    else:
        price = reserve

    price = max(reserve, min(price, winner.bid_cents))

    return {
        "ad": winner,
        "priceCents": price,
        "relevance": round(winner_share, 4),
        "bidders": len(scored),
    }


def broadcast_winner(
    db: DbSession,
    *,
    session=None,
    participant_codes=None,
    salon_topics=None,
    salon_languages=None,
) -> AdBroadcast | None:
    """Run the auction and record the winner's broadcast at the price it won for.

    Deliberately separate from record_broadcast in ad_billing_service, which charges the flat
    rate. That one exists for an ad bought by the broadcast; this one for an ad that bid. Both
    write the same table, and both copy the price onto the row — an invoice must charge what was
    agreed at the moment, not what a setting says later.
    """
    from datetime import datetime, timezone

    from src.services import house_ads

    outcome = run_auction(
        db,
        participant_codes=participant_codes,
        salon_topics=salon_topics,
        salon_languages=salon_languages,
    )

    if outcome is not None:
        ad, price = outcome["ad"], outcome["priceCents"]
    else:
        # Nobody bid, or nobody eligible. The house ad fills the silence rather than leaving a
        # salon with no advertising at all — and it is priced at zero, because invoicing the
        # platform owner for its own advertising would be a real Stripe charge to itself.
        ad = house_ads.fallback_ad(db, salon_languages=salon_languages)
        if ad is None:
            return None
        price = 0
    try:
        row = AdBroadcast(
            ad_id=ad.ad_id,
            advertiser_id=ad.advertiser_id,
            session_id=getattr(session, "id", None),
            salon_name=getattr(session, "livekit_room_name", "") or "",
            amount_cents=price,
            currency=settings.billing_currency,
            broadcast_at=datetime.now(tz=timezone.utc),
        )
        db.add(row)
        ad.number_of_broadcasts_left = ad.number_of_broadcasts_left - 1
        db.commit()
        db.refresh(row)
        logger.info(
            "Ad %s broadcast at %d cents (%s)",
            ad.ad_id,
            price,
            f"{outcome['bidders']} bidder(s)" if outcome else "house ad, no bidders",
        )
        return row
    except Exception:  # noqa: BLE001
        db.rollback()
        logger.warning("Could not record the auction winner", exc_info=True)
        return None
