"""Signing up with an address, a number, or both (Story 10.1, replacing FR27).

An identifier is required, and that requirement is the story. Anonymous access left nothing to
key an allowance to: somebody who used up their free minutes could have them back by arriving
again as a stranger, and no amount of accounting downstream could notice.

So the identifier is what the ten-minute lifetime quota belongs to. Not the account, which
anybody can make again; not the Salon, which anybody can recreate; not the role, which the
same person changes between hosting and being invited. Registering with an identifier that has
been seen before returns the person it belongs to, with whatever they have left.

Which makes normalisation load-bearing rather than tidy. `Marie@Example.COM` and
`marie@example.com` are one person, and a key that treated them as two would hand a second
lifetime allowance to anybody who pressed shift. Numbers are worse, since every form of
punctuation in them is optional.

**What this does not do.** It resolves and keys; it does not merge. Two identifiers already
belonging to two different people are refused rather than joined: combining two allowances is a
decision nobody has made, and picking one silently would discard the other's history.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from src.models.participant_identifier import ParticipantIdentifier
from src.models.user import User

# Ten minutes, for a lifetime, per identifier. A number here rather than in `config.py` for
# the same reason the Salon's parameters are not there: this is a product decision, not a
# deployment one.
#
# It sits beside the welcome credit of Story 8.2 (500 cents, about a hundred minutes at Base)
# and the inherited host trial (`free_trial_limit_seconds`, an hour). Three free allowances is
# two too many, and reconciling them is a product decision rather than a refactor — none of
# the three is wired to the live path yet, which is the moment to settle it.
LIFETIME_QUOTA_SECONDS = 600


class InvalidRegistration(ValueError):
    """A signup that cannot be honoured, with the reason spelled out for a human.

    Always says what was wrong with the values given. An error naming only the field sends
    somebody back to a form to guess what it did not like about what they typed.
    """


def normalise_email(value: str | None) -> str:
    """One address, however it was typed. Empty string when there is none.

    Lowercased whole. The local part is technically case-sensitive and in practice never is,
    and treating it as sensitive would mean `Marie@` and `marie@` are two people with two
    lifetime quotas — a worse error than the one being avoided.
    """
    return (value or "").strip().lower()


def normalise_phone(value: str | None) -> str:
    """One number, minus its decoration. Empty string when there is none.

    Digits, and a leading plus if there was one. Spaces, dashes, brackets and dots are how
    the same number gets written six ways; keeping any of them would make each of those a
    separate key.
    """
    raw = (value or "").strip()
    if not raw:
        return ""
    digits = "".join(character for character in raw if character.isdigit())
    if not digits:
        return ""
    return f"+{digits}" if raw.startswith("+") else digits


def identifiers_of(*, email: str | None, phone: str | None) -> list[str]:
    """Everything this signup can be keyed on, normalised, in the order given.

    At least one, or nothing to key an allowance to. A form submitted empty is not a form
    submitted with a value of nothing, so blanks are refused rather than stored.
    """
    found = [value for value in (normalise_email(email), normalise_phone(phone)) if value]
    if not found:
        raise InvalidRegistration(
            "An email address or a phone number is required. Without one there is nothing "
            "to hold the ten free minutes against, and they would start again tomorrow."
        )
    return found


def find_by_identifier(db: Session, identifier: str) -> User | None:
    """Who this address or number belongs to, or nobody.

    The registry first, then the account columns. An account that predates the registry has
    its address on `users` and no row here, and not finding it would hand somebody who has
    been using Vocaliz for months a fresh lifetime quota.
    """
    row = (
        db.query(ParticipantIdentifier)
        .filter(ParticipantIdentifier.identifier == identifier)
        .first()
    )
    if row is not None:
        return db.get(User, row.user_id)

    by_email = db.query(User).filter(User.email == identifier).first()
    if by_email is not None:
        return by_email
    return db.query(User).filter(User.phone_number == identifier).first()


def register(
    db: Session,
    *,
    email: str | None = None,
    phone: str | None = None,
    now: datetime | None = None,
) -> User:
    """Find the person these identifiers belong to, or make them, and key both to them.

    Returning rather than creating is the whole mechanism: a second signup with an identifier
    already spent is the same person with what they have left, which is what makes the quota
    survive a new account, a new Salon and a change of role.
    """
    wanted = identifiers_of(email=email, phone=phone)

    found = {}
    for identifier in wanted:
        person = find_by_identifier(db, identifier)
        if person is not None:
            found[person.id] = person

    if len(found) > 1:
        owners = ", ".join(sorted(str(person_id) for person_id in found))
        raise InvalidRegistration(
            f"these identifiers already belong to different people ({owners}). Merging two "
            "accounts would combine two lifetime allowances and discard one history, which "
            "is a decision for a human rather than a signup form."
        )

    person = next(iter(found.values()), None)
    if person is None:
        person = User(id=uuid.uuid4())
        db.add(person)

    # Written onto the account as well as into the registry. The account columns are what the
    # rest of Vocaliz already reads — sign-in, invitations, the participant report — and
    # leaving them empty would make a registered person invisible to all of it.
    normalised_email = normalise_email(email)
    normalised_phone = normalise_phone(phone)
    if normalised_email:
        person.email = normalised_email
    if normalised_phone:
        person.phone_number = normalised_phone

    db.flush()

    known = {
        row.identifier
        for row in db.query(ParticipantIdentifier)
        .filter(ParticipantIdentifier.user_id == person.id)
        .all()
    }
    for identifier in wanted:
        if identifier not in known:
            db.add(
                ParticipantIdentifier(
                    identifier=identifier, user_id=person.id, added_at=now
                )
            )
    db.flush()
    return person


def quota_remaining_seconds(db: Session, person: User) -> int:
    """What is left of the ten minutes, never below zero.

    Never negative: somebody may overrun the last few seconds of an allowance, and a negative
    remainder would read as a debt. This is an allowance, not a balance.
    """
    db.flush()
    return max(0, LIFETIME_QUOTA_SECONDS - (person.trial_seconds_used or 0))
