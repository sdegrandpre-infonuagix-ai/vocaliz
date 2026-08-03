"""The pool of six-digit codes guests dial to join a salon by telephone.

Two columns and no more. The table answers one question — is this code free? Which salon a
code reaches is not here: it is on the invitation the code was sent with, which is also
where the guest's address and number live. One lookup therefore yields both the room and who
is calling, and no second copy of the mapping exists to drift out of step.

A pool rather than a code minted per invitation. Minting means generating a value, querying
for a collision and retrying, with a race between the check and the insert. Claiming a row
is one atomic update, and the primary key settles any race for a fresh code.

Filled lazily. Pre-generating a million rows to hand out a handful would be storage spent on
nothing, so the table grows with use and is bounded by concurrent use rather than total use.

Revision ID: 023
Revises: 022
Create Date: 2026-08-03
"""
from alembic import op
import sqlalchemy as sa

revision = "023"
down_revision = "022"
branch_labels = None
depends_on = None

CODE_DIGITS = 6


def upgrade() -> None:
    op.create_table(
        "code_available",
        # The code is the key: what a caller types and what the dispatcher looks up.
        sa.Column("code", sa.String(CODE_DIGITS), nullable=False),
        # False from the moment the code is sent out until the guest leaves the salon.
        sa.Column("available", sa.Boolean(), nullable=False, server_default=sa.true()),
        # The only way to notice a code that leaked: a salon that never ended leaves its
        # codes reserved forever, and without a timestamp nothing can tell that from a code
        # in honest use.
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("code"),
        sa.CheckConstraint(f"length(code) = {CODE_DIGITS}", name="ck_code_available_length"),
        # A free code carries no claim time and a reserved one must. What stops the two
        # facts from contradicting each other.
        sa.CheckConstraint(
            "(available AND claimed_at IS NULL) OR (NOT available AND claimed_at IS NOT NULL)",
            name="ck_code_available_consistent",
        ),
    )
    # Claiming reads this on every invitation. Partial, because free codes are the only ones
    # ever selected and they become the minority once the platform is busy.
    op.create_index(
        "ix_code_available_free",
        "code_available",
        ["available"],
        postgresql_where=sa.text("available"),
    )


def downgrade() -> None:
    op.drop_index("ix_code_available_free", table_name="code_available")
    op.drop_table("code_available")
