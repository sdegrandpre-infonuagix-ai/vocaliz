"""What was said in a salon, and the same thing in another language.

The first tables in this schema to hold conversation. Until now the only text kept was
the source a host supplied; what participants said reached the agent and was discarded.
Keeping it is what makes a salon followable by someone who does not speak the language
being used — and it obliges us to tell participants, before they speak, that their words
are transcribed and stored.

Two tables rather than one: the spoken text is a record and must never be overwritten,
while a translation is derived and can be recomputed. Keying translations on
(utterance_id, language) also means every viewer watching in French shares the same rows,
so a language costs one call to the translator per turn no matter how many people read it.

Encryption at rest is the cluster's, as everywhere else. Nothing here is encrypted at the
column level, so SQL access reads the conversations in clear.

Revision ID: 015
Revises: 014
Create Date: 2026-08-03
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "015"
down_revision = "014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "utterances",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", UUID(as_uuid=True), nullable=False),
        # The LiveKit identity, the only handle available at the moment of speech.
        sa.Column("speaker_identity", sa.String(128), nullable=False),
        sa.Column("speaker_role", sa.String(5), nullable=False),
        # As spoken. Never overwritten by a translation.
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("language", sa.String(10), nullable=True),
        # Timestamps cannot order two turns transcribed in the same millisecond, and
        # captions arriving out of order read as a different conversation.
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column(
            "spoken_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.CheckConstraint(
            "speaker_role IN ('host', 'guest', 'agent')", name="ck_utterances_speaker_role"
        ),
    )
    op.create_index(
        "uq_utterances_session_sequence",
        "utterances",
        ["session_id", "sequence"],
        unique=True,
    )
    # The one query the client makes, every couple of seconds: this salon's turns, in
    # order, after the last one it saw.
    op.create_index("ix_utterances_session_spoken", "utterances", ["session_id", "spoken_at"])

    op.create_table(
        "utterance_translations",
        sa.Column("utterance_id", UUID(as_uuid=True), nullable=False),
        sa.Column("language", sa.String(10), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column(
            "translated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("utterance_id", "language"),
        sa.ForeignKeyConstraint(["utterance_id"], ["utterances.id"], ondelete="CASCADE"),
    )


def downgrade() -> None:
    op.drop_table("utterance_translations")
    op.drop_index("ix_utterances_session_spoken", table_name="utterances")
    op.drop_index("uq_utterances_session_sequence", table_name="utterances")
    op.drop_table("utterances")
