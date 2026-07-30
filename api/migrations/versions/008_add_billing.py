"""Add billed_seconds to users and create billing_events table.

Supports Story 4.4 — per-hour billing beyond the free trial.

Revision ID: 008
Revises: 007
Create Date: 2026-07-29
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("billed_seconds", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_table(
        "billing_events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "host_user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "session_id",
            UUID(as_uuid=True),
            sa.ForeignKey("sessions.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column("billable_seconds", sa.Integer(), nullable=False),
        sa.Column("amount_cents", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(10), nullable=False, server_default="usd"),
        sa.Column("stripe_payment_intent_id", sa.String(100), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("billing_events")
    op.drop_column("users", "billed_seconds")
