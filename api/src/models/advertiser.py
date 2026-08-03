"""Advertisers, and the audience each one is willing to pay to reach."""
import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    Numeric,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.database import Base

# JSONB where it exists, plain JSON on the SQLite the tests run against. Lists rather
# than child tables because every one of these is short, read whole, and never joined
# on its own — an advertiser picks a handful of countries, not a taxonomy.
StringList = JSON().with_variant(JSONB(), "postgresql")


class Advertiser(Base):
    """A business wanting its message carried into salons, and who it wants to reach.

    Targeting reads as an intersection: a salon matches when it satisfies every criterion
    the advertiser set. An empty list means "no restriction on this dimension", which is
    why the columns default to [] and are not nullable — NULL and [] would mean the same
    thing while sorting differently in every query, and one of the two would eventually
    be written by accident.

    Three of the four dimensions are matched against participants, not against the salon:
    the audience is the people in the room. The keyword list is the exception — it
    describes what was talked about.

    Encryption at rest is the Aurora cluster's, as everywhere else: KMS covers the
    storage, its snapshots and its backups, and contact_email is readable in clear to
    anyone holding SQL access.
    """

    __tablename__ = "advertisers"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    contact_email: Mapped[str] = mapped_column(String(320), nullable=False)

    # Paused on arrival. An advertiser that started running the moment its row was
    # written would go live before anyone had looked at what it wants to say.
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="paused")

    # ── Where ─────────────────────────────────────────────────────────────────
    # ISO 3166-1 alpha-2, uppercase. Matched against the country a participant was
    # placed in — which is derived from their IP address or their GPS position, and is
    # NOT a column anywhere yet. See the note at the foot of this class.
    target_countries: Mapped[list] = mapped_column(StringList, nullable=False, default=list)
    # ISO 3166-2 subdivisions, for advertisers who want a province rather than a country.
    target_regions: Mapped[list] = mapped_column(StringList, nullable=False, default=list)

    # A circle, for advertisers whose catchment is a neighbourhood rather than a border:
    # a restaurant does not want a province. This can only ever match participants who
    # granted their position — an IP-derived country cannot be tested against a radius of
    # two kilometres with any honesty.
    target_latitude: Mapped[float | None] = mapped_column(Numeric(8, 6), nullable=True)
    target_longitude: Mapped[float | None] = mapped_column(Numeric(9, 6), nullable=True)
    target_radius_km: Mapped[float | None] = mapped_column(Numeric(7, 2), nullable=True)

    # ── Who ───────────────────────────────────────────────────────────────────
    # BCP-47, lowercase. Matched against a participant's most frequent first-heard
    # language across their salons — the mode of salon_events.first_spoken_language, not
    # the language of any single conversation. Someone who holds four salons in French
    # and one in English is a French speaker for targeting.
    target_languages: Mapped[list] = mapped_column(StringList, nullable=False, default=list)

    # ── What ──────────────────────────────────────────────────────────────────
    # Lowercased topic words. Matched by overlap against the ten most frequent keywords
    # of the salons a participant attended: one word in common is a match, since an
    # advertiser listing twenty words is describing a field, not a conjunction.
    #
    # Nothing produces those ten keywords today. See below.
    target_keywords: Mapped[list] = mapped_column(StringList, nullable=False, default=list)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'paused', 'suspended')", name="ck_advertisers_status"
        ),
        # A circle is three numbers or none. Two of the three describes nothing, and a
        # half-written circle would silently match everyone or no one depending on which
        # part of the query read it first.
        CheckConstraint(
            "(target_latitude IS NULL AND target_longitude IS NULL "
            " AND target_radius_km IS NULL) OR "
            "(target_latitude IS NOT NULL AND target_longitude IS NOT NULL "
            " AND target_radius_km IS NOT NULL)",
            name="ck_advertisers_circle_complete",
        ),
        CheckConstraint(
            "target_radius_km IS NULL OR target_radius_km > 0",
            name="ck_advertisers_radius_positive",
        ),
    )


# ─── What this table cannot yet be matched against ───────────────────────────
#
# The columns above are the advertiser's half of the bargain. The participant's half is
# only partly there, and the gap is worth naming here rather than discovering it when
# the first campaign returns everyone or no one:
#
#   target_languages  — WORKS. salon_events.first_spoken_language is populated by the
#                       agent, and the most frequent value per email is one GROUP BY.
#
#   target_countries  — NOT YET. salon_events stores a Plus Code, which is a grid cell
#   target_regions      and not a political boundary. Naming the country or subdivision
#                       a cell falls in needs reverse geocoding, which does not exist
#                       here. These lists can be stored and cannot be applied.
#
#   target_radius_km  — COARSELY, AND ONLY DOWN TO A FEW KILOMETRES. A participant's
#                       position is a cell about five and a half kilometres across, so
#                       the distance available is from the centre of that cell with its
#                       own size as the error bar. A radius under that cannot mean
#                       anything, and a restaurant wanting two kilometres will not get
#                       it. Everyone who declined the location prompt — the common case
#                       — is invisible to a circle at any radius.
#
#   target_keywords   — NOT AT ALL. Nothing in the schema describes what a salon was
#                       about. Conversations are never transcribed or stored, so the
#                       only material available is the source a host supplied: its
#                       summary and its text. Keywords drawn from the source describe
#                       what the salon was *given*, which is a defensible proxy for what
#                       it was about, but it is a proxy and should be labelled as one.
