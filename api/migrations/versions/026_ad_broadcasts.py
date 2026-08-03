"""Every time an ad was spoken, what it cost, and whether it has been invoiced.

ads.number_of_broadcasts_left destroyed information by consuming it. A counter that only
decrements cannot say how many broadcasts happened, when, or in which salon — so nothing
could invoice an advertiser, report to one, or diagnose an ad burning through its allowance.
Zero was also ambiguous: exhausted, or never purchased?

The price lives on the row because rates change. An invoice must charge what was agreed when
the ad was spoken; reading the setting at billing time would silently reprice history.

stripe_invoice_item_id being NULL is what makes the invoicing run idempotent — it selects
uninvoiced rows, so a run interrupted halfway cannot bill anything twice. Batching matters:
Stripe takes roughly 2.9% plus thirty cents per transaction, so charging a few cents per
broadcast would cost more in fees than it collects.

Deletion of a broadcast ad is blocked rather than cascaded. These rows are the evidence an
advertiser could dispute, and a foreign key that quietly removed them would make history
depend on whether anyone had tidied up.

Revision ID: 026
Revises: 025
Create Date: 2026-08-03
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "026"
down_revision = "025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Advertisers need a Stripe customer before anything can be billed to them. Nullable:
    # one is created on the first invoice, exactly as it is for hosts.
    op.add_column(
        "advertisers", sa.Column("stripe_customer_id", sa.String(100), nullable=True)
    )

    op.create_table(
        "ad_broadcasts",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("ad_id", UUID(as_uuid=True), nullable=False),
        # Denormalised from the ad: this is who gets invoiced, and the run groups by it.
        sa.Column("advertiser_id", UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", UUID(as_uuid=True), nullable=True),
        # Text, so an invoice line can name the salon after the session is gone.
        sa.Column("salon_name", sa.String(100), nullable=False, server_default=""),
        sa.Column("amount_cents", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(10), nullable=False, server_default="usd"),
        sa.Column(
            "broadcast_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("stripe_invoice_item_id", sa.String(100), nullable=True),
        sa.Column("invoiced_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        # RESTRICT on both: an ad or an advertiser with broadcasts cannot be deleted, because
        # the alternative is losing the record that the ad ran.
        sa.ForeignKeyConstraint(["ad_id"], ["ads.ad_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["advertiser_id"], ["advertisers.advertiser_id"], ondelete="RESTRICT"
        ),
        # SET NULL: a salon is ephemeral and may legitimately be removed; losing which room
        # an ad played in must not block that.
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="SET NULL"),
        # A free broadcast is a real case; a negative one is a credit, and credits do not
        # belong in a table of things that happened.
        sa.CheckConstraint("amount_cents >= 0", name="ck_ad_broadcasts_amount"),
        # A row with an invoice item and no timestamp cannot be reconciled; one with a
        # timestamp and no item was never actually billed.
        sa.CheckConstraint(
            "(stripe_invoice_item_id IS NULL AND invoiced_at IS NULL) OR "
            "(stripe_invoice_item_id IS NOT NULL AND invoiced_at IS NOT NULL)",
            name="ck_ad_broadcasts_invoiced_consistent",
        ),
    )

    # The invoicing run's only query: uninvoiced rows, grouped by advertiser. Partial, because
    # invoiced rows are the vast majority once the platform has been running a while.
    op.create_index(
        "ix_ad_broadcasts_uninvoiced",
        "ad_broadcasts",
        ["advertiser_id"],
        postgresql_where=sa.text("stripe_invoice_item_id IS NULL"),
    )
    # Reporting to an advertiser about one ad.
    op.create_index("ix_ad_broadcasts_ad_id", "ad_broadcasts", ["ad_id", "broadcast_at"])


def downgrade() -> None:
    op.drop_index("ix_ad_broadcasts_ad_id", table_name="ad_broadcasts")
    op.drop_index("ix_ad_broadcasts_uninvoiced", table_name="ad_broadcasts")
    op.drop_table("ad_broadcasts")
    op.drop_column("advertisers", "stripe_customer_id")
