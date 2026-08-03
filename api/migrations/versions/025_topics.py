"""keywords becomes topics on shared_sources.

One idea under two names. ads.topic already existed, and these two columns are meant to be
matched against each other: an ad about coffee should reach a page whose topics include
coffee. Reading that comparison required translating "keyword" into "topic" in one's head
every time, which is exactly the kind of friction that produces a query joining the wrong
pair.

Ten of them per page now, matching what the extractor asks for. Nothing here enforces the
count — a thin page yields fewer, and padding to reach ten would make it findable by
questions it cannot answer.

Revision ID: 025
Revises: 024
Create Date: 2026-08-03
"""
from alembic import op

revision = "025"
down_revision = "024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The GIN index follows the column automatically, but its name would keep saying
    # keywords — renamed too, so nothing in the schema still uses the old word.
    op.alter_column("shared_sources", "keywords", new_column_name="topics")
    op.execute("ALTER INDEX ix_shared_sources_keywords RENAME TO ix_shared_sources_topics")


def downgrade() -> None:
    op.execute("ALTER INDEX ix_shared_sources_topics RENAME TO ix_shared_sources_keywords")
    op.alter_column("shared_sources", "topics", new_column_name="keywords")
