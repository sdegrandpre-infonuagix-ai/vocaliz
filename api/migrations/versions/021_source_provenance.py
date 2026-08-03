"""Where a source came from: its publication date, author and publisher.

Read from the metadata publishers already emit for social previews — article:published_time,
og:site_name, author — which is far more reliable than inferring any of it from the prose.
All three are optional and absent is ordinary: a personal blog names no publisher, plenty
of pages carry no date, and an uploaded file carries none of it.

article_date is a timestamp, not the string the page wrote. Ordering is the only reason the
field exists — "the latest news on X" is a question about time — and a date nothing can
sort is not a date. Unparseable values are therefore stored as NULL rather than kept as
strings to hope about later.

It also replaces the recency signal used for ranking the shared corpus. Ordering by when a
host happened to paste something is a proxy that fails in exactly the case that matters: an
old article shared today.

Revision ID: 021
Revises: 020
Create Date: 2026-08-03
"""
from alembic import op
import sqlalchemy as sa

revision = "021"
down_revision = "020"
branch_labels = None
depends_on = None

TABLES = ("uploaded_data", "shared_sources")


def upgrade() -> None:
    for table in TABLES:
        op.add_column(
            table, sa.Column("article_date", sa.DateTime(timezone=True), nullable=True)
        )
        op.add_column(
            table, sa.Column("author", sa.String(200), nullable=False, server_default="")
        )
        op.add_column(
            table, sa.Column("publisher", sa.String(200), nullable=False, server_default="")
        )

    # Ranking the corpus reads this before anything else, and NULLs are the common case —
    # a partial index keeps it to the rows that actually carry a date.
    op.create_index(
        "ix_shared_sources_article_date",
        "shared_sources",
        ["article_date"],
        postgresql_where=sa.text("article_date IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_shared_sources_article_date", table_name="shared_sources")
    for table in TABLES:
        op.drop_column(table, "publisher")
        op.drop_column(table, "author")
        op.drop_column(table, "article_date")
