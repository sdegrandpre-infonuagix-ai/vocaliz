"""Advertisers and the audience each one wants to reach.

Targeting is stored as JSONB lists on the advertiser row rather than in child tables:
each list is short, always read whole, and never joined on by itself. An empty list means
the dimension is unrestricted, which is why the columns are NOT NULL with a [] default —
NULL and [] would carry the same meaning while behaving differently in every query.

Two of the four dimensions cannot be matched against anything yet. salon_events stores a
raw IP address and, sometimes, a position; neither is a country, and resolving one needs
a GeoIP database or a lookup service that does not exist here. Nothing at all describes
what a salon was about, so the keyword list has no counterpart to be compared with. Both
are storable today and applicable later; the model file spells out what each would need.

Encryption at rest is the cluster's, as for salon_events and uploaded_data.

Revision ID: 014
Revises: 013
Create Date: 2026-08-03
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "014"
down_revision = "013"
branch_labels = None
depends_on = None

_EMPTY_LIST = sa.text("'[]'::jsonb")


def upgrade() -> None:
    op.create_table(
        "advertisers",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("contact_email", sa.String(320), nullable=False),
        # Paused on arrival: nothing goes live before someone has read what it says.
        sa.Column("status", sa.String(20), nullable=False, server_default="paused"),
        # ISO 3166-1 alpha-2 and ISO 3166-2. Storable now, matchable once an address or
        # a coordinate can be turned into a place.
        sa.Column("target_countries", JSONB(), nullable=False, server_default=_EMPTY_LIST),
        sa.Column("target_regions", JSONB(), nullable=False, server_default=_EMPTY_LIST),
        # A circle, for a catchment smaller than a border. Only ever matches participants
        # who granted their position.
        sa.Column("target_latitude", sa.Numeric(8, 6), nullable=True),
        sa.Column("target_longitude", sa.Numeric(9, 6), nullable=True),
        sa.Column("target_radius_km", sa.Numeric(7, 2), nullable=True),
        # BCP-47. The one dimension with data behind it today.
        sa.Column("target_languages", JSONB(), nullable=False, server_default=_EMPTY_LIST),
        # Topic words, matched by overlap. Nothing produces the participant side yet.
        sa.Column("target_keywords", JSONB(), nullable=False, server_default=_EMPTY_LIST),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "status IN ('active', 'paused', 'suspended')", name="ck_advertisers_status"
        ),
        # Three numbers or none. Two of the three describes nothing.
        sa.CheckConstraint(
            "(target_latitude IS NULL AND target_longitude IS NULL "
            " AND target_radius_km IS NULL) OR "
            "(target_latitude IS NOT NULL AND target_longitude IS NOT NULL "
            " AND target_radius_km IS NOT NULL)",
            name="ck_advertisers_circle_complete",
        ),
        sa.CheckConstraint(
            "target_radius_km IS NULL OR target_radius_km > 0",
            name="ck_advertisers_radius_positive",
        ),
    )

    # Selecting the campaigns in play is the query this table exists to serve, and it
    # always begins by discarding everything not running.
    op.create_index("ix_advertisers_status", "advertisers", ["status"])

    # GIN, because the question asked of these columns is containment — does this list
    # hold the participant's language, does it share a word with their topics — and a
    # B-tree on a JSONB value cannot answer it.
    for column in ("target_countries", "target_regions", "target_languages", "target_keywords"):
        op.create_index(
            f"ix_advertisers_{column}",
            "advertisers",
            [column],
            postgresql_using="gin",
        )


def downgrade() -> None:
    for column in ("target_keywords", "target_languages", "target_regions", "target_countries"):
        op.drop_index(f"ix_advertisers_{column}", table_name="advertisers")
    op.drop_index("ix_advertisers_status", table_name="advertisers")
    op.drop_table("advertisers")
