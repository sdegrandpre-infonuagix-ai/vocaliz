"""Identifiers that have already been paid a welcome credit, and never will be again (FR67).

A gift given per *account* is a gift given as often as somebody cares to make accounts. What
is spent is therefore the identifier, not the account: every address and number handed over
at signup is checked here, and on a grant all of them are burned — including any that were
not used to sign in, since an unused identifier is exactly what somebody keeps in reserve for
the next attempt.

Two properties this table exists to hold, both of which have to survive a well-meaning
migration:

- **No foreign key to a user.** Deleting the account and signing up again is the obvious
  attempt, and a registry that forgot on deletion would protect against nothing.
- **No expiry column.** The credit lapses after 30 days; the fact that it was once given does
  not. Those are different clocks and only one of them runs.
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.database import Base


class BurnedIdentifier(Base):
    """One address or number that has had its one welcome credit."""

    __tablename__ = "burned_identifiers"

    # The identifier itself is the key: two people cannot burn the same address twice, and
    # the uniqueness is the guarantee rather than a convenience.
    identifier: Mapped[str] = mapped_column(String(320), primary_key=True)
    burned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # Who it was burned for, kept as a bare identifier for support to trace a dispute. Not a
    # foreign key: this row outlives that account on purpose.
    granted_to: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
