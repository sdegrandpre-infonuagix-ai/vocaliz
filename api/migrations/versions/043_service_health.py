"""Remember whether xAI is answering, so an alert can fire once instead of every minute.

The probe runs every minute. Emailing on every failure would send more than a thousand messages
during one bad night, and an inbox with a thousand identical alerts is an inbox where the next
real one is missed. The administrator needs to know that something changed — it broke, or it
came back — and a transition cannot be detected without remembering the previous state.

Revision ID: 043
Revises: 042
"""
import sqlalchemy as sa
from alembic import op

revision = "043"
down_revision = "042"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "service_health",
        sa.Column("service", sa.String(40), primary_key=True),
        sa.Column("healthy", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "changed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("detail", sa.Text(), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_table("service_health")
