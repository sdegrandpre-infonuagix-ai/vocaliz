"""Record who took part in each salon.

One row per participation, keyed by (email, user_type, salon_name). Entry and exit
timestamps and the closing satisfaction answer live alongside, with the client address
and — when the browser grants it — the position.

Encryption at rest is the cluster's: Aurora storage is KMS-encrypted, so this table, its
snapshots and its backups are covered. No column-level encryption, which was a deliberate
trade: it would have required deterministic ciphertext on the key columns and left
equality as the only possible query.

Revision ID: 011
Revises: 010
Create Date: 2026-08-03
"""
from alembic import op
import sqlalchemy as sa

revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "salon_events",
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("user_type", sa.String(5), nullable=False),
        sa.Column("salon_name", sa.String(100), nullable=False),
        # Nullable: a proxy can hide the address, and losing the row over a missing
        # header would be worse than storing it without one.
        sa.Column("client_ip", sa.String(45), nullable=True),
        # BCP-47 code for the first language heard from this person in this salon — a
        # property of the participation, not of the person: the same user may hold one
        # conversation in French and the next in English. First rather than predominant,
        # because "first heard" is one event reported once, never revised.
        sa.Column("first_spoken_language", sa.String(10), nullable=True),
        # NULL whenever the participant declined the browser's location prompt — the
        # common case, and not an error.
        sa.Column("gps_latitude", sa.Numeric(8, 6), nullable=True),
        sa.Column("gps_longitude", sa.Numeric(9, 6), nullable=True),
        sa.Column(
            "entered_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("exited_at", sa.DateTime(timezone=True), nullable=True),
        # TRUE and FALSE are answers; NULL means the question was never asked or never
        # answered, which is not the same as a bad experience.
        sa.Column("enjoyed", sa.Boolean(), nullable=True),
        sa.PrimaryKeyConstraint("email", "user_type", "salon_name"),
        sa.CheckConstraint(
            "user_type IN ('host', 'guest')", name="ck_salon_events_user_type"
        ),
    )
    # Reading back a whole salon is the obvious query — who was there, when they came and
    # went — and the primary key cannot serve it, salon_name being its last column.
    op.create_index("ix_salon_events_salon_name", "salon_events", ["salon_name"])


def downgrade() -> None:
    op.drop_index("ix_salon_events_salon_name", table_name="salon_events")
    op.drop_table("salon_events")
