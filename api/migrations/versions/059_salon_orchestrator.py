"""Which orchestrator holds this Salon's text.

The third thing a Salon is made of, alongside its LiveKit room. The host creates the room and
the Salon in one breath; this records the instance that was handed the conversation, so
everything afterwards knows where to ask.

**Why it has to be written down rather than derived.** A Salon is stateful in a way a room is
not: the journal, every reader's position, who has been introduced to whom. One instance holds
that at a time, and any other instance answering for the same Salon would serve a second,
emptier version of the same conversation. A load balancer distributing by round robin is
exactly what this column prevents — the agents of one Salon must all reach the same address,
and the address of a Salon is a fact about that Salon.

**Nullable, and expected to be null for a while.** No orchestrator is deployed yet: the ECS
service exists on paper and nothing drives it. A Salon created today has no orchestrator and
says so, which is honest — the alternative is a default address that resolves to nothing and
fails on the first agent request instead of at the moment the choice was not made.

Null is also what a Salon reverts to when its instance is drained and nothing takes it over.
The journal survives that (NFR8); the affinity does not, and that asymmetry is the whole
reason affinity is a preference rather than a condition of survival.

Revision ID: 059
Revises: 058
"""
import sqlalchemy as sa
from alembic import op

revision = "059"
down_revision = "058"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "salons", sa.Column("orchestrator_url", sa.String(length=255), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("salons", "orchestrator_url")
