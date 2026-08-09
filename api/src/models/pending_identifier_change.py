"""A change of identifier waiting for its one-time code (Story 10.6 / FR64).

Kept in a table rather than in memory because the code travels by email or text and comes back
minutes later, from a different request and possibly a different process.

The anchor is written down at the moment the change is planned, not read back when it is
applied. Between the two the account may have moved — the whole point of this story is that
identifiers change — and a change that resolved its own anchor at the end could find one that
was not the one it was granted against.
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.database import Base


class PendingIdentifierChange(Base):
    """One identifier on its way to replacing another, once somebody proves they hold it."""

    __tablename__ = "pending_identifier_changes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Normalised on the way in, exactly as a signup identifier is: an account holding a key
    # spelled differently from the registry is an account nothing can find.
    new_identifier: Mapped[str] = mapped_column(String(320), nullable=False)
    # The one staying put. What still ties this account to the person it belonged to.
    anchor: Mapped[str] = mapped_column(String(320), nullable=False)
    # What is being replaced, so applying the change knows which key to withdraw.
    replaces: Mapped[str] = mapped_column(String(320), nullable=False)

    code: Mapped[str] = mapped_column(String(10), nullable=False)
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # Set when the change actually took effect. A spent row is kept rather than deleted: it
    # is the trace of when somebody's key last moved, which is the first thing anybody asks
    # about an account that has changed hands.
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
