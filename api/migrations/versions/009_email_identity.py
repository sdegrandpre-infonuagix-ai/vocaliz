"""Move account identity from phone number to email.

Sign-in is an email OTP (FR18). phone_number becomes optional: it is no longer the
account identifier, but it stays as the only key correlating an anonymous guest's SMS
invitation with the account they later register (link_prior_invitations).

Revision ID: 009
Revises: 008
Create Date: 2026-07-31
"""
from alembic import op
import sqlalchemy as sa

revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Added nullable so the migration is safe on a populated table; the API only ever
    # creates users through the email OTP flow, which always sets it.
    op.add_column("users", sa.Column("email", sa.String(320), nullable=True))
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.alter_column("users", "phone_number", existing_type=sa.String(20), nullable=True)


def downgrade() -> None:
    # Rows created after 009 may have no phone number, so restoring NOT NULL would
    # fail; they must be backfilled or removed before downgrading.
    op.alter_column("users", "phone_number", existing_type=sa.String(20), nullable=False)

    op.drop_index("ix_users_email", table_name="users")
    op.drop_column("users", "email")
