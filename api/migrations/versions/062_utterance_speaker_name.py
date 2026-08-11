"""The display label a turn was actually captioned under, kept beside it.

Every turn used to be labelled at read time — `display_label`, computed fresh from the
identity and role alone. That is a guess good enough for a guest with no chosen name, but a
turn spoken on somebody's behalf (a typed message shared to the whole Salon) has no identity
of its own to guess from at all, and a human who did give a name deserves to be shown it
consistently, not recomputed into an anonymised label the moment they leave the room and a
late joiner asks for the transcript.

Null means exactly what it always has: nobody supplied one, and `display_label` falls back
to its own guess — no different from every row already in this table.

Revision ID: 062
Revises: 061
"""
import sqlalchemy as sa
from alembic import op

revision = "062"
down_revision = "061"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("utterances", sa.Column("speaker_name", sa.String(length=60), nullable=True))


def downgrade() -> None:
    op.drop_column("utterances", "speaker_name")
