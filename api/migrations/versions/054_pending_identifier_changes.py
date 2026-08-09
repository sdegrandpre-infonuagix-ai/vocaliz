"""A change of identifier waiting for its one-time code.

Story 10.6 / FR64. An identifier is the key to somebody's balance, so changing one is changing
a lock while a person stands behind it. The **anchor** is what makes it safe: exactly one moves
at a time, and the other stays as the thing still tying the account to whoever held it
yesterday. Changing both at once is refused, and an account with a single identifier must add
its second before it can move the first.

A table rather than memory because the code travels by email or text and comes back minutes
later, from another request and possibly another process.

`anchor` and `replaces` are written when the change is planned, never resolved when it is
applied. Between the two the account may itself have moved — that is the whole point of this
feature — and a change resolving its own anchor at the end could find one it was never granted
against.

Spent rows are kept rather than deleted. `used_at` is the trace of when a key last moved, which
is the first thing anybody asks about an account that has changed hands.

Revision ID: 054
Revises: 053
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "054"
down_revision = "053"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pending_identifier_changes",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("new_identifier", sa.String(320), nullable=False),
        sa.Column("anchor", sa.String(320), nullable=False),
        sa.Column("replaces", sa.String(320), nullable=False),
        sa.Column("code", sa.String(10), nullable=False),
        sa.Column(
            "requested_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("pending_identifier_changes")
