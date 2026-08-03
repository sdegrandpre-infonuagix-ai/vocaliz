"""A six-digit code so a guest can join by telephone.

A phone call carries no URL, so the one-time join link is useless to someone dialling in.
The code is what replaces it: LiveKit answers, collects the digits on the keypad, and
places the caller in the room whose dispatch rule carries that code.

PER INVITATION, NOT PER SALON. A code shared by a whole salon would leave the caller
anonymous — no address, and no number either when the caller id is withheld. salon_events
requires one or the other, so the participation could not even be recorded. A code tied to
an invitation identifies the guest through the address and number the host already typed,
without the caller having to say anything.

RANDOM, FROM secrets. Six digits from the ordinary random module are predictable from a
handful of observed codes; these have to be unguessable by anyone who has seen others.

The unique index is partial, over pending invitations only. A global one would reserve
every code ever issued forever and exhaust a million-value space; restricted to pending
rows, the space is bounded by how many invitations are open at once.

Revision ID: 022
Revises: 021
Create Date: 2026-08-03
"""
from alembic import op
import sqlalchemy as sa

revision = "022"
down_revision = "021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Nullable: invitations created before this have none, and one is only minted when a
    # guest could actually receive it.
    op.add_column("invitations", sa.Column("phone_pin", sa.String(6), nullable=True))

    # Two open invitations must never share a code — the caller would reach whichever room
    # the dispatcher happened to match. Partial, so a code is released for reuse once the
    # invitation is accepted or expired rather than being reserved for all time.
    op.create_index(
        "uq_invitations_phone_pin_pending",
        "invitations",
        ["phone_pin"],
        unique=True,
        postgresql_where=sa.text("status = 'pending' AND phone_pin IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_invitations_phone_pin_pending", table_name="invitations")
    op.drop_column("invitations", "phone_pin")
