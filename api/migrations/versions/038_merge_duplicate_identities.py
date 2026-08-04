"""Fold a registered person's invitation-derived rows onto their account identity.

Two doors gave the same person two identities: their account UUID when they joined through the
app, and "guest-<invitation>" when they clicked an emailed link. Migration 037's predecessor
stopped that happening again; this repairs what was already written, so the participant report
shows one line per human instead of two.

Re-keyed rather than deleted, which is the important choice. Deleting the guest rows would keep
the report tidy at the cost of losing the fact that the person was in that salon at all — the
count would drop and nobody would know why. Moving the identity keeps every participation and
merely stops it being attributed to a stranger.

Where the two collide — the same person recorded as host *and* guest of one salon, under two
identities — the account row is kept and the invitation row is dropped. That is the instruction:
keep the host entry. Nothing is lost that the surviving row does not already say, since both
describe one person in one room.

Only invitations carrying a guest_user_id are touched. An invitation to somebody with no account,
anonymous or not, has no other identity to fold onto and is left exactly as it is.

Revision ID: 038
Revises: 037
Create Date: 2026-08-04
"""
from alembic import op

revision = "038"
down_revision = "037"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop the invitation-derived row wherever the account already has one for the same salon.
    # This runs first: re-keying it would violate the primary key, and the account row is the one
    # to keep.
    op.execute(
        """
        DELETE FROM salon_events AS dup
         USING invitations AS i, salon_events AS keep
         WHERE dup.participant_identity = 'guest-' || i.id::text
           AND i.guest_user_id IS NOT NULL
           AND keep.participant_identity = i.guest_user_id::text
           AND keep.salon_name = dup.salon_name
        """
    )

    # Everything else moves. The participation survives, attributed to the person rather than to
    # an invitation nobody will look up again.
    op.execute(
        """
        UPDATE salon_events AS se
           SET participant_identity = i.guest_user_id::text
          FROM invitations AS i
         WHERE se.participant_identity = 'guest-' || i.id::text
           AND i.guest_user_id IS NOT NULL
        """
    )


def downgrade() -> None:
    # Not reversible, and pretending otherwise would be worse than saying so. The mapping back
    # would need to know which invitation each folded row came from, and that is exactly the
    # information the fold discards — an account may hold several invitations to one salon.
    pass
