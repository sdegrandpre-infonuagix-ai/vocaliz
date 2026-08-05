"""Whether an outside service is answering us, remembered between probes.

One row per service, and its only purpose is to make an alert fire once.

A probe every minute that emailed on every failure would send more than a thousand messages
during one bad night, and an inbox with a thousand identical alerts is an inbox where the next
real one is missed. What the administrator needs to know is that something *changed* — it broke,
or it came back — and a transition cannot be detected without remembering the previous state.
"""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from src.database import Base


class ServiceHealth(Base):
    __tablename__ = "service_health"

    # "xai" today. A name rather than an enum: the next service to be watched should not need a
    # migration to be watchable.
    service: Mapped[str] = mapped_column(String(40), primary_key=True)
    healthy: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # When it last changed, not when it was last probed. A row untouched for a week means a week
    # without incident, which is the more useful reading of a timestamp here.
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # What the failure said, kept so the alert can quote it rather than saying "something went
    # wrong". Empty while healthy.
    detail: Mapped[str] = mapped_column(Text, nullable=False, default="")
