"""Signing up with an address, a number, or both (Story 10.1, replacing FR27).

An identifier is required, and that requirement is the story. Anonymous access left nothing to
key an allowance to: somebody who spent their welcome credit could have it back by arriving
again as a stranger, and no amount of accounting downstream could notice.

So the identifier is what the welcome credit (FR51) belongs to. Not the account, which anybody
can make again; not the Salon, which anybody can recreate; not the role, which the same person
changes between hosting and being invited. Registering with an identifier that has been seen
before returns the person it belongs to, credit already settled or not.

Which makes normalisation load-bearing rather than tidy. `Marie@Example.COM` and
`marie@example.com` are one person, and a key that treated them as two would hand a second
grant to anybody who pressed shift. Numbers are worse, since every form of punctuation in
them is optional.

**What this does not do.** It resolves and keys; it does not merge. Two identifiers already
belonging to two different people are refused rather than joined: combining two accounts is a
decision nobody has made, and picking one silently would discard the other's history.

This used to also key a ten-minute lifetime quota, alongside the inherited host trial
(`free_trial_limit_seconds`, an hour). Three free allowances coexisted here and none was wired
to the live path — retired 2026-08-09, before any of them could be. The welcome credit is the
one that stayed.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from src.credit import grant_welcome_credit
from src.models.participant_identifier import ParticipantIdentifier
from src.models.user import User


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
    """Find the person these identifiers belong to, or make them, key both to them, and grant
    the welcome credit (FR51) unless one of these identifiers already had it.

    Returning rather than creating is the whole mechanism: a second signup with an identifier
    already used is the same person, which is what makes the credit un-grantable a second
    time by the same route that grants it the first.
    """
    now = now or datetime.now(timezone.utc)
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

    # Refused rather than raised when it was already given: register() is called on every
    # sign-in, not only the first, and a returning person is not a failed signup.
    grant_welcome_credit(db, subject_id=person.id, identifiers=wanted, now=now)
    # Flushed like everything else here, and for the reason `credit.debit` gives: the grant
    # is an unflushed insert until something sends it, so a caller reading the balance back
    # on a session with autoflush off would be told the credit was never given.
    db.flush()

    return person
