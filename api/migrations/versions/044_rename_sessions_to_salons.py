"""Rename the session vocabulary to salon, everywhere the schema says it.

The product has only ever had one name for the thing a host opens — a Salon — while the
schema called it a session. The word was also taken: SQLAlchemy's unit of work is a
Session, and reading `session.session_id` in a file that also holds a database session
was a standing invitation to a mistake.

The rename became urgent rather than cosmetic when a Salon stopped being one room. It is
now a set of rooms, one per human-interpreter pair, and "session" suggested the
conversation and its room were the same object. They are not.

Renames only — no column is added, dropped, widened or re-typed, and no row is read or
written. Postgres carries the data, the foreign keys and the constraints across a rename
untouched; only the names move.

Indexes do not follow their table or column automatically, so each is renamed explicitly.
An index left behind would still work — it would just be the last place in production
still calling a Salon a session.

Every name is written out in full rather than looped over a list. These statements are
the only record of what the schema is called, and a reviewer — or the schema census in
tests/test_schema_visibility.py — must be able to read the names without executing the
file.

Revision ID: 044
Revises: 043
"""
from alembic import op

revision = "044"
down_revision = "043"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Tables first: the column renames below address salon_sources by its new name.
    op.rename_table("sessions", "salons")
    op.rename_table("session_sources", "salon_sources")

    # Every foreign key that pointed at sessions.id.
    op.alter_column("invitations", "session_id", new_column_name="salon_id")
    op.alter_column("salon_sources", "session_id", new_column_name="salon_id")
    op.alter_column("billing_events", "session_id", new_column_name="salon_id")
    op.alter_column("utterances", "session_id", new_column_name="salon_id")
    op.alter_column("shared_source_consents", "session_id", new_column_name="salon_id")
    op.alter_column("ad_broadcasts", "session_id", new_column_name="salon_id")

    op.execute("ALTER INDEX ix_sessions_host_user_id RENAME TO ix_salons_host_user_id")
    op.execute("ALTER INDEX ix_invitations_session_id RENAME TO ix_invitations_salon_id")
    op.execute("ALTER INDEX ix_session_sources_session_id RENAME TO ix_salon_sources_salon_id")
    op.execute("ALTER INDEX ix_billing_events_session_id RENAME TO ix_billing_events_salon_id")
    op.execute("ALTER INDEX ix_utterances_session_spoken RENAME TO ix_utterances_salon_spoken")
    # The one enforcing object among them: two turns of one Salon cannot share a position.
    op.execute("ALTER INDEX uq_utterances_session_sequence RENAME TO uq_utterances_salon_sequence")


def downgrade() -> None:
    op.execute("ALTER INDEX uq_utterances_salon_sequence RENAME TO uq_utterances_session_sequence")
    op.execute("ALTER INDEX ix_utterances_salon_spoken RENAME TO ix_utterances_session_spoken")
    op.execute("ALTER INDEX ix_billing_events_salon_id RENAME TO ix_billing_events_session_id")
    op.execute("ALTER INDEX ix_salon_sources_salon_id RENAME TO ix_session_sources_session_id")
    op.execute("ALTER INDEX ix_invitations_salon_id RENAME TO ix_invitations_session_id")
    op.execute("ALTER INDEX ix_salons_host_user_id RENAME TO ix_sessions_host_user_id")

    op.alter_column("ad_broadcasts", "salon_id", new_column_name="session_id")
    op.alter_column("shared_source_consents", "salon_id", new_column_name="session_id")
    op.alter_column("utterances", "salon_id", new_column_name="session_id")
    op.alter_column("billing_events", "salon_id", new_column_name="session_id")
    op.alter_column("salon_sources", "salon_id", new_column_name="session_id")
    op.alter_column("invitations", "salon_id", new_column_name="session_id")

    op.rename_table("salon_sources", "session_sources")
    op.rename_table("salons", "sessions")
