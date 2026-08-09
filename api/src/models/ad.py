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

    # The most this ad will pay for one broadcast. Zero means it does not bid at all — an ad
    # can exist, be bought by broadcast count, and sit out of the auction.
    #
    # It is a ceiling, never the price. The winner pays the least it would have taken to beat
    # the runner-up, because a first-price auction is played rather than bid: everyone shades
    # downwards guessing at the others, and the ranking stops reflecting who values the salon.
    bid_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

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

    # Roughly how long the creative takes to say. Indicative and never contractual: the same
    # text translated runs to different lengths in different languages, so what counts in an
    # interpreter's lag is the duration actually rendered, not this. Zero means nobody
    # estimated it, which is more honest than a made-up figure.
    indicative_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

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
        CheckConstraint("bid_cents >= 0", name="ck_ads_bid_not_negative"),
        CheckConstraint(
            "indicative_seconds >= 0", name="ck_ads_indicative_seconds_not_negative"
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


class AdLanguage(Base):
    """One language an ad is meant to be heard in.

    A targeting criterion, at the same level as a cell: it names the languages spoken by the
    humans the ad will be read to, and not a property of the text — the creative is written
    once in `spoken_language` and translated for whoever is listening, exactly as a turn of
    speech is.

    A row per language rather than a list on the ad, matching `ads_regions`: one ad addresses
    several regions and several languages without a row per combination.

    An ad with no rows here is unrestricted by language, the same way an advertiser's empty
    list means "no restriction on this dimension". An ad with no rows in either table is
    generic, and generic is the fallback served when nothing matches a participant's segment.
    """

    __tablename__ = "ads_languages"

    ad_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ads.ad_id", ondelete="CASCADE"), primary_key=True
    )
    # BCP-47, lowercase, as everywhere else.
    language: Mapped[str] = mapped_column(String(10), primary_key=True)

    __table_args__ = (
        CheckConstraint("trim(language) <> ''", name="ck_ads_languages_not_blank"),
    )


class AdSubstitution(Base):
    """Wording an advertiser requires word for word, in one language.

    A brand form or a legal order. When one exists for the language a participant is heard
    in, it replaces the translated creative and no interpretation step may touch it — no
    disfluency cleaning, no condensation, no shortening for lag. All three would alter
    wording supplied precisely because it must not be altered, which is the whole of what a
    substitution guarantees.

    One language only. The others carry on being translated from the canonical creative, so
    an advertiser constrained in French is not forced to author every other language too.
    """

    __tablename__ = "ads_substitutions"

    ad_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ads.ad_id", ondelete="CASCADE"), primary_key=True
    )
    language: Mapped[str] = mapped_column(String(10), primary_key=True)

    # Text, and bounded by the same CHECK as the pitch it stands in for.
    text: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        CheckConstraint(
            "trim(language) <> ''", name="ck_ads_substitutions_language_not_blank"
        ),
        # A blank substitution would be read out as a silence exactly where the canonical
        # creative would have been said — worse than having no substitution at all.
        CheckConstraint("trim(text) <> ''", name="ck_ads_substitutions_text_not_blank"),
        CheckConstraint(
            f"length(text) BETWEEN 1 AND {SALES_PITCH_MAX}",
            name="ck_ads_substitutions_text_length",
        ),
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
#   ads_languages     WORKS. The languages the ad is meant to be heard in, a targeting
#                     criterion at the same level as a cell.
#
#   GEOGRAPHY, TWO WAYS. There were three, and the third is gone as of Story 9.2:
#
#     ads_regions                  cells listed directly on the ad
#     advertisers_regions          named regions bought by the advertiser, resolving to
#       + region_google_plus_codes cells through the region
#
#   The two answer the same question at different grains — an ad covering one street
#   versus an advertiser covering a city — and both resolve to strings comparable against
#   salon_events.plus_code with no geometry involved. The JSONB lists and circle that used
#   to sit beside them on `advertisers` never had data behind them and never could: naming
#   the country a cell falls in needs reverse geocoding that does not exist here.
