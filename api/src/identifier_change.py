"""Changing an identifier without losing the account (Story 10.6 / FR64).

An identifier is the key to somebody's balance, so changing one is changing a lock while a
person is standing behind it. What makes that safe is the **anchor**: exactly one identifier
moves at a time, and the other stays as the thing that still ties the account to whoever held
it yesterday.

Changing both at once is refused, and not for want of a way to write two columns. It is that
afterwards nothing about the account resembles what it was, and nothing can say the person
holding it now is the person who held it before. The same reasoning refuses a change on an
account with a single identifier: the second must be added first, precisely so there is
something to anchor to.

The burned registry does not enter into it. That table stops a *gift* being given twice, so an
identifier in it means somebody once had a welcome credit for it — not that it is forbidden
ground. Reading it as a blocklist would leave somebody unable to reuse an address they burned
themselves, years ago.

And a change touches no money. The gifted balance keeps its current amount — not reassigned,
not topped up, not reset to five dollars — and nothing here writes to the ledger, because a
change of address is not a financial event and a stream whose every row moved something should
not gain one that moved nothing.
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from src.models.burned_identifier import BurnedIdentifier
from src.models.participant_identifier import ParticipantIdentifier
from src.models.pending_identifier_change import PendingIdentifierChange
from src.models.user import User
from src.signup import find_by_identifier, normalise_email, normalise_phone

# The same six digits and the same short life as the signup code. A verification good for a
# week is one somebody else can use after an address changes hands — which is exactly the
# situation this feature exists to handle.
CODE_LIFETIME = timedelta(minutes=15)
CODE_DIGITS = 6


class ChangeRefused(ValueError):
    """A change that cannot be made, with the reason spelled out for a human.

    Always names the identifier or the missing piece. "Refused" on its own sends somebody
    back to a form to guess which half of it was the problem.
    """


@dataclass(frozen=True)
class PlannedChange:
    """What is about to happen, once somebody proves they hold the new identifier."""

    row: PendingIdentifierChange

    @property
    def new_identifier(self) -> str:
        return self.row.new_identifier

    @property
    def anchor(self) -> str:
        return self.row.anchor

    @property
    def replaces(self) -> str:
        return self.row.replaces

    @property
    def code(self) -> str:
        return self.row.code


def _identifiers_of(person: User) -> tuple[str, str]:
    """This account's address and number, normalised. Either may be empty."""
    return normalise_email(person.email), normalise_phone(person.phone_number)


def plan_change(
    db: Session,
    person: User,
    *,
    new_email: str | None = None,
    new_phone: str | None = None,
    now: datetime | None = None,
) -> PlannedChange:
    """Check that a change is allowed and set it aside for verification.

    Nothing takes effect here. The account is untouched until `apply_change`, which will not
    run without the code — a change that took effect on request would let anybody holding a
    session move somebody's key to an address they control.
    """
    wanted_email = normalise_email(new_email) if new_email is not None else ""
    wanted_phone = normalise_phone(new_phone) if new_phone is not None else ""

    if wanted_email and wanted_phone:
        raise ChangeRefused(
            "Only one identifier may change at a time. The other is the anchor — the thing "
            "that still ties this account to the person it belongs to — and changing both "
            "would leave nothing to anchor to."
        )
    if not wanted_email and not wanted_phone:
        raise ChangeRefused(
            "Give a new email address or a new phone number. "
            "Neither was supplied, so there is nothing to change."
        )

    address, number = _identifiers_of(person)
    if wanted_email:
        wanted, replaces, anchor = wanted_email, address, number
    else:
        wanted, replaces, anchor = wanted_phone, number, address

    if not anchor:
        raise ChangeRefused(
            "This account has only one identifier, so there is nothing to anchor a change "
            "to. Add the second one first — it becomes the anchor — and then this one can "
            "move."
        )

    if wanted in (address, number):
        raise ChangeRefused(f"{wanted} is already on this account, so nothing would change.")

    owner = find_by_identifier(db, wanted)
    if owner is not None and owner.id != person.id:
        raise ChangeRefused(
            f"{wanted} already belongs to another account. Two people cannot hold one key, "
            "so this one cannot be moved onto it."
        )

    # The burned registry is deliberately not consulted. It records that a welcome credit was
    # once paid for an identifier, which is a fact about a gift and not about who may use it.

    row = PendingIdentifierChange(
        user_id=person.id,
        new_identifier=wanted,
        anchor=anchor,
        replaces=replaces,
        code="".join(random.choices("0123456789", k=CODE_DIGITS)),
    )
    if now is not None:
        row.requested_at = now
    db.add(row)
    db.flush()
    return PlannedChange(row=row)


def _as_utc(moment: datetime) -> datetime:
    """SQLite hands a stamped instant back naive; comparing it to an aware one raises."""
    from datetime import timezone

    return moment if moment.tzinfo is not None else moment.replace(tzinfo=timezone.utc)


def verify_code(
    db: Session, planned: PlannedChange, *, code: str, now: datetime
) -> bool:
    """Whether this code proves the person holds the new identifier, right now.

    A spent change verifies as false whatever the code: the one-time part is the point, and
    a code that keeps working is a code worth stealing.
    """
    row = planned.row
    if row.used_at is not None:
        return False
    if _as_utc(row.requested_at) + CODE_LIFETIME < now:
        return False
    return code == row.code


def apply_change(
    db: Session, planned: PlannedChange, *, code: str, now: datetime
) -> User:
    """Move the identifier, once the code has been given.

    The code is checked here rather than trusted from a caller that verified separately:
    two steps with the gate in the first is one refactor away from a change that applies
    without one.

    What moves: the account column, the registry key, and the burn of the new identifier —
    so the account it now belongs to cannot be handed a second welcome credit through it. The
    old key is **withdrawn**, because it is not theirs any more and leaving it would let
    somebody who recovered the old address walk back into an account that has moved on.

    What does not move: any balance, and anything in the ledger.
    """
    if not verify_code(db, planned, code=code, now=now):
        raise ChangeRefused(
            "That code does not match, or it has expired. Ask for another and try again."
        )

    row = planned.row
    person = db.get(User, row.user_id)
    if person is None:
        raise ChangeRefused("This account no longer exists, so there is nothing to change.")

    if "@" in row.new_identifier:
        person.email = row.new_identifier
    else:
        person.phone_number = row.new_identifier

    db.query(ParticipantIdentifier).filter(
        ParticipantIdentifier.identifier == row.replaces,
        ParticipantIdentifier.user_id == person.id,
    ).delete(synchronize_session=False)

    already = (
        db.query(ParticipantIdentifier)
        .filter(ParticipantIdentifier.identifier == row.new_identifier)
        .first()
    )
    if already is None:
        db.add(
            ParticipantIdentifier(
                identifier=row.new_identifier, user_id=person.id, added_at=now
            )
        )

    if db.get(BurnedIdentifier, row.new_identifier) is None:
        db.add(
            BurnedIdentifier(
                identifier=row.new_identifier, burned_at=now, granted_to=person.id
            )
        )

    row.used_at = now
    db.flush()
    return person
