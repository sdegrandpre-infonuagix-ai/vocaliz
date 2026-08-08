"""Key a participation to its Salon rather than to a room name.

`salon_events` identified a participation by `(participant_identity, salon_name)`, where
`salon_name` is the LiveKit room. That held while a Salon was one room. It stops holding
under the new topology: a Salon is now one room per human-interpreter pair, so three
participants of one conversation carry three different room names. Every count of
"distinct salons" would read three, and every lookup filtering on the host's room name
would find one participant out of three.

Adding `salon_id` rather than swapping the primary key, deliberately:

- Rows whose Salon was deleted before this migration have no id to point at. A primary
  key column cannot be NULL, so a swap would mean deleting those participations. They are
  the historical record of people who took part; losing them to a key change would be a
  poor trade for a constraint that gains nothing.
- `(participant_identity, salon_name)` remains unique and valid — one participant occupies
  one room. Replacing a live primary key buys no correctness here, and costs a rewrite of
  the table.

The uniqueness that actually matters under multi-rooms is expressed as a partial unique
index: one participant, one participation per Salon, whatever room they reconnect into.
Without it, a reconnection that lands in a fresh room would silently become a second
participation — the exact duplication the old key used to prevent.

ON DELETE CASCADE so orphans stop accumulating: from here on, a deleted Salon takes its
participations with it, which is also what deleting an account has to mean.

Revision ID: 045
Revises: 044
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "045"
down_revision = "044"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "salon_events",
        sa.Column("salon_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_salon_events_salon_id",
        "salon_events",
        "salons",
        ["salon_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # The room name was unique per Salon before this change, so it identifies exactly one.
    # Rows that match nothing keep a NULL id and stay: their Salon is already gone.
    op.execute(
        """
        UPDATE salon_events AS e
           SET salon_id = s.id
          FROM salons AS s
         WHERE s.livekit_room_name = e.salon_name
        """
    )

    op.create_index("ix_salon_events_salon_id", "salon_events", ["salon_id"])
    # Partial: orphaned participations share a NULL id and must not collide with each other.
    op.create_index(
        "uq_salon_events_participant_salon",
        "salon_events",
        ["participant_identity", "salon_id"],
        unique=True,
        postgresql_where=sa.text("salon_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_salon_events_participant_salon", table_name="salon_events")
    op.drop_index("ix_salon_events_salon_id", table_name="salon_events")
    op.drop_constraint("fk_salon_events_salon_id", "salon_events", type_="foreignkey")
    op.drop_column("salon_events", "salon_id")
