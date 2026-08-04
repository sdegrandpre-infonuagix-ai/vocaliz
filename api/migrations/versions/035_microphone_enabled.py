"""Whether this participant ever got their microphone working.

The question this answers came from the first real users. Five hosts created a salon, reached
the room — their device type is recorded, and that is only sent when LiveKit credentials are
handed out — and the agent never heard any of them. Two very different things look identical in
the data: somebody who arrived out of curiosity and said nothing, and somebody who tried to
speak and could not be heard.

On a phone browser the microphone needs an explicit gesture and then a permission grant, which
is why the page carries an "Enable microphone" button at all. So the second case is not
hypothetical, and the two need opposite responses.

Together with first_spoken_language this gives three distinguishable outcomes:

  microphone never enabled          they never tried
  enabled, no language heard        they tried and were not heard, or said nothing
  enabled and a language heard      it worked

Write-once and true-only: the interesting fact is whether it ever worked, not whether it was on
at the end. Somebody who mutes themselves before leaving has still been heard.

Revision ID: 035
Revises: 034
Create Date: 2026-08-04
"""
from alembic import op
import sqlalchemy as sa

revision = "035"
down_revision = "034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # False for everything recorded before this migration, which is honest: nothing was
    # measured then, and defaulting to true would invent working microphones.
    op.add_column(
        "salon_events",
        sa.Column(
            "microphone_enabled", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )


def downgrade() -> None:
    op.drop_column("salon_events", "microphone_enabled")
