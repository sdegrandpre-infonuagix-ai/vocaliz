"""When a Salon is due to close, so guests can be given their fifteen seconds.

A balance running out ends a Salon, and FR55 says the guests are told fifteen seconds
before it does — enough to say goodbye, which is the whole reason for a notice rather than
a sudden disconnection.

That needs somewhere to live. The heartbeat is a request and a response; it cannot wait
fifteen seconds inside one. So exhaustion sets a moment in the future and says so, and the
next heartbeat — or the sweep, if the worker has gone — finalises once that moment has
passed. Holding it in memory would lose it the instant the process moved, and a Salon that
forgot it was closing would either close without warning or never close at all.

Null for every Salon that is not closing, which is nearly all of them. The column answers
"is this one on its way out, and since when?", and null is the honest answer for a
conversation in progress.

Revision ID: 057
Revises: 056
"""
import sqlalchemy as sa
from alembic import op

revision = "057"
down_revision = "056"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "salons",
        sa.Column("closing_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Whether the low-balance warning has already been given. Persisted for the same reason
    # as the moment above: the warning is once, not on every tick, and somebody asked twelve
    # times a minute stops hearing it. Held in memory it would repeat at every restart.
    op.add_column(
        "salons",
        sa.Column(
            "balance_alerted",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("salons", "balance_alerted")
    op.drop_column("salons", "closing_at")
