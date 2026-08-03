"""The platform's own advertising, in French and English.

House ads: Vocaliz advertising the company that built it. They exist because an auction with no
bidders plays nothing, and a salon that never mentions Infonuagix.ai gives no visible reason for
an advertiser to enquire.

WHY THEY ARE FREE. An ad is invoiced to its advertiser, and here the advertiser is the platform
owner — the daily run would create a real Stripe invoice, with real per-transaction fees,
addressed to themselves. Absurd rather than dangerous, and avoidable: a house ad is priced at
zero, and invoice_advertiser already skips zero-amount broadcasts. The broadcast is still
recorded, so the count and the reporting are true.

WHY THE COPY IS SHORT AND MAKES NO CLAIMS. Two sentences that say who built this and how to
reach them. Anything more specific about what Infonuagix.ai sells would be marketing written by
somebody who does not know the business — the sort of text that reads as filler and stays in
production for a year. It is meant to be replaced.
"""
import logging

from sqlalchemy.orm import Session as DbSession

from src.models.ad import Ad
from src.models.advertiser import Advertiser

logger = logging.getLogger(__name__)

HOUSE_EMAIL = "ads@infonuagix.ai"
HOUSE_COMPANY = "Infonuagix.ai"
HOUSE_WEBSITE = "https://infonuagix.ai"

# Enough that nobody has to think about topping them up while the platform is being tested, and
# not so many that a bug spends a fortune of nothing.
HOUSE_BROADCASTS = 100000

# No topic, so the ad matches whatever a salon is about. Not laziness: a house ad exists to be
# heard when nothing else bids, and a topic would exclude it from exactly those salons.
HOUSE_TOPIC = ""

PITCHES = {
    "en": (
        "Vocaliz was built by Infonuagix.ai. If your business would like to be heard in "
        "conversations like this one, get in touch at infonuagix.ai."
    ),
    "fr": (
        "Vocaliz a été conçu par Infonuagix.ai. Si votre entreprise souhaite se faire entendre "
        "dans des conversations comme celle-ci, écrivez-nous à infonuagix.ai."
    ),
}


def seed(db: DbSession) -> dict:
    """Create or update the house advertiser and its two ads. Idempotent.

    Matched on the advertiser's email and each ad's language, so running this twice changes
    nothing and running it after the copy has been edited restores the copy. That last part is
    deliberate: this function is the definition of what a house ad says, not a one-time insert
    somebody later has to remember editing.
    """
    advertiser = (
        db.query(Advertiser).filter(Advertiser.email == HOUSE_EMAIL).first()
    )
    created_advertiser = advertiser is None
    if advertiser is None:
        advertiser = Advertiser(
            company=HOUSE_COMPANY,
            email=HOUSE_EMAIL,
            website=HOUSE_WEBSITE,
            status="active",
        )
        db.add(advertiser)
        db.commit()
        db.refresh(advertiser)

    touched = []
    for language, pitch in PITCHES.items():
        ad = (
            db.query(Ad)
            .filter(
                Ad.advertiser_id == advertiser.advertiser_id,
                Ad.spoken_language == language,
            )
            .first()
        )
        if ad is None:
            ad = Ad(
                advertiser_id=advertiser.advertiser_id,
                spoken_language=language,
                topic=HOUSE_TOPIC,
            )
            db.add(ad)
            touched.append(f"created:{language}")
        else:
            touched.append(f"updated:{language}")

        ad.sales_pitch = pitch
        # Priced at zero, and the reason is above: invoicing the platform owner for its own
        # advertising would produce a real Stripe charge with real fees, addressed to itself.
        #
        # Zero also means this ad never enters the auction — bid_cents must clear the reserve —
        # so a paying advertiser is never outbid by the house. The house ad plays only when the
        # auction has no winner at all, which is exactly when it should.
        ad.bid_cents = 0
        ad.number_of_broadcasts_left = HOUSE_BROADCASTS

    db.commit()
    logger.info("House ads seeded: %s", ", ".join(touched))
    return {
        "status": "ok",
        "advertiser": "created" if created_advertiser else "existing",
        "ads": touched,
    }


def fallback_ad(db: DbSession, salon_languages=None) -> Ad | None:
    """The house ad to speak when the auction produced no winner.

    Chosen by language: the one written for a language somebody here speaks, falling back to
    English. The agent renders any pitch in the listener's language anyway, so this is about
    which wording was authored for whom rather than about comprehension.

    Returns None when the house ads have not been seeded. A salon then simply hears no
    advertising, which is what happened before they existed.
    """
    wanted = [str(lang).split("-")[0].lower() for lang in (salon_languages or []) if lang]

    try:
        advertiser = db.query(Advertiser).filter(Advertiser.email == HOUSE_EMAIL).first()
        if advertiser is None:
            return None
        ads = (
            db.query(Ad)
            .filter(
                Ad.advertiser_id == advertiser.advertiser_id,
                Ad.number_of_broadcasts_left > 0,
            )
            .all()
        )
    except Exception:  # noqa: BLE001
        logger.warning("Could not read the house ads", exc_info=True)
        return None

    if not ads:
        return None

    by_language = {ad.spoken_language: ad for ad in ads}
    for language in wanted:
        if language in by_language:
            return by_language[language]
    return by_language.get("en") or ads[0]
