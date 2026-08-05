"""The language a Salon's agent must speak, whatever it hears.

Until now the agent followed each speaker, which is right for a discussion between people who
came together on purpose and wrong for a caller reaching a front desk: the desk answers in the
language of the house, or in the one the caller picked before ringing.

"auto" is the default and means the old behaviour, so every Salon already running keeps it.

Ten characters, because the tags are BCP-47 with regional variants — "pt-BR", "ar-AE" — and
truncating them at the hyphen is exactly the mistake that would collapse three Arabics into
one and pick a voice from the wrong side of a continent.

Revision ID: 041
Revises: 040
"""
import sqlalchemy as sa
from alembic import op

revision = "041"
down_revision = "040"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "sessions",
        sa.Column(
            "agent_language",
            sa.String(10),
            nullable=False,
            server_default=sa.text("'auto'"),
        ),
    )


def downgrade() -> None:
    op.drop_column("sessions", "agent_language")
