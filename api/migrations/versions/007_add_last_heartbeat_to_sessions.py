"""Add last_heartbeat_at column to sessions table for precise metering (Story 4.2).

Revision ID: 007
Revises: 006
Create Date: 2026-07-29
"""
from alembic import op
import sqlalchemy as sa

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "sessions",
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("sessions", "last_heartbeat_at")
