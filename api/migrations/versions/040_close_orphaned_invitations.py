"""Close invitations left pending by a salon that is already over.

They are not merely untidy. A pending invitation holds its telephone code under a partial
unique index, and ending a session returned that code to the pool without closing the
invitation — so the pool offered a code a pending row still owned. The pool hands out its
oldest free code first, which turned one stale row into a permanent outage: every invitation
anybody created was given the same poisoned code and failed with a 500.

Two changes ship together. The lifecycle now closes these invitations before releasing their
codes, which stops new ones appearing; this repairs the rows already written, which is what
actually clears the outage.

Marked expired rather than deleted. The invitation is a record that a host asked somebody to
join, and that remains true whether or not they came — deleting it would quietly shorten the
history to make a constraint comfortable.

Codes are freed as a consequence, not as an act: once these rows stop being pending they no
longer hold anything, and the pool's own bookkeeping is left exactly as it is.

Revision ID: 040
Revises: 039
"""
from alembic import op

revision = "040"
down_revision = "039"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Scoped to invitations of an ended session. A pending invitation to a live salon is
    # somebody who has not arrived yet, and closing it would cancel a real invitation.
    op.execute(
        """
        UPDATE invitations
           SET status = 'expired'
         WHERE status = 'pending'
           AND session_id IN (SELECT id FROM sessions WHERE status <> 'active')
        """
    )


def downgrade() -> None:
    # Deliberately empty. Which expired invitations were expired by this migration and which
    # by the normal course of a salon ending is not recorded anywhere, so reopening them would
    # mean guessing — and guessing wrong puts the outage back.
    pass
