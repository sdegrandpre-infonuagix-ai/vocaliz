"""Getting your money back when every way in has failed (Story 10.7 / FR65, FR51).

Somebody with no reachable identifier and no password still paid for something. This is the
route that returns that money, and its shape follows from one observation: **holding the card
that paid does not prove you are the account holder.** Cards are shared between partners,
inherited, and issued by employers. So a successful check here opens the **refund of what was
paid** and nothing else — returning money to whoever paid it and returning access to somebody's
conversations are two different decisions, and only the first is made here.

A test reads this module to check it never touches a token, a password or a username. The
separation is the whole safeguard, and prose alone would not keep it.

**More than the last four digits.** Four digits are ten thousand guesses and are printed on
receipts, so on their own they prove nothing. An expiry date is one of about sixty and is on the
same receipt. What an impostor generally cannot produce is what was charged, or when — so at
least three elements must agree, and one of them has to be a transaction detail.

**A recovery path is also an attack path**, so attempts are counted and written down. Limited
rather than permanent: a lockout with no end is a denial of service anybody can inflict on
somebody else's account by guessing badly at it.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from src.ledger import as_utc, paid_balance
from src.models.recovery_attempt import RecoveryAttempt

# Three concordant elements, of which one must be a transaction detail.
REQUIRED_ELEMENTS = 3

MAX_ATTEMPTS = 5
# Long enough to stop somebody working through a space, short enough that a real person who
# misremembered their own card is not locked out for good.
ATTEMPT_WINDOW = timedelta(hours=24)


class RecoveryRefused(ValueError):
    """The card was not proved, or too many tries have been made."""


@dataclass(frozen=True)
class CardEvidence:
    """What somebody says about the card, or what is actually on file.

    The same shape for both sides, so the comparison is field against field with nothing to
    line up by hand.
    """

    last_four: str
    expiry: str | None
    recent_amount_cents: int | None
    recent_charge_on: date | None


def _agrees(given, known) -> bool:
    """Whether an offered element matches a known one that actually exists.

    An absent value on either side agrees with nothing. Treating a missing field as a match
    would make an account with no card on file pass every check vacuously.
    """
    return given is not None and known is not None and given == known


def verify_card(given: CardEvidence, *, on_file: CardEvidence) -> bool:
    """Whether enough elements agree to believe this person holds the card.

    Concordant, not merely numerous: three answers of which one is wrong is somebody guessing,
    so a single disagreement fails the whole check rather than being outvoted.
    """
    if not on_file.last_four:
        # No card on file. There is nothing to prove, and every comparison would be vacuous.
        return False

    offered = {
        "last_four": (given.last_four or None, on_file.last_four or None),
        "expiry": (given.expiry, on_file.expiry),
        "amount": (given.recent_amount_cents, on_file.recent_amount_cents),
        "charged_on": (given.recent_charge_on, on_file.recent_charge_on),
    }

    agreed = []
    for name, (said, known) in offered.items():
        if said is None:
            continue
        if not _agrees(said, known):
            return False
        agreed.append(name)

    if len(agreed) < REQUIRED_ELEMENTS:
        return False
    # The last four and the expiry are both on a receipt. Without a transaction detail this
    # is a check somebody passes holding a piece of paper rather than a card.
    return bool({"amount", "charged_on"} & set(agreed))


def attempts_left(db: Session, subject_id: uuid.UUID, *, now: datetime) -> int:
    """How many tries remain inside the current window."""
    since = now - ATTEMPT_WINDOW
    recent = [
        row
        for row in db.query(RecoveryAttempt)
        .filter(RecoveryAttempt.subject_id == subject_id)
        .all()
        if as_utc(row.attempted_at) >= since
    ]
    return max(0, MAX_ATTEMPTS - len(recent))


def record_attempt(
    db: Session, subject_id: uuid.UUID, *, succeeded: bool, now: datetime
) -> RecoveryAttempt:
    """Write down that somebody tried, and how it went.

    Successes are recorded as well as failures. A recovery that worked is the more
    interesting row of the two when an account is later disputed.
    """
    row = RecoveryAttempt(subject_id=subject_id, succeeded=succeeded, attempted_at=now)
    db.add(row)
    return row


def refundable_cents(
    db: Session,
    subject_id: uuid.UUID,
    *,
    given: CardEvidence,
    on_file: CardEvidence,
    now: datetime,
) -> int:
    """What may be returned to whoever paid it, once the card is proved.

    The **paid** balance and nothing else (FR51). A gifted credit was never their money, so
    there is nothing of theirs to give back — refunding a gift would be Vocaliz paying
    somebody to lose access to their account.

    Raises rather than returning zero on a refusal: nothing to refund and not allowed to
    refund are different answers, and a caller reading `0` cannot tell them apart.
    """
    if attempts_left(db, subject_id, now=now) <= 0:
        raise RecoveryRefused(
            "Too many verification attempts have been made on this account recently. "
            "Please try again tomorrow, or contact support."
        )

    proved = verify_card(given, on_file=on_file)
    record_attempt(db, subject_id, succeeded=proved, now=now)
    db.flush()

    if not proved:
        raise RecoveryRefused(
            "Those card details do not match what is on file. At least three must agree, "
            "and one of them has to be the amount or the date of a recent charge."
        )

    return max(0, paid_balance(db, subject_id).balance_cents)
