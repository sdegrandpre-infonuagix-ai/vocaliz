"""Advertisements, and the places each one is meant to be heard in."""
import uuid

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.database import Base

# Two thousand characters is roughly three minutes of speech. That is long for something
# said aloud in the middle of someone else's conversation, and the limit exists to bound
# the column rather than to suggest the whole of it should be used.
SALES_PITCH_MAX = 2000


class Ad(Base):
    """One thing to say, in one language, a bounded number of times.

    The pitch is stored as written, not as a script the agent must read verbatim: the
    agent speaks it in the participant's language and at the participant's register, so
    what matters is that the substance and the claims are exactly what the advertiser
    supplied.

    Encryption at rest is the Aurora cluster's, as everywhere else.
    """

    __tablename__ = "ads"

    ad_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # Who is paying for it. Required: an ad with no owner is one nobody can be invoiced
    # for, asked about, or held responsible for. CASCADE because an advertiser removed
    # from the platform should not leave its claims behind, still eligible to be spoken.
    advertiser_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("advertisers.advertiser_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Text rather than String(2000): the length is enforced by a CHECK, which reports a
    # clear violation, where a varchar overflow surfaces as a driver error nobody reads.
    sales_pitch: Mapped[str] = mapped_column(Text, nullable=False)

    # BCP-47. The language the pitch was written in, which is not necessarily the language
    # it will be heard in — the agent renders it for whoever is listening. Kept because a
    # pitch written in French carries assumptions a Spanish listener may not share, and an
    # advertiser is entitled to know which version was authored.
    spoken_language: Mapped[str] = mapped_column(String(10), nullable=False, default="en")

    # Decremented once per broadcast. Zero means exhausted, not disabled: an ad that has
    # been heard its full count has done what it was paid for, and the row is kept so the
    # history survives. Never negative — the CHECK is what stops a concurrent decrement
    # from spending a broadcast that was not there.
    number_of_broadcasts_left: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )

    # What the ad is about, in the advertiser's own words. Matched against what a salon
    # discussed — which nothing in the schema records yet. See the note at the foot of
    # this module.
    topic: Mapped[str] = mapped_column(String(200), nullable=False, default="")

    created_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # length() and trim() rather than char_length() and btrim(): the first pair exists on
    # both Postgres and the SQLite the tests run against, and a constraint that cannot be
    # evaluated in tests is a constraint nobody has checked.
    __table_args__ = (
        CheckConstraint(
            f"length(sales_pitch) BETWEEN 1 AND {SALES_PITCH_MAX}",
            name="ck_ads_sales_pitch_length",
        ),
        # An empty pitch is not an ad, and a space-only one would be broadcast as silence.
        # Note the limit: trim() strips spaces and nothing else, on Postgres as much as on
        # SQLite, so a pitch made of tabs and newlines passes this. Whatever input path
        # eventually creates an ad has to reject that itself.
        CheckConstraint("trim(sales_pitch) <> ''", name="ck_ads_sales_pitch_not_blank"),
        CheckConstraint(
            "number_of_broadcasts_left >= 0", name="ck_ads_broadcasts_not_negative"
        ),
    )


class AdRegion(Base):
    """One place an ad may be heard in, as an Open Location Code cell.

    A row per cell rather than a list on the ad: an advertiser covering a city names
    several, and a set of rows can be indexed and joined where a JSON array of them
    cannot.

    The codes must be at the same precision as the ones recorded for participants —
    six digits, about five and a half kilometres. A finer code would never match: a cell
    is compared as a string, so "87Q8GC2M+" and "87Q8GC00+" are simply different values
    even though one contains the other geographically.
    """

    __tablename__ = "ads_regions"

    ad_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ads.ad_id", ondelete="CASCADE"), primary_key=True
    )
    google_plus_code: Mapped[str] = mapped_column(String(16), primary_key=True)

    __table_args__ = (
        CheckConstraint("trim(google_plus_code) <> ''", name="ck_ads_regions_code_not_blank"),
    )


# ─── What these tables are not yet wired to ──────────────────────────────────
#
#   ads_regions       WORKS against salon_events.plus_code, provided the codes are stored
#                     at the same length. Both sides are six digits today; a mismatch
#                     silently matches nothing rather than failing.
#
#   spoken_language   WORKS against salon_events.first_spoken_language.
#
#   topic             NOT YET. Nothing in the schema records what a salon discussed.
#                     Conversations are transcribed now, so the material exists — but
#                     turning a transcript into topics is a step nobody has built, and
#                     using conversation content to place advertising is a consent
#                     question well beyond storing it for translation.
#
#   owner             PRESENT. advertiser_id ties an ad to its advertiser, and through
#                     advertisers_regions to the named regions that advertiser bought.
#
#   GEOGRAPHY, THREE WAYS. There are now three ways to say where an ad may be heard, and
#   that is one too many:
#
#     ads_regions                  cells listed directly on the ad
#     advertisers_regions          named regions bought by the advertiser, resolving to
#       + region_google_plus_codes cells through the region
#     advertisers.target_countries the original JSONB lists and circle — which never had
#       target_regions, circle     any data behind them, because naming the country a
#                                  cell falls in needs reverse geocoding that does not
#                                  exist here
#
#   The third should go. The first two answer the same question at different grains — an
#   ad covering one street versus an advertiser covering a city — and both resolve to
#   strings comparable against salon_events.plus_code with no geometry involved.
