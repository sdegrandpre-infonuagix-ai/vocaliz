"""A third way into an account, and a way to get money back without one.

Story 10.7 / FR65. Every route so far runs through an identifier — a code to an address, a code
to a number. That works until somebody loses both, and then the account, the paid balance and
the gifted credit are gone with no way left to prove they were ever theirs.

`username` and `password_hash` are nullable because everybody who signed up before this story
has neither, and because this is a **third** route rather than a replacement: both identifier
routes stay open, since the failure it covers is precisely that they stopped working.

The hash is a salted scrypt value carrying its own salt and cost factors, so the salt is never
a second column somebody migrates without, and the parameters can be raised for new passwords
without invalidating old ones. 255 characters leaves room for both.

`recovery_attempts` has **no foreign key**, like `burned_identifiers`: it is evidence about
attempts on an account and must survive that account being deleted — which is itself one of the
things somebody might do after taking one over.

Revision ID: 055
Revises: 054
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "055"
down_revision = "054"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("username", sa.String(32), nullable=True))
        batch.add_column(sa.Column("password_hash", sa.String(255), nullable=True))
        batch.create_unique_constraint("uq_users_username", ["username"])
    op.create_index("ix_users_username", "users", ["username"])

    op.create_table(
        "recovery_attempts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("subject_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("succeeded", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "attempted_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("recovery_attempts")
    op.drop_index("ix_users_username", table_name="users")
    with op.batch_alter_table("users") as batch:
        batch.drop_constraint("uq_users_username", type_="unique")
        batch.drop_column("password_hash")
        batch.drop_column("username")
