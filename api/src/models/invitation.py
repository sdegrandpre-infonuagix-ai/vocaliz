import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.database import Base


class Invitation(Base):
    __tablename__ = "invitations"

    # Declared here as well as in the migration, and that is the whole lesson of this
    # constraint. It lived only in migration 016, so the test database — built from these
    # models — never had it, and the first thing to violate it did so in production: an
    # anonymous invitation, which carries no address by design, met a rule demanding one.
    #
    # Each kind of invitation states its own shape. An anonymous link must have neither
    # channel, so it cannot quietly carry an address while claiming not to; every other kind
    # must have at least one, so a host who typed nothing is refused rather than handed a link
    # addressed to no one.
    __table_args__ = (
        CheckConstraint(
            "(invitation_type = 'anonymous_link' AND guest_email = '' AND guest_phone = '')"
            " OR (invitation_type <> 'anonymous_link'"
            " AND (guest_email <> '' OR guest_phone <> ''))",
            name="ck_invitations_contact",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    host_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    # Who is invited
    # Guests are invited by email; the join link is emailed via SES.
    guest_email: Mapped[str] = mapped_column(String(320), nullable=False, index=True)

    # Kept nullable for invitations created before the switch to email.
    guest_phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # Six digits, so a guest can join by telephone: a call carries no URL, so the one-time
    # link is useless to someone dialling in. LiveKit collects these on the keypad and
    # places the caller in the room whose dispatch rule carries them.
    #
    # Per invitation rather than per salon, deliberately. A code shared by a whole salon
    # would leave the caller anonymous — no address, and no number either when the caller
    # id is withheld — and salon_events requires one of the two. Tied to an invitation, the
    # code identifies the guest through what the host already typed.
    phone_pin: Mapped[str | None] = mapped_column(String(6), nullable=True)

    guest_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # 'salon_friend' → in-app notification, 'sms_contact' → SMS with join link
    invitation_type: Mapped[str] = mapped_column(String(20), nullable=False)
    join_token: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Friend(Base):
    __tablename__ = "friends"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    friend_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
