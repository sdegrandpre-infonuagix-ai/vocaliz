"""The interpreter's voice, chosen by the host instead of fixed for every Salon.

Every Salon has run on the same xAI voice ("ara") regardless of tier or taste — Mode C was
supposed to read as "the most attentive interpreter" and had nothing that actually set it
apart from Base. A combo box is a smaller, more honest fix than guessing which voice counts
as premium: let the host pick, and default to the one everybody already has.

Null means "ara", the same way `host_tier` null means Base — not stored as the literal
string, so a Salon that never touched this setting stays visibly distinct from one that
chose "ara" on purpose.

Revision ID: 061
Revises: 060
"""
import sqlalchemy as sa
from alembic import op

revision = "061"
down_revision = "060"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("salons", sa.Column("agent_voice", sa.String(length=20), nullable=True))


def downgrade() -> None:
    op.drop_column("salons", "agent_voice")
