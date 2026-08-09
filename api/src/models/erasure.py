"""Proof that an erasure was asked for and carried out (Story 10.8 / FR66).

The record of a *request being honoured*, deliberately not a list of who asked. A log naming
everybody who exercised the right would be a new personal record created by honouring the old
one — so the subject appears only as the same one-way pseudonym left behind in the journals.

`due_by` is written when the request is accepted rather than checked afterwards: a bounded
delay that lives only in a policy document is a delay nobody can show was met.
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.database import Base


class Erasure(Base):
    """One erasure: when it was asked for, when it was due, when it was done, and over what."""

    __tablename__ = "erasures"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # The pseudonym, never the account id. See the module note.
    subject_pseudonym: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    due_by: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Which tables were touched and how, in words. What was erased matters as much as that
    # something was, and a boolean would not survive the first question about it.
    scope: Mapped[str] = mapped_column(Text, nullable=False, default="")
