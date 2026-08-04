"""An anonymous invitation has no contact, and the constraint has to say so.

ck_invitations_contact required an address or a number on every invitation. That was exactly
right while every invitation was addressed to somebody: a row with neither was a host who had
typed nothing, and refusing it in the database meant no code path could produce one by
accident.

Anonymous links are the case that was not foreseen. They carry no address on purpose, so the
old rule rejected them outright — a 500 at the moment the host clicked the button.

The replacement is narrower rather than weaker, and that is the point. Before, one rule applied
to every row; now each kind states what it must look like:

  anonymous_link  BOTH must be empty. An anonymous invitation cannot quietly carry an address,
                  which would make it addressed while claiming not to be.
  anything else   at least one must be present, exactly as before.

Dropping the constraint instead would have been the smaller diff and the worse schema: it would
have allowed an addressed invitation with nothing to address it to, which is the bug the
original author was preventing.

Also declared on the model in this change. It had lived only here, so the test database — built
from the models — never had it, and a violation could only ever be discovered in production.
That is how this one was found.

Revision ID: 031
Revises: 030
Create Date: 2026-08-04
"""
from alembic import op

revision = "031"
down_revision = "030"
branch_labels = None
depends_on = None

_OLD = "guest_email <> '' OR guest_phone <> ''"
_NEW = (
    "(invitation_type = 'anonymous_link' AND guest_email = '' AND guest_phone = '')"
    " OR (invitation_type <> 'anonymous_link' AND (guest_email <> '' OR guest_phone <> ''))"
)


def upgrade() -> None:
    op.drop_constraint("ck_invitations_contact", "invitations", type_="check")
    op.create_check_constraint("ck_invitations_contact", "invitations", _NEW)


def downgrade() -> None:
    # Any anonymous invitation would violate the old rule, so they go first. Deleting rather
    # than rewriting: there is no address to put back, and inventing one would turn a link
    # nobody was named on into an invitation that appears to have been sent to someone.
    op.execute("DELETE FROM invitations WHERE invitation_type = 'anonymous_link'")
    op.drop_constraint("ck_invitations_contact", "invitations", type_="check")
    op.create_check_constraint("ck_invitations_contact", "invitations", _OLD)
