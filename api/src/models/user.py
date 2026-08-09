import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, CheckConstraint, DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.database import Base


class User(Base):
    __tablename__ = "users"

    # Declared alongside the migration, not only in it: a constraint that lives only in a
    # migration is invisible to the test database, which is built from these models. That gap
    # let an anonymous invitation meet an unmet CHECK for the first time in production.
    __table_args__ = (
        CheckConstraint(
            "caption_scale IS NULL OR (caption_scale BETWEEN 50 AND 300)",
            name="ck_users_caption_scale",
        ),
        # Story 10.1. An address, a number, or both — and never neither. Anonymous access
        # left nothing to hold the lifetime quota against, so somebody who had used theirs
        # could have it back by arriving again as a stranger. The rule is in the schema
        # rather than only in the signup path because it is the signup path's whole point.
        CheckConstraint(
            "email IS NOT NULL OR phone_number IS NOT NULL",
            name="ck_users_one_identifier",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # Account identifier: registered users sign in with an email OTP.
    #
    # Nullable since Story 10.1, which lets somebody sign up with a telephone number alone —
    # a person invited by telephone has a number and no address, and demanding one anyway
    # would be demanding a second identifier to prove the first. The CHECK above is what
    # keeps "either" from becoming "neither". Note the consequence: sign-in is by email OTP,
    # so a number-only person can be identified and cannot yet sign in.
    email: Mapped[str | None] = mapped_column(
        String(320), unique=True, nullable=True, index=True
    )

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
    # Story 9.1 / FR50. Nullable on purpose: three states, not two. `None` means nobody has
    # asked yet, which is neither a yes nor a no — reading silence either way would put words
    # in somebody's mouth. Only an explicit True permits location-chosen advertising.
    location_consent: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    location_consent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

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

    # How large this person reads their captions, as a whole percentage — 85, 100, 120. Not a
    # multiplier: the client compares the stored value against a fixed list of steps, and 1.2
    # read back from a database is not reliably the 1.2 in that list.
    #
    # NULL means never chosen, so the device keeps whatever size it already had rather than
    # jumping on first sign-in.
    caption_scale: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Stripe billing
    stripe_customer_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    stripe_payment_method_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
