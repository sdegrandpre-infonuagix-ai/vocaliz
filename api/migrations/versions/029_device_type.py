"""What kind of device each participation came from, as a category rather than a fingerprint.

Only the classification is stored — "iphone", "android-tablet", "windows" — never the
User-Agent header it was derived from. That header carries browser build, engine version and
often the exact device model, which together identify a person across sessions better than
anything else in this schema. The same reasoning as the position column: a neighbourhood-scale
Plus Code rather than coordinates, because the imprecision is part of the value.

On the participation and not on the user, deliberately. The same person joins from a laptop at
work and a phone on the train; an account-level column would keep whichever came last and
present it as a fact about them.

Empty for everything recorded before this migration, and empty for a participant who joined by
telephone — who has no device in this sense at all. Not NULL: the sibling columns use the empty
string for absent, and one column behaving differently in every query is a worse cost than the
ambiguity it would resolve.

Revision ID: 029
Revises: 028
Create Date: 2026-08-03
"""
from alembic import op
import sqlalchemy as sa

revision = "029"
down_revision = "028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "salon_events",
        sa.Column("device_type", sa.String(20), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_column("salon_events", "device_type")
