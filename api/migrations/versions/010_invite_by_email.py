"""Invite guests by email instead of SMS.

The join link is emailed via SES (FR2). guest_phone becomes optional — rows created
before this migration keep theirs, new invitations do not set it.

Side benefit: guest_email is a correlation key that always exists on a registered
account, which phone_number did not. link_prior_invitations can finally match reliably
(Story 3.5), which it could not do once sign-in moved to email.

Revision ID: 010
Revises: 009
Create Date: 2026-07-31
"""
from alembic import op
import sqlalchemy as sa

revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Nullable at first so the migration is safe on a populated table; the API only
    # creates invitations through the email path, which always sets it.
    op.add_column("invitations", sa.Column("guest_email", sa.String(320), nullable=True))
    op.create_index("ix_invitations_guest_email", "invitations", ["guest_email"])

    op.alter_column("invitations", "guest_phone", existing_type=sa.String(20), nullable=True)


def downgrade() -> None:
    # Invitations created after 010 have no phone number, so restoring NOT NULL would
    # fail; they must be backfilled or removed before downgrading.
    op.alter_column("invitations", "guest_phone", existing_type=sa.String(20), nullable=False)

    op.drop_index("ix_invitations_guest_email", table_name="invitations")
    op.drop_column("invitations", "guest_email")
