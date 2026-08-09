"""Which address or number belongs to which person (Story 10.1).

The signup identifier is the key to the ten-minute lifetime quota, and this is the table that
makes it one. Without it the quota is keyed to an account, and an account is something anybody
can make again — the allowance would reset for the price of a second signup.

One row per identifier, and the identifier is the primary key. That uniqueness is the whole
guarantee rather than a convenience: two rows for one address would be two quotas for one
person, found in whichever order a query happened to return them.

Not to be confused with `burned_identifiers`, which it resembles and does not duplicate. That
one records that the welcome credit has already been paid, has no foreign key, and outlives
the account on purpose. This one records who an identifier currently belongs to, and follows
the account it points at: an identifier whose person is gone belongs to nobody, and a signup
that reused it would be a new person with a fresh quota. Which is correct — what must not come
back is the *credit*, and that is the other table's job.
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.database import Base


class ParticipantIdentifier(Base):
    """One address or number, and the person it identifies."""

    __tablename__ = "participant_identifiers"

    # Normalised before it gets here: lowercased for an address, digits and a leading plus
    # for a number. Storing what somebody typed would make `Marie@Example.COM` a second key
    # to a second quota, which is the evasion this table exists to close.
    identifier: Mapped[str] = mapped_column(String(320), primary_key=True)

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
