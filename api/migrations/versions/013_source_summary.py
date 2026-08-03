"""Give the agent a summary instead of the first 2 500 characters.

A document was accepted up to 5 MB, extracted up to 50 000 characters, stored in full —
and then handed to the agent as its opening page and a half. A forty-page PDF became its
table of contents, silently, while the host was told the whole thing had been added.

The summary replaces that truncation. The full text stays where it is, searchable, for the
questions a summary cannot answer.

Nullable, and null is a working state: when the summariser is unreachable or unconfigured
the agent falls back to the old truncation, which is worse but still a conversation.

Revision ID: 013
Revises: 012
Create Date: 2026-08-03
"""
from alembic import op
import sqlalchemy as sa

revision = "013"
down_revision = "012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("sessions", sa.Column("source_summary", sa.Text(), nullable=True))
    op.add_column("session_sources", sa.Column("source_summary", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("session_sources", "source_summary")
    op.drop_column("sessions", "source_summary")
