"""A new Salon starts with its agent listening again.

Migration 039 made it start paused, so the host decided when the conversation began. That was
tried for an afternoon and reversed: a Salon that says nothing until somebody finds a button
reads as broken, and finding the button was the first thing every new host had to do.

Pausing survives as a control — a host who wants a private moment still has it. What it stops
being is a starting gate.

Only the default changes. Sessions already running keep whatever value they hold, because
their agent is already in the room and already listening or already paused; rewriting the
column underneath them would contradict what their host is looking at.

Revision ID: 042
Revises: 041
"""
import sqlalchemy as sa
from alembic import op

revision = "042"
down_revision = "041"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "sessions",
        "agent_muted",
        existing_type=sa.Boolean(),
        existing_nullable=False,
        server_default=sa.text("false"),
    )


def downgrade() -> None:
    op.alter_column(
        "sessions",
        "agent_muted",
        existing_type=sa.Boolean(),
        existing_nullable=False,
        server_default=sa.text("true"),
    )
