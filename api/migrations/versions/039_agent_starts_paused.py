"""A new salon starts with its agent paused, waiting to be given the floor.

The agent used to open the conversation on its own a fixed number of seconds after the first
invitation. That put the start of a salon on a timer nobody had asked for: a host still reading
the page was interrupted, and a host who wanted to begin at once had to wait out the count. The
countdown is gone and the decision is the host's — they press a button and the agent speaks.

Only the default changes. Sessions already running keep whatever value they hold, because their
agent is already in the room and already listening or already paused; rewriting that column
underneath them would contradict what their host is looking at.

Revision ID: 039
Revises: 038
"""
import sqlalchemy as sa
from alembic import op

revision = "039"
down_revision = "038"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # server_default rather than an UPDATE: it is the *next* session that must start paused.
    op.alter_column(
        "sessions",
        "agent_muted",
        existing_type=sa.Boolean(),
        existing_nullable=False,
        server_default=sa.text("true"),
    )


def downgrade() -> None:
    op.alter_column(
        "sessions",
        "agent_muted",
        existing_type=sa.Boolean(),
        existing_nullable=False,
        server_default=sa.text("false"),
    )
