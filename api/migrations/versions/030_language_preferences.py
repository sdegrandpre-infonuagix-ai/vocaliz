"""The two languages a person chose, remembered on their account.

Until now both lived in the browser's local storage, so a host who set the interface to Polish
on their laptop met English again on their phone, and a reader who picked Thai captions picked
them again every session. A choice is a property of the person, unlike the language they were
first heard speaking — that one belongs to the participation and already lives there.

Three language columns on the user now, and they answer different questions:

  detected_language   what the agent heard. A suggestion, written by the worker.
  interface_language  what they chose to read the application in.
  caption_language    what they chose to read other people's speech in.

Both new columns are nullable, and for caption_language that is load-bearing rather than
incidental: the empty string is a real choice there — "as spoken", translate nothing — so NULL
has to mean "never chose" and "" has to mean "chose not to translate". Collapsing them would
make it impossible to offer somebody a default without overriding a decision they made.

Revision ID: 030
Revises: 029
Create Date: 2026-08-03
"""
from alembic import op
import sqlalchemy as sa

revision = "030"
down_revision = "029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # No server default: absent must stay NULL, which is what distinguishes a person who never
    # chose from one who chose the empty option.
    op.add_column("users", sa.Column("interface_language", sa.String(10), nullable=True))
    op.add_column("users", sa.Column("caption_language", sa.String(10), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "caption_language")
    op.drop_column("users", "interface_language")
