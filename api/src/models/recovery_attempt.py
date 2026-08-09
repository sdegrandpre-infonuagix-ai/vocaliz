"""Every attempt to prove a card, successful or not (Story 10.7 / FR65).

A recovery path is also an attack path, so the attempts are counted *and* written down.
Counting alone would stop somebody probing an account and leave no trace that they had.

Successes are recorded beside failures. A recovery that worked is the more interesting of the
two rows when an account is later disputed.

No foreign key to a user, for the same reason `burned_identifiers` has none: this is evidence
about attempts on an account, and it has to survive that account being deleted — which is
itself one of the things somebody might do after taking one over.
"""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.database import Base


class RecoveryAttempt(Base):
    """One try at proving the card behind an account."""

    __tablename__ = "recovery_attempts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # Deliberately not a foreign key. See the module note.
    subject_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    succeeded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    attempted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
