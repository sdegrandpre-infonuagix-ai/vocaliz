"""Advertiser contact details, ad ownership, and named regions.

Three things at once, because they are one change: an advertiser becomes a business you
can actually reach, an ad belongs to one, and geography gets a name instead of being
restated cell by cell.

RENAMES rather than additions on advertisers. The table already had `id`, `name` and
`contact_email`; adding `company` and `email` beside them would have been two columns for
each idea, and one of each pair would eventually have been left empty. `id` becomes
`advertiser_id` to match ad_id and region_id. The table is empty in production, so the
rename costs nothing.

REGIONS exist so geography can be named once and reused. An advertiser picks "Montréal"
rather than restating forty Plus Codes, and those forty are corrected in one place when
they turn out to be wrong. A region resolves to a set of strings comparable directly
against salon_events.plus_code — no geometry, no reverse geocoding.

Revision ID: 019
Revises: 018
Create Date: 2026-08-03
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "019"
down_revision = "018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── advertisers: a business you can reach ─────────────────────────────────
    op.alter_column("advertisers", "id", new_column_name="advertiser_id")
    op.alter_column("advertisers", "name", new_column_name="company")
    op.alter_column("advertisers", "contact_email", new_column_name="email")

    # Not required. A business may have no street address worth recording, and demanding
    # a website before there is one invites a placeholder that is worse than blank.
    op.add_column(
        "advertisers",
        sa.Column("phone_number", sa.String(20), nullable=False, server_default=""),
    )
    op.add_column(
        "advertisers", sa.Column("address", sa.String(300), nullable=False, server_default="")
    )
    op.add_column(
        "advertisers", sa.Column("website", sa.String(300), nullable=False, server_default="")
    )

    # An advertiser with no company name and no address to answer at is a row nobody can
    # act on.
    op.create_check_constraint(
        "ck_advertisers_company_not_blank", "advertisers", "trim(company) <> ''"
    )
    op.create_check_constraint(
        "ck_advertisers_email_not_blank", "advertisers", "trim(email) <> ''"
    )

    # ── ads: an owner ─────────────────────────────────────────────────────────
    # NOT NULL with no default and no backfill: the table was created one migration ago
    # and is empty. An ad with no owner is one nobody can be invoiced for or held
    # responsible for, so nullable was never the right shape.
    op.add_column("ads", sa.Column("advertiser_id", UUID(as_uuid=True), nullable=False))
    op.create_foreign_key(
        "fk_ads_advertiser",
        "ads",
        "advertisers",
        ["advertiser_id"],
        ["advertiser_id"],
        ondelete="CASCADE",
    )
    op.create_index("ix_ads_advertiser_id", "ads", ["advertiser_id"])

    # ── regions ───────────────────────────────────────────────────────────────
    op.create_table(
        "regions",
        sa.Column("region_id", UUID(as_uuid=True), nullable=False),
        # Unique: two regions with the same name are one region entered twice, and an
        # advertiser choosing from a list could not tell them apart.
        sa.Column("region_name", sa.String(200), nullable=False),
        # Nullable. A region is usable without knowing how many people live in it, and an
        # invented figure would be worse than an absent one. BigInteger because Integer
        # caps around 2.1 billion, which two of the world's regions exceed.
        sa.Column("population", sa.BigInteger(), nullable=True),
        sa.PrimaryKeyConstraint("region_id"),
        sa.UniqueConstraint("region_name", name="uq_regions_name"),
        sa.CheckConstraint("trim(region_name) <> ''", name="ck_regions_name_not_blank"),
        sa.CheckConstraint(
            "population IS NULL OR population >= 0", name="ck_regions_population"
        ),
    )

    op.create_table(
        "region_google_plus_codes",
        sa.Column("region_id", UUID(as_uuid=True), nullable=False),
        sa.Column("google_plus_code", sa.String(16), nullable=False),
        sa.PrimaryKeyConstraint("region_id", "google_plus_code"),
        sa.ForeignKeyConstraint(
            ["region_id"], ["regions.region_id"], ondelete="CASCADE"
        ),
        sa.CheckConstraint("trim(google_plus_code) <> ''", name="ck_region_codes_not_blank"),
    )
    # The question actually asked: which regions contain this cell. The primary key leads
    # with region_id and cannot serve it.
    op.create_index(
        "ix_region_codes_code", "region_google_plus_codes", ["google_plus_code"]
    )

    op.create_table(
        "advertisers_regions",
        sa.Column("advertiser_id", UUID(as_uuid=True), nullable=False),
        sa.Column("region_id", UUID(as_uuid=True), nullable=False),
        sa.PrimaryKeyConstraint("advertiser_id", "region_id"),
        sa.ForeignKeyConstraint(
            ["advertiser_id"], ["advertisers.advertiser_id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["region_id"], ["regions.region_id"], ondelete="CASCADE"
        ),
    )
    op.create_index("ix_advertisers_regions_region", "advertisers_regions", ["region_id"])


def downgrade() -> None:
    op.drop_index("ix_advertisers_regions_region", table_name="advertisers_regions")
    op.drop_table("advertisers_regions")
    op.drop_index("ix_region_codes_code", table_name="region_google_plus_codes")
    op.drop_table("region_google_plus_codes")
    op.drop_table("regions")

    op.drop_index("ix_ads_advertiser_id", table_name="ads")
    op.drop_constraint("fk_ads_advertiser", "ads", type_="foreignkey")
    op.drop_column("ads", "advertiser_id")

    op.drop_constraint("ck_advertisers_email_not_blank", "advertisers", type_="check")
    op.drop_constraint("ck_advertisers_company_not_blank", "advertisers", type_="check")
    op.drop_column("advertisers", "website")
    op.drop_column("advertisers", "address")
    op.drop_column("advertisers", "phone_number")
    op.alter_column("advertisers", "email", new_column_name="contact_email")
    op.alter_column("advertisers", "company", new_column_name="name")
    op.alter_column("advertisers", "advertiser_id", new_column_name="id")
