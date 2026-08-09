"""Signing up with an address, a number, or both (FR27 replaced).

The point of the story is not the form. It is that the identifier becomes the **key** to the
welcome credit (FR51), so it cannot be reset by making a new Salon, taking a different role,
or signing up again with the same address typed differently.

Which makes normalisation load-bearing rather than tidy. `Marie@Example.COM ` and
`marie@example.com` are one person, and a key that treated them as two would hand out a second
lifetime allowance to anybody who pressed shift. The same goes for a number written with
spaces, dashes or brackets.

Two identifiers on one person are two keys to one quota, and either finds it. That is what
"whatever their role" means in practice: somebody invited as a guest by telephone and later
signing in by email is one person with one allowance, not two accounts with one each.
"""
import uuid

import pytest

from src.credit import WELCOME_CREDIT_CENTS, balance
from src.models.participant_identifier import ParticipantIdentifier
from src.models.user import User
from src.signup import (
    InvalidRegistration,
    find_by_identifier,
    identifiers_of,
    normalise_email,
    normalise_phone,
    register,
)


# ── One identifier is enough, and one is required ─────────────────────────────


def test_an_address_alone_is_enough(db):
    person = register(db, email="marie@example.com")

    assert person.email == "marie@example.com"


def test_a_number_alone_is_enough(db):
    """Somebody who joined by telephone has a number and no address. Demanding one anyway
    would be demanding a second identifier to prove the first."""
    person = register(db, phone="+15145550123")

    assert person.phone_number == "+15145550123"
    assert person.email is None


def test_both_may_be_given(db):
    person = register(db, email="marie@example.com", phone="+15145550123")

    assert (person.email, person.phone_number) == ("marie@example.com", "+15145550123")


def test_neither_is_refused(db):
    """No anonymous access. There is nothing to key a quota to, so there is nothing to
    stop somebody starting again tomorrow."""
    with pytest.raises(InvalidRegistration):
        register(db)


def test_blank_strings_are_not_identifiers(db):
    """A form submitted empty is not a form submitted with a value of nothing."""
    with pytest.raises(InvalidRegistration):
        register(db, email="   ", phone="")


# ── One person, however they type it ──────────────────────────────────────────


def test_an_address_is_the_same_address_in_any_case():
    assert normalise_email("  Marie@Example.COM ") == "marie@example.com"


def test_a_number_keeps_its_country_and_loses_its_decoration():
    assert normalise_phone(" +1 (514) 555-0123 ") == "+15145550123"


def test_a_number_written_two_ways_is_one_identifier(db):
    first = register(db, phone="+1 514 555-0123")

    again = register(db, phone="+15145550123")

    assert again.id == first.id


def test_an_address_typed_in_capitals_is_the_same_person(db):
    first = register(db, email="marie@example.com")

    again = register(db, email="MARIE@EXAMPLE.COM")

    assert again.id == first.id


def test_punctuation_with_no_digits_is_not_a_number():
    """`+()` is a form somebody gave up on halfway. Keeping the plus would store `+` as a
    key, and the next person to give up would find themselves already registered."""
    assert normalise_phone("+( ) -") == ""


def test_identifiers_of_refuses_an_empty_pair():
    with pytest.raises(InvalidRegistration):
        identifiers_of(email=None, phone=None)


def test_identifiers_of_returns_both_normalised():
    assert identifiers_of(email="Marie@Example.com", phone="+1 514 555-0123") == [
        "marie@example.com",
        "+15145550123",
    ]


# ── Coming back ───────────────────────────────────────────────────────────────


def test_signing_up_again_is_the_same_person(db):
    first = register(db, email="marie@example.com")

    again = register(db, email="marie@example.com")

    assert again.id == first.id
    assert db.query(User).count() == 1


def test_either_identifier_finds_the_person(db):
    """Two keys to one quota. Somebody invited by telephone and later signing in by email is
    one person with one allowance, not two accounts with one each."""
    first = register(db, email="marie@example.com", phone="+15145550123")

    by_phone = register(db, phone="+15145550123")
    by_email = register(db, email="marie@example.com")

    assert by_phone.id == first.id == by_email.id


def test_a_second_identifier_is_added_to_the_person_who_returns(db):
    """They gave an address first and a number later. The number becomes a key too, rather
    than a second account."""
    first = register(db, email="marie@example.com")

    again = register(db, email="marie@example.com", phone="+15145550123")

    assert again.id == first.id
    assert again.phone_number == "+15145550123"
    assert find_by_identifier(db, "+15145550123").id == first.id


def test_two_people_are_not_merged_by_a_shared_registration(db):
    """Each identifier already belongs to somebody different. Picking one would silently
    discard the other's history, and merging two allowances is a decision nobody has made —
    so it is refused and a human is told."""
    marie = register(db, email="marie@example.com")
    hans = register(db, phone="+15145550123")

    with pytest.raises(InvalidRegistration) as raised:
        register(db, email="marie@example.com", phone="+15145550123")

    assert str(marie.id) in str(raised.value)
    assert str(hans.id) in str(raised.value)


