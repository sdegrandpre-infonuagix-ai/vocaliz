"""The one append-only stream of financial and operational facts (NFR7).

`billing_events` and `ad_broadcasts` already had the right instincts — append-only, prices
frozen at the moment of the fact, idempotent invoicing. What they were not is *one* stream.
Two logs of overlapping facts drift apart, and when they disagree nothing in the system can
say which is right. Everything is written here once, and every journal, audit and metric is
folded back out of it.

Two properties are enforced rather than described.

**Nothing is ever modified or deleted.** A correction is a compensating event that points at
what it corrects, so both facts survive: what was recorded, and that it was wrong. A stream
that could be rewritten would say what somebody last decided rather than what happened, and
would be worth nothing as evidence.

**The subject is a bare identifier and not a foreign key.** The inherited `billing_events`
cascaded on the user, so deleting an account destroyed the record of what had been charged
to it — exactly backwards, since the person deleting an account is often the one with a
reason to want the record gone.
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, event, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.database import Base


class LedgerAppendOnly(RuntimeError):
    """Raised when something tries to change or remove an event that was already written."""


class LedgerEvent(Base):
    """One fact, written once."""

    __tablename__ = "ledger_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # When the fact happened, which is not always when the row was written — a refund
    # reconciled a day later belongs at the moment of the refund.
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    # Deliberately no ForeignKey. The stream outlives the account it is about, and a
    # migration that helpfully added one back would silently undo the retention guarantee —
    # which is why a test asserts the absence directly.
    subject_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    subject_type: Mapped[str] = mapped_column(String(20), nullable=False, default="user")
    # Absent for a fact with no money attached: abandoning a Salon is operational, and the
    # stream is the record of both kinds.
    amount_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="usd")
    # Which balance this moved: gifted credit that expires, or paid credit that does not.
    # Recorded rather than derived — which pool a debit came out of was a decision made when
    # it happened, and re-deriving it later would be re-deciding the past.
    pool: Mapped[str | None] = mapped_column(String(10), nullable=True)
    # "The system did it" and "a named person did it" are different facts, and the second is
    # the one an audit exists to answer.
    actor: Mapped[str] = mapped_column(String(20), nullable=False, default="system")
    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    # Set on a compensating event, pointing at what it corrects.
    corrects_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    detail: Mapped[str | None] = mapped_column(String(500), nullable=True)


@event.listens_for(LedgerEvent, "before_update", propagate=True)
def _refuse_update(_mapper, _connection, target: LedgerEvent) -> None:
    raise LedgerAppendOnly(
        f"ledger event {target.id} cannot be modified. Record a compensating event that "
        "points at it with corrects_id — a rewritten stream says what somebody last "
        "decided rather than what happened."
    )


@event.listens_for(LedgerEvent, "before_delete", propagate=True)
def _refuse_delete(_mapper, _connection, target: LedgerEvent) -> None:
    raise LedgerAppendOnly(
        f"ledger event {target.id} cannot be deleted. The stream is the evidence, and it "
        "outlives both the account it is about and anybody's wish to be rid of it."
    )
