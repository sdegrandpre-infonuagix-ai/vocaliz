"""Each invitation, its own room.

An accepted invitation used to join the host's room — the shared one, sized for everybody.
Under the per-pair topology a guest gets a room of their own, paired with their own agent, and
that room has to be created once and reused: a guest who reloads the join page, or whose first
attempt failed to reach a microphone, must come back to the room they already have rather than
be handed a second one nobody closes.

Nullable, and null until the guest's first successful `GET /guest-join/{token}` — an invitation
sent but never opened has no room to name.

Revision ID: 060
Revises: 059
"""
import sqlalchemy as sa
from alembic import op

revision = "060"
down_revision = "059"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "invitations", sa.Column("livekit_room_name", sa.String(length=100), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("invitations", "livekit_room_name")
