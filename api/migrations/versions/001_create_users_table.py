"""create users table

Revision ID: 001
Revises:
Create Date: 2026-07-28
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("phone_number", sa.String(20), unique=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("otp_code", sa.String(10), nullable=True),
        sa.Column("otp_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("otp_attempts", sa.Integer(), nullable=False, server_default="0"),
        # trial_seconds_used / stripe_* are added by migration 006, detected_language
        # by 005 — do not duplicate them here or upgrade head breaks on a fresh DB.
    )
    op.create_index("ix_users_phone_number", "users", ["phone_number"])


def downgrade() -> None:
    op.drop_index("ix_users_phone_number", table_name="users")
    op.drop_table("users")
