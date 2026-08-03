"""Every time an ad was actually spoken, and what it cost.

WHY THIS TABLE EXISTS. ads.number_of_broadcasts_left destroys information by consuming it.
A counter that only decrements cannot say how many broadcasts happened, when, or in which
salon — so nothing could invoice an advertiser, report to one, or diagnose an ad burning
through its allowance. Zero was also ambiguous: exhausted, or never purchased?

WHY THE PRICE IS ON THE ROW. Rates change. An invoice has to charge what was agreed when the
ad was spoken, not what the setting happens to say when the invoice is drawn. Reading the
rate at billing time would silently reprice history.

WHY DELETION IS BLOCKED. An ad that has been broadcast cannot be deleted: RESTRICT rather
than CASCADE. These rows are billing evidence, and a foreign key that quietly removed them
would make an advertiser's history depend on whether anyone had tidied up. The same reasoning
argues against the CASCADE from advertisers to ads, which is still there — noted at the foot
of this module.
"""
import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.database import Base


class AdBroadcast(Base):
    """One ad, spoken once, in one salon."""

    __tablename__ = "ad_broadcasts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # RESTRICT: an ad with broadcasts cannot be deleted. The alternative is losing the record
    # that it ran, which is the one thing an advertiser could dispute.
    ad_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ads.ad_id", ondelete="RESTRICT"), nullable=False
    )

    # Denormalised from the ad. Not for speed: this is who gets invoiced, and the invoicing
    # run groups by it. Immutable for a given ad, so there is nothing to keep in step.
    advertiser_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("advertisers.advertiser_id", ondelete="RESTRICT"),
        nullable=False,
    )

    # SET NULL rather than RESTRICT: a salon is ephemeral and may legitimately be removed,
    # and losing which room an ad played in must not block that. The name below survives it.
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="SET NULL"), nullable=True
    )
    # Kept as text so an invoice line can name the salon even after the session is gone.
    salon_name: Mapped[str] = mapped_column(String(100), nullable=False, default="")

    # The rate at the moment of broadcast, in cents. See the module note.
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="usd")

    # When the auction was won and the ad set aside for this salon.
    broadcast_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # When it was actually spoken. NULL means reserved and never delivered — the host closed
    # their tab, or the worker died, between the salon opening and the greeting ending.
    #
    # The row is kept rather than deleted, so the gap between reserved and heard is measurable
    # instead of invisible. Nothing NULL is ever invoiced, and no allowance is spent on it:
    # charging an advertiser for a sentence nobody heard is the one outcome this must not
    # produce.
    delivered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # NULL until this broadcast has been put on a Stripe invoice. That makes the invoicing
    # run idempotent: it selects rows where this is NULL, and a run interrupted halfway
    # cannot bill anything twice.
    stripe_invoice_item_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    invoiced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        # A free broadcast is a real case — a promotion, a make-good — but a negative one is
        # a credit, and credits do not belong in a table of things that happened.
        CheckConstraint("amount_cents >= 0", name="ck_ad_broadcasts_amount"),
        # Either both are set or neither. A row with an invoice item and no timestamp cannot
        # be reconciled, and one with a timestamp and no item was never actually billed.
        CheckConstraint(
            "(stripe_invoice_item_id IS NULL AND invoiced_at IS NULL) OR "
            "(stripe_invoice_item_id IS NOT NULL AND invoiced_at IS NOT NULL)",
            name="ck_ad_broadcasts_invoiced_consistent",
        ),
        # The guarantee, in the schema rather than in a query somebody has to write correctly:
        # a charge cannot exist for something that was never spoken.
        CheckConstraint(
            "stripe_invoice_item_id IS NULL OR delivered_at IS NOT NULL",
            name="ck_ad_broadcasts_billed_only_if_delivered",
        ),
    )


# ─── The cascade that should not be there ────────────────────────────────────
#
# ads.advertiser_id still cascades from advertisers. Deleting an advertiser would therefore
# try to delete their ads — and now fail, because this table's RESTRICT blocks it once
# anything has been broadcast. That is the safe failure, but it is accidental: the delete
# succeeds for an advertiser who never ran anything and fails for one who did.
#
# The honest shape is RESTRICT there too, or a status of 'closed' instead of a delete. Left
# as it is because changing it is a separate decision about what removing an advertiser is
# supposed to mean, and guessing would be worse than the inconsistency.
