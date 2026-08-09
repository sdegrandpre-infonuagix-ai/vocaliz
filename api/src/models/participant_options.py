"""What one participant chose, in one Salon (FR35).

Keyed on (salon, person) rather than on the person: somebody may want Mode C for a client
call and Base for a chat with a friend, and options that followed a person around would make
the second choice overwrite the first.

There is deliberately no equivalent on `salons`. A Salon does not have a mode — the people in
it do — and a column here is what keeps that true in the schema rather than only in prose.
"""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.database import Base


class ParticipantOptions(Base):
    """One person's own choices for one Salon."""

    __tablename__ = "salon_participant_options"

    salon_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("salons.id", ondelete="CASCADE"), primary_key=True
    )
    # Not a foreign key on purpose is *not* the rule here: these are live preferences rather
    # than evidence, and they are meaningless once the account is gone. Contrast the ledger,
    # where the whole point is that the record outlives the account.
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    tier: Mapped[str] = mapped_column(String(20), nullable=False)
    video: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # What they asked to top up by, if anything. Their own amount, not the host's.
    top_up_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    chosen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
