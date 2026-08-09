"""Advertisers, and the audience each one is willing to pay to reach."""
import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
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

    The language list is matched against participants rather than against the salon: the
    audience is the people in the room. The keyword list is the exception — it describes
    what was talked about. Where an advertiser wants to be heard is said through
    `advertisers_regions`, in cells, and nowhere else.

    Encryption at rest is the Aurora cluster's, as everywhere else: KMS covers the
    storage, its snapshots and its backups, and the contact details are readable in clear
    to anyone holding SQL access. Unlike salon_events, this is business contact
    information rather than personal data about a participant.
    """

    __tablename__ = "advertisers"

    advertiser_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # The business itself. Renamed from `name` when address, phone and website joined it:
    # `name` beside `company` would have been two columns for one idea, and one of them
    # would eventually have been left empty.
    company: Mapped[str] = mapped_column(String(200), nullable=False)

    # How to reach them. The email is required — it is how an advertiser is contacted
    # about their own account — and the rest are not: a business may have no street
    # address worth recording, and asking for a website before there is one invites a
    # placeholder.
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    phone_number: Mapped[str] = mapped_column(String(20), nullable=False, default="")
    address: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    website: Mapped[str] = mapped_column(String(300), nullable=False, default="")

    # Paused on arrival. An advertiser that started running the moment its row was
    # written would go live before anyone had looked at what it wants to say.
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="paused")

    # ── Where ─────────────────────────────────────────────────────────────────
    # Through `advertisers_regions` and nothing else. The JSONB country and subdivision
    # lists, and the circle, were removed in Story 9.2: see the note at the foot of this
    # class.

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

    # Created on the first invoice, not on signup: an advertiser who never runs an ad leaves
    # no trace in Stripe. Same pattern as hosts.
    stripe_customer_id: Mapped[str | None] = mapped_column(String(100), nullable=True)

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
        # An advertiser with no company name and no address to answer at is a row nobody
        # can act on.
        CheckConstraint("trim(company) <> ''", name="ck_advertisers_company_not_blank"),
        CheckConstraint("trim(email) <> ''", name="ck_advertisers_email_not_blank"),
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
#   where             — THROUGH advertisers_regions, which resolves to Open Location Code
#                       cells comparable against salon_events.plus_code as strings.
#
#                       The JSONB target_countries and target_regions lists, and the
#                       target_latitude / target_longitude / target_radius_km circle, were
#                       dropped in Story 9.2. They were storable and never applicable:
#                       salon_events holds a grid cell, not a political boundary, and
#                       naming the country a cell falls in needs reverse geocoding that
#                       does not exist here. The circle failed for a second reason — a
#                       position is a cell about five and a half kilometres across, so a
#                       restaurant asking for two kilometres could never have been served
#                       honestly, and everyone who declined the location prompt was
#                       invisible to it at any radius.
#
#   target_keywords   — NOT AT ALL. Nothing in the schema describes what a salon was
#                       about. Conversations are never transcribed or stored, so the
#                       only material available is the source a host supplied: its
#                       summary and its text. Keywords drawn from the source describe
#                       what the salon was *given*, which is a defensible proxy for what
#                       it was about, but it is a proxy and should be labelled as one.
