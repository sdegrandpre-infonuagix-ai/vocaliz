"""What other people in a Salon are told somebody is called.

A participant must enter a name when creating their account, and until this column there was
nowhere to put one. `username` is not it: that is the third way in of Story 10.7, a login
identifier alongside an email and a phone number, and reusing it would mean somebody's
credential being read out loud to strangers.

The absence was doing visible harm. A host's LiveKit token carried `display_name=user.email`,
so joining a conversation published your email address to everybody in it — a leak nobody
chose, in exchange for nothing, since an address is a poor thing to be called by anyway.
Guests were already better served: `guest_display_name(invitation.id)` gives them something
opaque rather than something personal.

**Nullable, and that is not a softening of the rule.** The rule governs a person creating an
account, which is enforced where that happens — `POST /auth/otp/request`, where signing up
and asking for a code are one act. A second path creates account rows without anybody
filling in a form: a guest arriving on an invitation is registered against the address the
host typed, and there is no moment in that flow at which they were asked anything. Making
the column NOT NULL would force a placeholder into it, and a placeholder is worse than an
absence — it looks like an answer. Null says plainly that this person has not been asked
yet, and the next real sign-up fills it in.

Sixty characters. Long enough for a name written the way its owner writes it, including the
ones that do not fit in thirty; short enough that nobody uses the field as a message board.

Revision ID: 058
Revises: 057
"""
import sqlalchemy as sa
from alembic import op

revision = "058"
down_revision = "057"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("display_name", sa.String(length=60), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "display_name")
