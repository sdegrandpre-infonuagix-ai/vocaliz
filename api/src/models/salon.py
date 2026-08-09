import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base


class Salon(Base):
    __tablename__ = "salons"

    # Declared here as well as in migration 053, because the test database is built from
    # these models: a constraint living only in a migration is one no test can see, and the
    # first thing to violate it does so in production. That has happened once already, to the
    # invitations table.
    __table_args__ = (
        CheckConstraint("participant_cap >= 2", name="ck_salons_participant_cap"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    host_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    livekit_room_name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    source_type: Mapped[str] = mapped_column(String(20), nullable=False)      # 'url' | 'document' | 'none'
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_content: Mapped[str | None] = mapped_column(Text, nullable=True)   # extracted plain text

    # What the agent is actually given. The full text above stays for search;
    # this is the brief that replaces the old 2 500-character truncation, and it is
    # written in the host's language whatever language the source is in. Null when
    # the summariser was unreachable — the agent then falls back to the truncation.
    source_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")

    # Whether the host has paused the voice agent. Paused means it stays in the room and keeps
    # everything it knows, but neither hears nor speaks — as opposed to removing it, which ends
    # the job and starts the next one with no memory of the conversation.
    #
    # Recorded because there is nothing else to ask. Presence is read from LiveKit, which knows
    # who is in a room; mute lives inside the running agent, so a host who reloads the page
    # would otherwise be shown a listening agent that is not listening.
    #
    # False on a brand-new salon: the agent joins listening and opens the conversation
    # itself.
    #
    # It defaulted to True for a few hours, so a host had to press activate before anything
    # happened. That was tried and reversed: a Salon that says nothing until a button is found
    # reads as broken, and the button was the first thing anybody had to learn. Pausing is
    # still there for a host who wants a private moment — it is a control, not a starting
    # gate.
    agent_muted: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    # The language the agent must speak, whatever it hears. "auto" — the default — means
    # follow each speaker, which is what every Salon did before this existed.
    #
    # Held on the salon rather than on the participant who chose it: a caller picks the
    # language of the conversation, not of their own line, and an agent answering one person
    # in Persian and another in Mandarin because they each set a preference would be two
    # conversations in one room.
    agent_language: Mapped[str] = mapped_column(
        String(10), nullable=False, default="auto", server_default=text("'auto'")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Story 8.3. The host's own tier, and nobody else's. A Salon does not have a mode —
    # each participant has one, and the host choosing Mode C imposes nothing on a guest who
    # chose Base. Null means the floor applies, which is what happens when nothing is picked.
    host_tier: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # Story 8.4. The host covering everybody. It belongs to the Salon because it is one
    # offer made once, but what it produces still lands per participant: each guest gets
    # their own row placing them at Mode B, never a mode stored on the Salon itself.
    host_pays_all: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false"), default=False
    )

    # Story 10.2. How many people this Salon was opened for, bounded at creation by the
    # deployment's `participant_ceiling`. Stored rather than read back from the settings,
    # because the two answer different questions: the ceiling is what is allowed *now*, and
    # this is what the host was promised *then*. A ceiling lowered mid-conversation must not
    # throw somebody out of a Salon they were already in.
    participant_cap: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("3"), default=3
    )

    host = relationship("User", foreign_keys=[host_user_id])
