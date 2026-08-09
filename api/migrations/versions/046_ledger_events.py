"""One append-only stream of financial and operational facts, with views folded out of it.

`billing_events` and `ad_broadcasts` already had the right instincts — append-only, prices
frozen at the moment of the fact, idempotent invoicing. What they were not is *one* stream.
Two logs of overlapping facts drift apart, and when they disagree nothing can say which is
right. This table is the single source of truth; the grant audit, the credit journals and the
metrics are all folds over it and are never written alongside it.

The tables it supersedes are left in place. Nothing in an append-only design justifies
deleting the records that were already written, and cutting their writers over is a change
with its own risk that belongs in its own migration.

Two things are deliberate in the schema:

- `subject_id` has **no foreign key**. The inherited `billing_events.host_user_id` cascaded
  on the user, so deleting an account destroyed the record of what had been charged to it —
  exactly backwards, since the person deleting an account is often the one with a reason to
  want the record gone. Retention here is independent of user accounts.
- The database refuses updates and deletes outright. The ORM refuses them too, but a
  guarantee that lives only in the application is one a psql prompt walks straight past.

Revision ID: 046
Revises: 045
"""
import sqlalchemy as sa
from alembic import op

revision = "046"
down_revision = "045"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ledger_events",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
        ),
        # When the fact happened, which is not always when the row was written: a refund
        # reconciled a day later belongs at the moment of the refund.
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
            index=True,
        ),
        sa.Column("type", sa.String(40), nullable=False, index=True),
        # No ForeignKey, on purpose. See the note above.
        sa.Column(
            "subject_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            nullable=False,
            index=True,
        ),
        sa.Column("subject_type", sa.String(20), nullable=False, server_default="user"),
        # Absent for a fact with no money attached — abandoning a Salon is operational, and
        # this stream records both kinds.
        sa.Column("amount_cents", sa.Integer(), nullable=True),
        sa.Column("currency", sa.String(10), nullable=False, server_default="usd"),
        # Which balance moved: gifted credit that expires, or paid credit that does not.
        # Recorded rather than derived, because which pool a debit came out of was a decision
        # made when it happened and re-deriving it later would be re-deciding the past.
        sa.Column("pool", sa.String(10), nullable=True),
        sa.Column("actor", sa.String(20), nullable=False, server_default="system"),
        sa.Column("actor_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
        # Set on a compensating event, pointing at what it corrects. Both facts survive.
        sa.Column("corrects_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("detail", sa.String(500), nullable=True),
    )

    # The guarantee, at the level that actually holds it. An application rule is one a psql
    # prompt walks straight past, and this stream is evidence.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION ledger_events_are_append_only()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION
                'ledger_events is append-only: record a compensating event with corrects_id '
                'instead of rewriting or removing one';
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER ledger_events_no_rewrite
        BEFORE UPDATE OR DELETE ON ledger_events
        FOR EACH ROW EXECUTE FUNCTION ledger_events_are_append_only();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS ledger_events_no_rewrite ON ledger_events")
    op.execute("DROP FUNCTION IF EXISTS ledger_events_are_append_only()")
    op.drop_table("ledger_events")
