"""Proof that an erasure was asked for and carried out.

Story 10.8 / FR66. The record of a *request being honoured*, deliberately not a list of who
asked: a log naming everybody who exercised the right would be a new personal record created by
honouring the old one. The subject appears only as the one-way pseudonym also left behind in
the journals.

`due_by` is written when the request is accepted rather than checked afterwards — a bounded
delay that lives only in a policy document is one nobody can show was met. `scope` is words
rather than a boolean, because what was erased matters as much as that something was.

Revision ID: 056
Revises: 055
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "056"
down_revision = "055"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "erasures",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("subject_pseudonym", sa.String(64), nullable=False, index=True),
        sa.Column(
            "requested_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("due_by", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scope", sa.Text(), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_table("erasures")
