import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # Account identifier: registered users (i.e. hosts) sign in with an email OTP.
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)

    # Optional now that sign-in is email-based. Still the only key that correlates an
    # invitation of a guest without an account to the account they later register
    # (see invitation_service.link_prior_invitations), so it is kept, not dropped.
    phone_number: Mapped[str | None] = mapped_column(
        String(20), unique=True, nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # OTP verification (cleared once verified)
    otp_code: Mapped[str | None] = mapped_column(String(10), nullable=True)
    otp_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    otp_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Trial tracking (seconds used as host)
    trial_seconds_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Post-trial billing: cumulative host seconds already charged to Stripe.
    # billable-so-far = max(0, trial_seconds_used - free_trial_limit); the delta
    # between that and billed_seconds is what remains to be charged.
    billed_seconds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Detected spoken language (BCP-47 code, e.g. "fr", "en") — set by agent on first detection
    detected_language: Mapped[str | None] = mapped_column(String(10), nullable=True)

    # The two languages this person *chose*, as opposed to the one above, which is what they
    # were heard speaking. Kept on the account because a choice follows the person: setting the
    # interface to Polish on a laptop and meeting English on a phone is the thing this fixes.
    #
    # NULL means never chosen, and the clients then fall back to the browser or device
    # language. For captions that distinction is load-bearing rather than tidy: the empty
    # string is itself a choice there — "as spoken", translate nothing — so a column that
    # collapsed NULL and "" could not offer a default without overriding a decision.
    interface_language: Mapped[str | None] = mapped_column(String(10), nullable=True)
    caption_language: Mapped[str | None] = mapped_column(String(10), nullable=True)

    # Stripe billing
    stripe_customer_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    stripe_payment_method_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
