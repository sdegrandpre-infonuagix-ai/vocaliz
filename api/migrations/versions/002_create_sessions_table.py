"""create sessions table

Revision ID: 002
Revises: 001
Create Date: 2026-07-28
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("host_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("livekit_room_name", sa.String(100), unique=True, nullable=False),
        sa.Column("source_type", sa.String(20), nullable=False),
        sa.Column("source_url", sa.Text, nullable=True),
        sa.Column("source_filename", sa.String(255), nullable=True),
        sa.Column("source_content", sa.Text, nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_sessions_host_user_id", "sessions", ["host_user_id"])


def downgrade() -> None:
    op.drop_index("ix_sessions_host_user_id", table_name="sessions")
    op.drop_table("sessions")
