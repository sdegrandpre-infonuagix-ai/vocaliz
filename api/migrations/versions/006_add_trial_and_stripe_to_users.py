"""Add trial_seconds_used and Stripe billing columns to users table.

Revision ID: 006
Revises: 005
Create Date: 2026-07-29
"""
from alembic import op
import sqlalchemy as sa

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("trial_seconds_used", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "users",
        sa.Column("stripe_customer_id", sa.String(50), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("stripe_payment_method_id", sa.String(50), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "stripe_payment_method_id")
    op.drop_column("users", "stripe_customer_id")
    op.drop_column("users", "trial_seconds_used")
