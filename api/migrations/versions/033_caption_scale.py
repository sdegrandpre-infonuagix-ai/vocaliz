"""How large this person reads their captions, remembered on their account.

Somebody reading the conversation rather than hearing it spends the whole salon in that panel,
and the default size is a guess about eyesight. The two language choices already follow the
person from device to device; this is the third thing they set once and should not have to set
again.

Stored as a whole percentage — 85, 100, 120 — rather than a multiplier. A float would be
compared for equality against a fixed list of steps by the client, and 1.2 read back from a
database is not reliably the 1.2 in that list. An integer is exact, and reads as what it is.

Nullable, not defaulted. NULL means never chosen, which lets the client keep whatever the
device already had rather than jumping to a size nobody asked for on first sign-in.

Revision ID: 033
Revises: 032
Create Date: 2026-08-04
"""
from alembic import op
import sqlalchemy as sa

revision = "033"
down_revision = "032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("caption_scale", sa.Integer(), nullable=True))
    # A percentage, so anything outside a sane reading range is a bug rather than a preference.
    # The client offers 85 to 175; the bounds are wider so the steps can be retuned without a
    # migration, and narrow enough that a stray value cannot make the panel unreadable.
    op.create_check_constraint(
        "ck_users_caption_scale",
        "users",
        "caption_scale IS NULL OR (caption_scale BETWEEN 50 AND 300)",
    )


def downgrade() -> None:
    op.drop_constraint("ck_users_caption_scale", "users", type_="check")
    op.drop_column("users", "caption_scale")
