from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from src.database import Base


class SalonEvent(Base):
    """One participation: who was in which salon, for how long, and how it went.

    Encryption at rest is the Aurora cluster's, not this table's — the storage is
    KMS-encrypted, which covers snapshots and backups too. Nothing here is encrypted at
    the column level, so anyone holding SQL access reads these values in clear. That was
    a deliberate choice: column encryption would have forced a deterministic scheme on the
    key columns and ruled out every query but equality.

    The row still holds personal data — an email, an IP, sometimes a precise position. It
    deserves a retention rule; there is none yet.
    """

    __tablename__ = "salon_events"

    # Composite key: one row per person, per role, per salon. Re-entering the same salon
    # updates that row rather than adding a second one — a participation, not a visit log.
    #
    # IP and GPS were initially meant to be part of this key. They are not, and could not
    # be: a primary key column cannot be NULL, and the position is missing whenever the
    # browser refuses it.
    email: Mapped[str] = mapped_column(String(320), primary_key=True)
    user_type: Mapped[str] = mapped_column(String(5), primary_key=True)
    salon_name: Mapped[str] = mapped_column(String(100), primary_key=True)

    # Nullable on purpose. The address is normally supplied by API Gateway, but a proxy
    # can hide it, and a row worth keeping should not be lost over a missing header.
    client_ip: Mapped[str | None] = mapped_column(String(45), nullable=True)

    # BCP-47 code for the first language this person was heard speaking *in this salon* —
    # not the language of the interface they clicked through, and not a property of the
    # person. Someone may hold one conversation in French and the next in English, which
    # is why this lives on the participation rather than on the account.
    #
    # First rather than predominant, deliberately: "first heard" is a single event the
    # agent can report once and never revise, where "predominant" would need continuous
    # weighing and a rule for when the balance tips. The cost is that someone who opens in
    # English and continues in French is recorded as English — rare in ten minutes.
    #
    # Written once. A later report is ignored rather than overwriting, so the column
    # keeps meaning what its name says.
    first_spoken_language: Mapped[str | None] = mapped_column(String(10), nullable=True)

    # Precision is fixed rather than floating: these are coordinates, compared and stored
    # as given. Six decimals is about eleven centimetres, far beyond what a browser
    # reports. NULL whenever the participant declined the location prompt, which is the
    # common case and not an error.
    gps_latitude: Mapped[float | None] = mapped_column(Numeric(8, 6), nullable=True)
    gps_longitude: Mapped[float | None] = mapped_column(Numeric(9, 6), nullable=True)

    entered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    exited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Three states, and the third is not a failure: TRUE and FALSE are answers, NULL means
    # the question was never asked or never answered — a participant who simply closed
    # the tab. Collapsing NULL into FALSE would invent dissatisfaction that nobody voiced.
    enjoyed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    __table_args__ = (
        CheckConstraint("user_type IN ('host', 'guest')", name="ck_salon_events_user_type"),
    )
