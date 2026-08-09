"""Whether somebody's whereabouts may be used to choose their advertising.

Nullable on purpose, and that is the whole design of the column. Three states, not two:
`NULL` means nobody has asked yet, which is neither a yes nor a no. Reading that silence
either way puts words in somebody's mouth — one way by targeting them, the other by recording
a refusal they never gave. A `NOT NULL DEFAULT false` would have quietly chosen the second.

The storage of the location itself was already careful and is untouched: `salon_events`
holds a six-digit Open Location Code cell of about five and a half kilometres, encoded at
ingestion, with no IP fallback. This adds the question, not the data.

Revision ID: 050
Revises: 049
"""
import sqlalchemy as sa
from alembic import op

revision = "050"
down_revision = "049"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("location_consent", sa.Boolean(), nullable=True))
    op.add_column(
        "users",
        sa.Column("location_consent_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "location_consent_at")
    op.drop_column("users", "location_consent")
