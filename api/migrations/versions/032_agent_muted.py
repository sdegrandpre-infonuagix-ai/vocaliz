"""Whether the host has paused the voice agent in this salon.

The host now has two ways to get the agent out of a conversation, and they are different
things. Pausing stops it hearing and speaking while it stays in the room, so it keeps
everything it knows; removing it ends the job, and the next one starts with no memory of what
was said. Both are useful, for different reasons, and the interface offers both.

Only the pause needs recording. Presence is read from LiveKit, which is the authority on who is
in a room — a column tracking that would describe what we last asked for rather than what is
true, and the agent can leave for reasons nothing here initiated. Mute has no such authority to
consult: it lives inside the running agent, and a host who reloads the page would otherwise be
shown a listening agent that is not listening.

Defaults to false. Every salon so far had an agent that listened, and that is what these rows
mean.

Revision ID: 032
Revises: 031
Create Date: 2026-08-04
"""
from alembic import op
import sqlalchemy as sa

revision = "032"
down_revision = "031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "sessions",
        sa.Column("agent_muted", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("sessions", "agent_muted")
