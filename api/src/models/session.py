import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base


class SessionModel(Base):
    __tablename__ = "sessions"

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
    # True on a brand-new session: the agent joins paused and stays silent until the host
    # activates it. A salon that opened by itself started talking before its host was ready
    # to be talked to, and a countdown only moved the problem to a fixed number of seconds
    # later. Activation is now the host's, so the conversation begins when they decide.
    agent_muted: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    host = relationship("User", foreign_keys=[host_user_id])
