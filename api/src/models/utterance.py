"""What was said in a salon, and the same thing in another language.

This is the first place in the schema where conversations are kept. Until now the only
text retained was the source a host supplied; what participants actually said passed
through the agent and was discarded. That changed deliberately, to let someone follow a
conversation held in a language they do not speak — and it carries an obligation that
belongs next to the table rather than in a document nobody reads: the participants must
be told, before they speak, that their words are transcribed and stored.
"""
import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.database import Base


class Utterance(Base):
    """One turn of speech, as it was spoken.

    Finals only. The realtime model streams a transcript that is revised as it hears more
    — storing the interim versions would fill the table with half-sentences that were
    never true, and the client already sees those live.
    """

    __tablename__ = "utterances"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )

    # The LiveKit identity, which is the only handle available at the moment of speech:
    # `guest-{invitation_id}` for a guest, the user id for anyone else, and the literal
    # "agent" for the facilitator. Deliberately not an email — resolving one costs a
    # query per turn, and the client needs a display label, not an address.
    speaker_identity: Mapped[str] = mapped_column(String(128), nullable=False)
    speaker_role: Mapped[str] = mapped_column(String(5), nullable=False)

    # As transcribed, in the language it was spoken. Never overwritten by a translation:
    # every translation is a derived row, and this is the only record of what was said.
    text: Mapped[str] = mapped_column(Text, nullable=False)

    # BCP-47, reported per turn by the realtime model. Null when it did not say — the
    # translator detects the source itself, so a missing value costs nothing.
    language: Mapped[str | None] = mapped_column(String(10), nullable=True)

    # Monotonic within a session, assigned on insert. Timestamps alone cannot order two
    # turns transcribed in the same millisecond, and captions arriving out of order read
    # as a different conversation.
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)

    spoken_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "speaker_role IN ('host', 'guest', 'agent')", name="ck_utterances_speaker_role"
        ),
        # Two turns of one session cannot share a position in the order.
        Index("uq_utterances_session_sequence", "session_id", "sequence", unique=True),
    )


class UtteranceTranslation(Base):
    """One turn rendered into one language.

    Keyed on the pair, so asking twice for the same language costs one lookup rather than
    one call to the translator. Which matters more than it looks: every participant
    watching captions in French shares these rows, and a ten-minute salon is a few hundred
    turns.
    """

    __tablename__ = "utterance_translations"

    utterance_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("utterances.id", ondelete="CASCADE"),
        primary_key=True,
    )
    language: Mapped[str] = mapped_column(String(10), primary_key=True)

    text: Mapped[str] = mapped_column(Text, nullable=False)
    translated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
