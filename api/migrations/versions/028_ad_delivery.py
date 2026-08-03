"""A broadcast is reserved when the salon opens, and billed only once it is spoken.

The auction now runs at salon creation, so the pitch is in the agent's hands before it is
needed and no network round trip interrupts a conversation. That creates a gap the previous
design did not have: between reserving an ad and saying it, the host may close their tab or the
worker may die — and charging an advertiser for a sentence nobody heard is the one outcome an
advertising system must not produce.

delivered_at is what closes it. A row with NULL was reserved and never spoken: it is kept, so
the gap is measurable rather than invisible, and the invoicing run ignores it. An allowance is
likewise only spent on delivery.

Revision ID: 028
Revises: 027
Create Date: 2026-08-03
"""
from alembic import op
import sqlalchemy as sa

revision = "028"
down_revision = "027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "ad_broadcasts", sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True)
    )
    # Everything recorded before this migration was written at the moment it was spoken, so it
    # was delivered by definition. Backfilled rather than left NULL, which would silently write
    # off every broadcast already earned.
    op.execute("UPDATE ad_broadcasts SET delivered_at = broadcast_at")

    # An invoice must never carry a reservation. The constraint is the guarantee: a row with a
    # Stripe item but no delivery is a charge for something nobody heard.
    op.create_check_constraint(
        "ck_ad_broadcasts_billed_only_if_delivered",
        "ad_broadcasts",
        "stripe_invoice_item_id IS NULL OR delivered_at IS NOT NULL",
    )

    # The invoicing run's query becomes "delivered and not yet billed".
    op.drop_index("ix_ad_broadcasts_uninvoiced", table_name="ad_broadcasts")
    op.create_index(
        "ix_ad_broadcasts_billable",
        "ad_broadcasts",
        ["advertiser_id"],
        postgresql_where=sa.text(
            "stripe_invoice_item_id IS NULL AND delivered_at IS NOT NULL"
        ),
    )


def downgrade() -> None:
    op.drop_index("ix_ad_broadcasts_billable", table_name="ad_broadcasts")
    op.create_index(
        "ix_ad_broadcasts_uninvoiced",
        "ad_broadcasts",
        ["advertiser_id"],
        postgresql_where=sa.text("stripe_invoice_item_id IS NULL"),
    )
    op.drop_constraint(
        "ck_ad_broadcasts_billed_only_if_delivered", "ad_broadcasts", type_="check"
    )
    op.drop_column("ad_broadcasts", "delivered_at")
