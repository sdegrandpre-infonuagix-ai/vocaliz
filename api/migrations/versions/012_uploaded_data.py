"""Accounting for the sources given to each salon.

One row per source handed to a salon's agent, with its size. The schema records sources in
two places and measures them in neither — a session's first source on the sessions row,
later ones in session_sources — so nothing could answer what a conversation was fed.

Nothing here drives behaviour. It exists to be read.

This was briefly designed as a cross-salon cache keyed on xAI file ids, to avoid
re-embedding documents. That was dropped: a salon has one source and lasts ten minutes, so
there is no corpus to retrieve from. content_hash survives because it is the single column
a cache would need later, and computing it costs one pass over a string already in memory.

Encryption at rest is the cluster's, as for salon_events: Aurora storage is KMS-encrypted,
covering snapshots and backups.

Revision ID: 012
Revises: 011
Create Date: 2026-08-03
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "012"
down_revision = "011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "uploaded_data",
        sa.Column("file_id", sa.String(128), nullable=False),
        sa.Column("salon_id", UUID(as_uuid=True), nullable=False),
        # Not used today; the one column a future cache would look up.
        sa.Column("content_hash", sa.String(64), nullable=True),
        # A source is a URL or a file, never both; each is null for the other kind.
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("filename", sa.String(255), nullable=True),
        # Reported by whoever counted them. Never inferred from character counts.
        sa.Column("tokens", sa.Integer(), nullable=True),
        # Characters of extracted text — the unit the sources endpoint already reports.
        sa.Column("content_size", sa.BigInteger(), nullable=True),
        sa.Column("uploaded_by", sa.String(320), nullable=False),
        sa.Column(
            "uploaded_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("file_id"),
        sa.ForeignKeyConstraint(["salon_id"], ["sessions.id"], ondelete="CASCADE"),
    )
    # Listing what a salon was given is the query this table exists for, and the primary
    # key is a file id, which cannot serve it.
    op.create_index("ix_uploaded_data_salon_id", "uploaded_data", ["salon_id"])
    op.create_index("ix_uploaded_data_content_hash", "uploaded_data", ["content_hash"])


def downgrade() -> None:
    op.drop_index("ix_uploaded_data_content_hash", table_name="uploaded_data")
    op.drop_index("ix_uploaded_data_salon_id", table_name="uploaded_data")
    op.drop_table("uploaded_data")
