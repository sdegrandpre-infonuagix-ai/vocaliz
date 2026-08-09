"""Each participant's own options, and the host's offer to pay for everybody.

Keyed on (salon, person) rather than on the person: somebody may want Mode C for a client
call and Base for a chat with a friend, and options that followed a person around would make
the second choice overwrite the first.

There is deliberately no mode column on `salons`. A Salon does not have a mode — the people
in it do — and putting one there would assert the opposite in the schema, which is where
people look when the prose and the code disagree. `host_pays_all` is on the Salon because it
is one offer made once; what it *produces* still lands per participant, as a row here.

Unlike `ledger_events` and `burned_identifiers`, these carry foreign keys with cascades on
purpose. Those two are evidence and outlive the account; these are live preferences and are
meaningless without it.

Revision ID: 049
Revises: 048
"""
import sqlalchemy as sa
from alembic import op

revision = "049"
down_revision = "048"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "salons",
        sa.Column(
            "host_pays_all", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
    )
    op.create_table(
        "salon_participant_options",
        sa.Column(
            "salon_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("salons.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "user_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("tier", sa.String(20), nullable=False),
        sa.Column(
            "video", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        # Their own top-up amount, not the host's.
        sa.Column("top_up_cents", sa.Integer(), nullable=True),
        sa.Column(
            "chosen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )


def downgrade() -> None:
    op.drop_table("salon_participant_options")
    op.drop_column("salons", "host_pays_all")
