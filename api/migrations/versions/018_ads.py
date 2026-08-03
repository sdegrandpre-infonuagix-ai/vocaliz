"""Advertisements, and the places each one may be heard in.

Two tables rather than one. An advertiser covering a city names several cells, and a set
of rows can be indexed and joined where a JSON array of them cannot.

The cells are Open Location Codes at the same length as the ones recorded for
participants — six digits, about five and a half kilometres. This matters more than it
looks: a code is compared as a string, so a finer targeting code matches nothing at all
rather than matching the cell that contains it. "87Q8GC2M+" and "87Q8GC00+" are simply
different values.

Encryption at rest is the cluster's, as everywhere else.

Revision ID: 018
Revises: 017
Create Date: 2026-08-03
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "018"
down_revision = "017"
branch_labels = None
depends_on = None

SALES_PITCH_MAX = 2000


def upgrade() -> None:
    op.create_table(
        "ads",
        sa.Column("ad_id", UUID(as_uuid=True), nullable=False),
        # Text with a CHECK rather than varchar(2000): the constraint reports a clear
        # violation where an overflow surfaces as a driver error nobody reads.
        sa.Column("sales_pitch", sa.Text(), nullable=False),
        # BCP-47. The language the pitch was authored in, not necessarily the one it will
        # be heard in — the agent renders it for whoever is listening.
        sa.Column("spoken_language", sa.String(10), nullable=False, server_default="en"),
        # Decremented per broadcast. Zero means exhausted, not disabled.
        sa.Column(
            "number_of_broadcasts_left", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("topic", sa.String(200), nullable=False, server_default=""),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("ad_id"),
        sa.CheckConstraint(
            f"length(sales_pitch) BETWEEN 1 AND {SALES_PITCH_MAX}",
            name="ck_ads_sales_pitch_length",
        ),
        # An empty pitch is not an ad, and a blank one would be broadcast as silence.
        sa.CheckConstraint("trim(sales_pitch) <> ''", name="ck_ads_sales_pitch_not_blank"),
        # What stops a concurrent decrement from spending a broadcast that was not there.
        sa.CheckConstraint(
            "number_of_broadcasts_left >= 0", name="ck_ads_broadcasts_not_negative"
        ),
    )
    # Choosing what to broadcast begins by discarding everything exhausted.
    op.create_index("ix_ads_broadcasts_left", "ads", ["number_of_broadcasts_left"])
    op.create_index("ix_ads_spoken_language", "ads", ["spoken_language"])

    op.create_table(
        "ads_regions",
        sa.Column("ad_id", UUID(as_uuid=True), nullable=False),
        sa.Column("google_plus_code", sa.String(16), nullable=False),
        sa.PrimaryKeyConstraint("ad_id", "google_plus_code"),
        sa.ForeignKeyConstraint(["ad_id"], ["ads.ad_id"], ondelete="CASCADE"),
        sa.CheckConstraint(
            "trim(google_plus_code) <> ''", name="ck_ads_regions_code_not_blank"
        ),
    )
    # The question actually asked of this table: which ads may be heard in this cell.
    # The primary key leads with ad_id and cannot serve it.
    op.create_index("ix_ads_regions_code", "ads_regions", ["google_plus_code"])


def downgrade() -> None:
    op.drop_index("ix_ads_regions_code", table_name="ads_regions")
    op.drop_table("ads_regions")
    op.drop_index("ix_ads_spoken_language", table_name="ads")
    op.drop_index("ix_ads_broadcasts_left", table_name="ads")
    op.drop_table("ads")