def test_an_account_that_predates_the_registry_is_still_found(db):
    """A host who signed up before this story has an address on `users` and no row in the
    identifier table. Not finding them would hand them a fresh lifetime quota."""
    existing = User(id=uuid.uuid4(), email="old@example.com")
    db.add(existing)
    db.commit()

    person = register(db, email="old@example.com")

    assert person.id == existing.id
    assert find_by_identifier(db, "old@example.com").id == existing.id


def test_an_unknown_identifier_belongs_to_nobody(db):
    assert find_by_identifier(db, "nobody@example.com") is None


# ── What the identifier is keyed to now ───────────────────────────────────────
#
# This used to be a ten-minute quota, keyed the same way. Retired 2026-08-09: three free
# allowances coexisted in this codebase and none was wired to the live path, which was the
# moment to settle it rather than reconcile them later. The welcome credit stays; this
# quota and the inherited host trial go. What the identifier keys now is the credit below.


def test_registering_grants_the_welcome_credit(db):
    person = register(db, email="marie@example.com")

    assert balance(db, person.id).gifted_cents == WELCOME_CREDIT_CENTS


def test_signing_up_again_does_not_grant_it_twice(db):
    """The obvious attempt. The identifier is what was burned, so the second signup finds
    the first person and nothing is granted a second time."""
    first = register(db, email="marie@example.com")
    register(db, email="marie@example.com")

    assert balance(db, first.id).gifted_cents == WELCOME_CREDIT_CENTS
    assert db.query(User).count() == 1


def test_a_second_identifier_on_the_same_person_grants_nothing_further(db):
    """Hosting under an address and being invited on a number are the same person. A second
    identifier added to somebody already granted is not a second chance at the gift."""
    person = register(db, email="marie@example.com")
    register(db, email="marie@example.com", phone="+15145550123")

    assert balance(db, person.id).gifted_cents == WELCOME_CREDIT_CENTS


# ── The registry itself ───────────────────────────────────────────────────────


def test_every_identifier_given_becomes_a_key(db):
    person = register(db, email="marie@example.com", phone="+15145550123")

    stored = {row.identifier for row in db.query(ParticipantIdentifier).all()}

    assert stored == {"marie@example.com", "+15145550123"}
    assert all(
        row.user_id == person.id for row in db.query(ParticipantIdentifier).all()
    )


def test_an_identifier_belongs_to_one_person_only(db):
    """The uniqueness is the guarantee rather than a convenience: two rows for one address
    would be two quotas for one person, found in whichever order the query happened to
    return them."""
    from sqlalchemy.exc import IntegrityError

    person = register(db, email="marie@example.com")
    db.add(ParticipantIdentifier(identifier="marie@example.com", user_id=uuid.uuid4()))

    with pytest.raises(IntegrityError):
        db.flush()

    db.rollback()
    assert person is not None


# ── The live path ─────────────────────────────────────────────────────────────


def test_asking_for_a_sign_in_code_registers_the_identifier(db, monkeypatch):
    """Signing up and asking for a code are one act. Creating the account without keying the
    identifier would leave somebody registered with no key to their own allowance."""
    from src.services import otp

    monkeypatch.setattr(otp, "_send_email", lambda *args, **kwargs: None)
    otp.send_otp("Marie@Example.COM", db)

    assert find_by_identifier(db, "marie@example.com") is not None
    assert db.query(User).filter(User.email == "marie@example.com").count() == 1


def test_a_code_requested_in_one_case_is_confirmed_in_another(db, monkeypatch):
    """One person confirming one code. Matching the raw string would tell them there was no
    pending code for an address they had just used."""
    from src.services import otp

    monkeypatch.setattr(otp, "_send_email", lambda *args, **kwargs: None)
    otp.send_otp("marie@example.com", db)
    code = db.query(User).filter(User.email == "marie@example.com").one().otp_code

    confirmed = otp.verify_otp("MARIE@Example.com", code, db)

    assert confirmed.email == "marie@example.com"


def test_two_spellings_do_not_become_two_accounts(db, monkeypatch):
    """The quota is keyed to the identifier, so a second spelling that made a second account
    would be a second lifetime allowance for the price of pressing shift."""
    from src.services import otp

    monkeypatch.setattr(otp, "_send_email", lambda *args, **kwargs: None)
    otp.send_otp("marie@example.com", db)
    otp.send_otp("Marie@Example.COM ", db)

    assert db.query(User).count() == 1


def test_the_registry_is_not_the_burned_credit_registry(db):
    """Two tables that look alike and answer different questions. This one says who an
    identifier belongs to and is read on every signup; `burned_identifiers` says the welcome
    credit has already been paid and deliberately survives the account being deleted."""
    from src.models.burned_identifier import BurnedIdentifier

    assert ParticipantIdentifier.__tablename__ != BurnedIdentifier.__tablename__
    assert ParticipantIdentifier.__table__.c.user_id.foreign_keys != set()
    assert BurnedIdentifier.__table__.c.granted_to.foreign_keys == set()
