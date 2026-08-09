"""Identifiers that have already had their one welcome credit, and never get another.

A gift given per *account* is a gift given as often as somebody cares to make accounts. What
is spent is the identifier: every address and number handed over at signup is checked here,
and on a grant all of them are burned — including any that were not used to authenticate,
since an unused identifier is exactly what somebody keeps in reserve for the next attempt.

Two absences in this schema are the whole point, and both have to survive a well-meaning
migration later:

- **No foreign key to `users`.** Deleting the account and signing up again is the obvious
  attempt, and a registry that forgot on deletion would protect against nothing at all.
- **No expiry column.** The credit lapses after 30 days; the fact that it was once given does
  not. Those are two different clocks and only one of them runs.

Revision ID: 047
Revises: 046
"""
import sqlalchemy as sa
from alembic import op

revision = "047"
down_revision = "046"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "burned_identifiers",
        # The identifier is the key: two people cannot burn the same address twice, and that
        # uniqueness is the guarantee rather than a convenience.
        sa.Column("identifier", sa.String(320), primary_key=True),
        sa.Column(
            "burned_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        # Kept so support can trace a dispute. Deliberately not a foreign key — this row
        # outlives that account, which is the entire reason the table exists.
        sa.Column("granted_to", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("burned_identifiers")
