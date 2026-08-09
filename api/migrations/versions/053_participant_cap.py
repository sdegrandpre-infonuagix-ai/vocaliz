"""How many people a Salon was opened for.

Story 10.2, replacing FR2. The number moves out of `LIVEKIT_ROOM_MAX_PARTICIPANTS` and into
the persisted settings of Story 7.1, where it can be raised for one customer on a Tuesday: a
knob behind a deployment is one that in practice never gets turned. The API reads
`participant_ceiling` out of the same `salon_settings` table the orchestrator writes, so there
is one number and not two copies to disagree.

The column here is a different question from the ceiling, which is why it is stored rather than
looked up. The ceiling is what is allowed *now*; this is what the host was promised *then*. A
ceiling lowered mid-conversation must not throw somebody out of a Salon they are already in.

Three as the server default, matching the documented starting value. Existing Salons were
created under exactly that limit, so backfilling them with it records what was true rather than
guessing.

Revision ID: 053
Revises: 052
"""
import sqlalchemy as sa
from alembic import op

revision = "053"
down_revision = "052"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "salons",
        sa.Column(
            "participant_cap",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("3"),
        ),
    )
    # A Salon for one participant is somebody talking to a translation of themselves.
    op.create_check_constraint(
        "ck_salons_participant_cap", "salons", "participant_cap >= 2"
    )


def downgrade() -> None:
    op.drop_constraint("ck_salons_participant_cap", "salons", type_="check")
    op.drop_column("salons", "participant_cap")
