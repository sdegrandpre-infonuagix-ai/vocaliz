"""The pool of six-digit codes guests dial to join a salon by telephone.

A call carries no URL, so the one-time join link is useless to someone dialling in. These
codes replace it: LiveKit answers, collects the digits on the keypad, and places the caller
in the room that code belongs to.

TWO COLUMNS, AND NO MORE. This table answers one question — is this code free? — and holds
nothing else. Which salon a code reaches is not here: it is on the invitation that was sent
the code, which is also where the guest's address and number live. One lookup therefore
gives both the room and who is calling, and there is no second copy of the mapping to drift
out of step.

ONE CODE PER INVITATION. A code shared by a whole salon would leave the caller anonymous —
no address, and no number when the caller id is withheld — and salon_events requires one of
the two, so the participation could not be recorded at all.
"""
from sqlalchemy import Boolean, CheckConstraint, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from src.database import Base

CODE_DIGITS = 6


def digits_only(column: str) -> str:
    """A CHECK expression asserting that `column` holds nothing but digits.

    A chain of replaces rather than a regular expression, deliberately. Postgres would
    write `code ~ '^[0-9]{6}$'` and SQLite `code GLOB '[0-9]...'` — two different strings
    meaning the same thing, one enforced in production and the other in the tests, free to
    drift the day somebody edits one of them. Stripping every digit and requiring nothing
    to remain is uglier and runs identically on both, so the tests verify the rule exactly
    as production enforces it.
    """
    expression = column
    for digit in "0123456789":
        expression = f"replace({expression}, '{digit}', '')"
    return f"length({expression}) = 0"


class CodeAvailable(Base):
    """One telephone code, free or in use."""

    __tablename__ = "code_available"

    # The code is the key. It is what a caller types and what the dispatcher looks up, so
    # anything else would be a second identity for one thing.
    code: Mapped[str] = mapped_column(String(CODE_DIGITS), primary_key=True)

    # False from the moment the code is sent out until the guest leaves the salon. Not
    # inferred from anything else: reservation is a fact of its own, and a claim that had
    # to be deduced from a join would be a claim two requests could both win.
    available: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, index=True
    )

    # When it was taken. Not part of the question this table answers, but the only way to
    # notice a code that leaked — a salon that never ended leaves its codes reserved
    # forever, and without a timestamp nothing can tell that from a code in honest use.
    claimed_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        # Six digits, not six characters. A keypad cannot enter a letter, so "12a456"
        # would be a code nobody could ever dial — stored, reserved and unreachable.
        CheckConstraint(
            f"length(code) = {CODE_DIGITS} AND {digits_only('code')}",
            name="ck_code_available_digits",
        ),
        # A free code cannot carry a claim time, and a reserved one must. This is what stops
        # the two facts from contradicting each other.
        CheckConstraint(
            "(available AND claimed_at IS NULL) OR (NOT available AND claimed_at IS NOT NULL)",
            name="ck_code_available_consistent",
        ),
    )
