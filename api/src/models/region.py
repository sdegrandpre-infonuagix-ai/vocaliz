"""Named places, and the grid cells that make them up.

A region is whatever an advertiser thinks of as one place — a city, a borough, a
catchment. It exists so that geography can be named once and reused: an advertiser picks
"Montréal" rather than restating forty Plus Codes, and the same forty are corrected in one
place when they turn out to be wrong.

The cells are the same ones recorded for participants, at the same precision. That is the
whole point of the indirection: a region resolves to a set of strings that can be compared
directly against salon_events.plus_code, with no geometry and no reverse geocoding.
"""
import uuid

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.database import Base


class Region(Base):
    """One named place.

    Encryption at rest is the cluster's, as everywhere else — though nothing here is
    personal data: a region is a fact about the world, not about anyone.
    """

    __tablename__ = "regions"

    region_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # Unique, because two regions with the same name are one region entered twice, and an
    # advertiser choosing from a list would have no way to tell them apart.
    region_name: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)

    # Nullable on purpose: a region is usable without knowing how many people live in it,
    # and a made-up figure would be worse than an absent one. BigInteger because an
    # Integer caps at about 2.1 billion, which two of the world's regions exceed.
    population: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    __table_args__ = (
        CheckConstraint("trim(region_name) <> ''", name="ck_regions_name_not_blank"),
        CheckConstraint("population IS NULL OR population >= 0", name="ck_regions_population"),
    )


class RegionGooglePlusCode(Base):
    """One grid cell belonging to one region.

    A row per cell rather than a list on the region: a city is hundreds of them, they are
    joined against participant positions, and a JSON array cannot be indexed for that.

    Nothing stops a cell belonging to two regions, and that is deliberate — a borough sits
    inside a city, and an advertiser may want either.
    """

    __tablename__ = "region_google_plus_codes"

    region_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("regions.region_id", ondelete="CASCADE"),
        primary_key=True,
    )
    google_plus_code: Mapped[str] = mapped_column(String(16), primary_key=True)

    __table_args__ = (
        CheckConstraint(
            "trim(google_plus_code) <> ''", name="ck_region_codes_not_blank"
        ),
    )


class AdvertiserRegion(Base):
    """Which advertiser has bought which region.

    A plain join table: an advertiser covers several regions, and a region carries several
    advertisers. Nothing else belongs here — a price or a date would be a property of the
    purchase, not of the pairing, and there is no purchase yet.
    """

    __tablename__ = "advertisers_regions"

    advertiser_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("advertisers.advertiser_id", ondelete="CASCADE"),
        primary_key=True,
    )
    region_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("regions.region_id", ondelete="CASCADE"),
        primary_key=True,
    )
