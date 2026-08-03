"""The consented corpus: public web pages a host chose to make searchable by everyone.

Two properties make this safe, and both are structural rather than enforced by care.

ONLY WHAT WAS CONSENTED TO EXISTS HERE. Sources live in two places — the first on the
sessions row, later ones in session_sources — so a cross-platform search over those would
have to query both and never once forget the filter. One missing WHERE would expose every
private document. Here, not sharing is a row that does not exist; withdrawing is a delete.

ONLY URLS CAN BE HERE. There is no filename column and no source type, so an uploaded
document cannot be published even by a mistake in the calling code. A URL points at
something already public — indexing its summary tells nobody anything they could not read
by following the link. A file is the opposite, and no checkbox is worth getting that wrong.

CONSENT IS SEPARATE FROM THE PAGE. Two hosts may publish the same article; the first
withdrawing must not remove material the second still stands behind. Sharing prevails: the
page remains while any consent remains, and goes with the last one.

Revision ID: 020
Revises: 019
Create Date: 2026-08-03
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "020"
down_revision = "019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "shared_sources",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        # The only kind of source that can be here. Its presence is what makes publishing
        # an uploaded file impossible rather than merely forbidden.
        sa.Column("url", sa.Text(), nullable=False),
        # What another agent reads aloud — a result has to be speakable in a sentence or two.
        sa.Column("summary", sa.Text(), nullable=False, server_default=""),
        # The extracted text, kept rather than re-fetched: the page may have changed or
        # gone, and an answer drawn from what the salon actually read is the honest one.
        sa.Column("content", sa.Text(), nullable=False, server_default=""),
        # Lowercased topic terms, extracted once. This is what a spoken question matches.
        sa.Column("keywords", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        # The page's real identity — two URLs can serve the same article.
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column(
            "first_shared_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        # Ranking uses this one: a page published again today is topical again today.
        sa.Column(
            "last_shared_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("content_hash", name="uq_shared_sources_content_hash"),
        sa.CheckConstraint("trim(url) <> ''", name="ck_shared_sources_url"),
        sa.CheckConstraint("trim(content_hash) <> ''", name="ck_shared_sources_hash"),
        sa.CheckConstraint(
            "trim(summary) <> '' OR trim(content) <> ''",
            name="ck_shared_sources_has_something",
        ),
    )
    # Most recent first is the default ordering of every search here.
    op.create_index("ix_shared_sources_last_shared_at", "shared_sources", ["last_shared_at"])
    # GIN, because the question asked of keywords is containment, which a B-tree on a JSONB
    # value cannot answer.
    op.create_index(
        "ix_shared_sources_keywords", "shared_sources", ["keywords"], postgresql_using="gin"
    )

    op.create_table(
        "shared_source_consents",
        sa.Column("source_id", UUID(as_uuid=True), nullable=False),
        # An email, shown to nobody. It lets a host review and withdraw their own
        # publications, and lets a complaint be traced to whoever published the material.
        sa.Column("shared_by", sa.String(320), nullable=False),
        sa.Column("session_id", UUID(as_uuid=True), nullable=False),
        sa.Column(
            "shared_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("source_id", "shared_by"),
        sa.ForeignKeyConstraint(["source_id"], ["shared_sources.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
    )
    # Listing what one host has published, which is the screen that makes the checkbox
    # meaningful. The primary key leads with source_id and cannot serve it.
    op.create_index(
        "ix_shared_source_consents_shared_by", "shared_source_consents", ["shared_by"]
    )


def downgrade() -> None:
    op.drop_index("ix_shared_source_consents_shared_by", table_name="shared_source_consents")
    op.drop_table("shared_source_consents")
    op.drop_index("ix_shared_sources_keywords", table_name="shared_sources")
    op.drop_index("ix_shared_sources_last_shared_at", table_name="shared_sources")
    op.drop_table("shared_sources")
