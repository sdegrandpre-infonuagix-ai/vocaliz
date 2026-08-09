"""The host's own tier choice, which is the host's alone.

A Salon does not have a mode. Each participant has one, and the host picking Mode C imposes
nothing on a guest who picked Base — that independence is the point of the whole epic, and a
column on `salons` called something like `mode` would have quietly asserted the opposite.
Hence the name: it is the *host's* tier, sitting beside the host's own row.

Null means the floor applies, which is what happens when nothing is chosen. A default of
'Base' would have been indistinguishable from somebody actively choosing Base, and those are
different facts.

Revision ID: 048
Revises: 047
"""
import sqlalchemy as sa
from alembic import op

revision = "048"
down_revision = "047"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("salons", sa.Column("host_tier", sa.String(20), nullable=True))


def downgrade() -> None:
    op.drop_column("salons", "host_tier")
