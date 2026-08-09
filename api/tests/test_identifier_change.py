"""Changing an identifier without losing the account (Story 10.6 / FR64).

An identifier is the key to a person's balance, so changing one is changing a lock somebody is
standing behind. The rule that makes it safe is the **anchor**: exactly one identifier moves at
a time, and the other stays put as the thing that still ties the account to the person it
belonged to yesterday.

Which is why changing both at once is refused. It is not a technical limitation — both could be
written in one statement. It is that after such a change nothing about the account resembles
what it was, and there is no longer any way to say the person holding it now is the person who
held it before. The same reasoning refuses a change on an account with only one identifier: the
second has to be added first, precisely so there is something to anchor to.

The burned registry does not enter into it. That table exists to stop a *gift* being given
twice, and an identifier appearing in it means somebody once had a welcome credit for it — not
that it is forbidden ground. Reading it as a blocklist would make a person unable to reuse an
address they themselves burned years ago.

And a change is not an event that touches money. The gifted balance keeps its current amount:
not reassigned, not topped up, not reset to five dollars. Somebody who has spent four of their
five dollars and changes their address has spent four of their five dollars.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from src.credit import WELCOME_CREDIT_CENTS, balance, debit, grant_welcome_credit
from src.identifier_change import (
    CODE_LIFETIME,
    ChangeRefused,
    apply_change,
    plan_change,
    verify_code,
)
from src.models.burned_identifier import BurnedIdentifier
from src.models.pending_identifier_change import PendingIdentifierChange
from src.models.user import User
from src.signup import find_by_identifier, register

NOW = datetime(2026, 8, 1, tzinfo=timezone.utc)


@pytest.fixture
def person(db):
    """Somebody holding both identifiers, which is who may change either."""
    row = register(db, email="marie@example.com", phone="+15145550123")
    db.commit()
    return row


# ── One moves, the other anchors ──────────────────────────────────────────────


def test_the_address_may_change_while_the_number_anchors(db, person):
    pending = plan_change(db, person, new_email="new@example.com", now=NOW)

    assert pending.new_identifier == "new@example.com"
    assert pending.anchor == "+15145550123"


def test_the_number_may_change_while_the_address_anchors(db, person):
    pending = plan_change(db, person, new_phone="+15145559999", now=NOW)

    assert pending.new_identifier == "+15145559999"
    assert pending.anchor == "marie@example.com"


def test_both_at_once_is_refused(db, person):
    """Not a technical limitation. Afterwards nothing about the account resembles what it
    was, and nothing can say the person holding it is the person who held it."""
    with pytest.raises(ChangeRefused) as raised:
        plan_change(db, person, new_email="a@example.com", new_phone="+15145559999", now=NOW)

    assert "anchor" in str(raised.value).lower()


def test_changing_nothing_is_refused(db, person):
    with pytest.raises(ChangeRefused):
        plan_change(db, person, now=NOW)


def test_an_account_with_one_identifier_cannot_change_it(db):
    """The second has to be added first, precisely so there is something to anchor to."""
    alone = register(db, email="alone@example.com")
    db.commit()

    with pytest.raises(ChangeRefused) as raised:
        plan_change(db, alone, new_email="other@example.com", now=NOW)

    assert "add" in str(raised.value).lower()


def test_adding_a_second_identifier_is_not_a_change(db):
    """It is a signup with an identifier already known — `register` resolves it to the same
    person. Nothing is being replaced, so nothing needs an anchor."""
    alone = register(db, email="alone@example.com")
    db.commit()

    again = register(db, email="alone@example.com", phone="+15145550199")
    db.commit()

    assert again.id == alone.id
    assert plan_change(db, again, new_email="other@example.com", now=NOW).anchor == "+15145550199"


# ── Somebody else's identifier ────────────────────────────────────────────────


def test_an_identifier_belonging_to_another_account_is_refused(db, person):
    """Explicitly, and naming the reason: two people cannot hold one key."""
    register(db, email="taken@example.com", phone="+15145550777")
    db.commit()

    with pytest.raises(ChangeRefused) as raised:
        plan_change(db, person, new_email="taken@example.com", now=NOW)

    assert "taken@example.com" in str(raised.value)


def test_your_own_other_identifier_is_not_a_change(db, person):
    """Asking to change an address to the number already on the account is asking for
    nothing, and it must not read as a collision with yourself."""
    with pytest.raises(ChangeRefused) as raised:
        plan_change(db, person, new_email="marie@example.com", now=NOW)

    assert "already" in str(raised.value).lower()


def test_a_burned_identifier_attached_to_nobody_is_accepted(db, person):
    """The registry stops a gift being given twice. Reading it as a blocklist would make
    somebody unable to reuse an address they themselves burned years ago."""
    db.add(BurnedIdentifier(identifier="burned@example.com", burned_at=NOW, granted_to=None))
    db.flush()

    pending = plan_change(db, person, new_email="burned@example.com", now=NOW)

    assert pending.new_identifier == "burned@example.com"


# ── Verified before it takes effect ───────────────────────────────────────────


def test_nothing_changes_until_the_code_is_given(db, person):
    plan_change(db, person, new_email="new@example.com", now=NOW)
    db.commit()

    assert db.get(User, person.id).email == "marie@example.com"
    assert find_by_identifier(db, "new@example.com") is None


def test_the_right_code_lets_it_through(db, person):
    pending = plan_change(db, person, new_email="new@example.com", now=NOW)

    assert verify_code(db, pending, code=pending.code, now=NOW) is True


def test_a_wrong_code_does_not(db, person):
    pending = plan_change(db, person, new_email="new@example.com", now=NOW)

    assert verify_code(db, pending, code="000000", now=NOW) is False


def test_a_code_does_not_last_forever(db, person):
    """The same reasoning as the signup code: a verification good for a week is a verification
    somebody else can use after the address changes hands."""
    pending = plan_change(db, person, new_email="new@example.com", now=NOW)

    assert verify_code(db, pending, code=pending.code, now=NOW + CODE_LIFETIME * 2) is False


def test_the_code_is_six_digits_like_the_signup_one(db, person):
    pending = plan_change(db, person, new_email="new@example.com", now=NOW)

    assert len(pending.code) == 6 and pending.code.isdigit()


def test_a_code_works_once(db, person):
    """The one-time part is the point. A code that keeps working is a code worth stealing —
    and the second use would move an identifier that has already moved."""
    pending = plan_change(db, person, new_email="new@example.com", now=NOW)
    apply_change(db, pending, code=pending.code, now=NOW)
    db.commit()

    assert verify_code(db, pending, code=pending.code, now=NOW) is False
    with pytest.raises(ChangeRefused):
        apply_change(db, pending, code=pending.code, now=NOW)


def test_applying_with_the_wrong_code_changes_nothing(db, person):
    """The gate is inside `apply_change` rather than trusted from a caller that verified
    separately: two steps with the check in the first is one refactor away from a change
    that applies without one."""
    pending = plan_change(db, person, new_email="new@example.com", now=NOW)

    with pytest.raises(ChangeRefused):
        apply_change(db, pending, code="000000", now=NOW)

    assert db.get(User, person.id).email == "marie@example.com"


def test_a_change_knows_which_identifier_it_replaces(db, person):
    """Written down when the change is planned, not resolved when it is applied. The account
    may itself have moved in between — that is what this feature is for."""
    pending = plan_change(db, person, new_email="new@example.com", now=NOW)

    assert pending.replaces == "marie@example.com"


def test_a_change_against_an_account_that_is_gone_is_refused(db, person):
    """Somebody deleted their account between asking and confirming. Nothing to move, and
    the honest answer is to say so rather than to raise on a missing row."""
    pending = plan_change(db, person, new_email="new@example.com", now=NOW)
    code = pending.code
    db.delete(db.get(User, person.id))
    db.flush()

    with pytest.raises(ChangeRefused) as raised:
        apply_change(db, pending, code=code, now=NOW)

    assert "no longer exists" in str(raised.value)


# ── What the change does ──────────────────────────────────────────────────────


def test_the_new_identifier_takes_effect(db, person):
    pending = plan_change(db, person, new_email="new@example.com", now=NOW)

    apply_change(db, pending, code=pending.code, now=NOW)
    db.commit()

    assert db.get(User, person.id).email == "new@example.com"
    assert find_by_identifier(db, "new@example.com").id == person.id


def test_the_anchor_is_untouched(db, person):
    pending = plan_change(db, person, new_email="new@example.com", now=NOW)

    apply_change(db, pending, code=pending.code, now=NOW)
    db.commit()

    assert db.get(User, person.id).phone_number == "+15145550123"
    assert find_by_identifier(db, "+15145550123").id == person.id


def test_the_old_identifier_stops_pointing_at_the_account(db, person):
    """It is not theirs any more. Leaving it as a key would let somebody who recovered the
    old address walk back into an account that has moved on."""
    pending = plan_change(db, person, new_email="new@example.com", now=NOW)

    apply_change(db, pending, code=pending.code, now=NOW)
    db.commit()

    assert find_by_identifier(db, "marie@example.com") is None


def test_the_new_identifier_is_burned(db, person):
    """So the account it now belongs to cannot be handed a second welcome credit through it."""
    pending = plan_change(db, person, new_email="new@example.com", now=NOW)

    apply_change(db, pending, code=pending.code, now=NOW)
    db.commit()

    burned = db.get(BurnedIdentifier, "new@example.com")
    assert burned is not None and burned.granted_to == person.id


# ── The money does not move ───────────────────────────────────────────────────


def test_the_gifted_balance_keeps_its_current_amount(db, person):
    """Not reassigned, not topped up, not reset to five dollars. Somebody who has spent four
    of their five dollars and changes their address has spent four of their five dollars."""
    grant_welcome_credit(
        db, subject_id=person.id, identifiers=["marie@example.com"], now=NOW
    )
    debit(db, person.id, cents=400, now=NOW)
    db.flush()
    before = balance(db, person.id)

    pending = plan_change(db, person, new_email="new@example.com", now=NOW)
    apply_change(db, pending, code=pending.code, now=NOW)
    db.commit()

    after = balance(db, person.id)
    assert after.gifted_cents == before.gifted_cents == WELCOME_CREDIT_CENTS - 400


def test_no_second_gift_is_granted_by_the_change(db, person):
    """The new identifier was never paid for, and it must not become the reason to pay."""
    grant_welcome_credit(
        db, subject_id=person.id, identifiers=["marie@example.com"], now=NOW
    )
    db.flush()

    pending = plan_change(db, person, new_email="new@example.com", now=NOW)
    apply_change(db, pending, code=pending.code, now=NOW)
    db.commit()

    assert balance(db, person.id).gifted_cents == WELCOME_CREDIT_CENTS


def test_the_paid_balance_is_untouched(db, person):
    from src.ledger import EventType, Pool, append

    append(
        db,
        type=EventType.RECHARGED,
        subject_id=person.id,
        amount_cents=2500,
        pool=Pool.PAID,
        occurred_at=NOW,
    )
    db.flush()

    pending = plan_change(db, person, new_email="new@example.com", now=NOW)
    apply_change(db, pending, code=pending.code, now=NOW)
    db.commit()

    assert balance(db, person.id).paid_cents == 2500


def test_the_change_writes_nothing_to_the_ledger(db, person):
    """A change of address is not a financial event. Writing one would put a movement of
    zero into a stream whose whole purpose is that every row moved something."""
    from src.models.ledger_event import LedgerEvent

    before = db.query(LedgerEvent).count()

    pending = plan_change(db, person, new_email="new@example.com", now=NOW)
    apply_change(db, pending, code=pending.code, now=NOW)
    db.commit()

    assert db.query(LedgerEvent).count() == before


# ── Both, one after the other ─────────────────────────────────────────────────


def test_each_identifier_may_change_in_turn(db, person):
    """The chain holds at every step: the address moves while the number anchors, then the
    number moves while the *new* address anchors."""
    first = plan_change(db, person, new_email="new@example.com", now=NOW)
    apply_change(db, first, code=first.code, now=NOW)
    db.commit()

    second = plan_change(db, person, new_phone="+15145559999", now=NOW + timedelta(days=1))
    assert second.anchor == "new@example.com"
    apply_change(db, second, code=second.code, now=NOW + timedelta(days=1))
    db.commit()

    moved = db.get(User, person.id)
    assert (moved.email, moved.phone_number) == ("new@example.com", "+15145559999")


def test_nothing_of_the_original_pair_still_opens_the_account(db, person):
    first = plan_change(db, person, new_email="new@example.com", now=NOW)
    apply_change(db, first, code=first.code, now=NOW)
    db.commit()
    second = plan_change(db, person, new_phone="+15145559999", now=NOW)
    apply_change(db, second, code=second.code, now=NOW)
    db.commit()

    assert find_by_identifier(db, "marie@example.com") is None
    assert find_by_identifier(db, "+15145550123") is None
    assert find_by_identifier(db, "new@example.com").id == person.id


def test_no_gift_is_granted_across_the_whole_chain(db, person):
    """The acceptance criterion that matters most, stated end to end: two changes, one
    account, and never a second five dollars."""
    grant_welcome_credit(
        db, subject_id=person.id, identifiers=["marie@example.com"], now=NOW
    )
    db.flush()

    for change in (
        dict(new_email="new@example.com"),
        dict(new_phone="+15145559999"),
    ):
        pending = plan_change(db, person, now=NOW, **change)
        apply_change(db, pending, code=pending.code, now=NOW)
        db.commit()

    assert balance(db, person.id).gifted_cents == WELCOME_CREDIT_CENTS
    assert db.query(BurnedIdentifier).count() == 3


def test_a_normalised_identifier_is_what_gets_stored(db, person):
    """The same normalisation as signup, or the account would hold a key that finds nobody."""
    pending = plan_change(db, person, new_email="  NEW@Example.COM ", now=NOW)
    apply_change(db, pending, code=pending.code, now=NOW)
    db.commit()

    assert db.get(User, person.id).email == "new@example.com"


def test_an_identifier_that_is_not_one_is_refused(db, person):
    with pytest.raises(ChangeRefused):
        plan_change(db, person, new_email="   ", now=NOW)


# ── The door a person actually uses ───────────────────────────────────────────


@pytest.fixture
def signed_in(db, person):
    from src.services.jwt_service import issue_token

    return {"Authorization": f"Bearer {issue_token(str(person.id))}"}


def test_a_change_can_be_asked_for_over_http(client, db, person, signed_in, monkeypatch):
    from src.services import otp

    monkeypatch.setattr(otp, "_send_email", lambda *a, **k: None)

    resp = client.post("/me/identifier", json={"newEmail": "new@example.com"}, headers=signed_in)

    assert resp.status_code == 202
    assert resp.json()["anchor"] == "+15145550123"


def test_asking_changes_nothing_yet(client, db, person, signed_in, monkeypatch):
    """202, not 200. A change that took effect on request would let anybody holding a session
    move somebody's key to an address they control."""
    from src.services import otp

    monkeypatch.setattr(otp, "_send_email", lambda *a, **k: None)
    client.post("/me/identifier", json={"newEmail": "new@example.com"}, headers=signed_in)

    assert db.get(User, person.id).email == "marie@example.com"


def test_the_code_is_never_in_the_response(client, db, person, signed_in, monkeypatch):
    """It travels to the identifier being proved. Returning it here would prove nothing."""
    from src.services import otp

    monkeypatch.setattr(otp, "_send_email", lambda *a, **k: None)
    body = client.post(
        "/me/identifier", json={"newEmail": "new@example.com"}, headers=signed_in
    ).json()

    row = db.query(PendingIdentifierChange).one()
    assert row.code not in str(body)


def test_a_refused_change_says_why(client, db, person, signed_in):
    resp = client.post(
        "/me/identifier",
        json={"newEmail": "a@example.com", "newPhone": "+15145559999"},
        headers=signed_in,
    )

    assert resp.status_code == 400
    assert "anchor" in resp.json()["detail"].lower()


def test_the_code_completes_the_change(client, db, person, signed_in, monkeypatch):
    from src.services import otp

    monkeypatch.setattr(otp, "_send_email", lambda *a, **k: None)
    client.post("/me/identifier", json={"newEmail": "new@example.com"}, headers=signed_in)
    code = db.query(PendingIdentifierChange).one().code

    resp = client.post("/me/identifier/confirm", json={"code": code}, headers=signed_in)

    assert resp.status_code == 200
    # The request ran in its own session; this one still holds the pre-change instance.
    db.expire_all()
    assert db.get(User, person.id).email == "new@example.com"


def test_a_wrong_code_over_http_changes_nothing(client, db, person, signed_in, monkeypatch):
    from src.services import otp

    monkeypatch.setattr(otp, "_send_email", lambda *a, **k: None)
    client.post("/me/identifier", json={"newEmail": "new@example.com"}, headers=signed_in)

    resp = client.post("/me/identifier/confirm", json={"code": "000000"}, headers=signed_in)

    assert resp.status_code == 400
    assert db.get(User, person.id).email == "marie@example.com"


def test_confirming_nothing_is_a_not_found(client, db, person, signed_in):
    resp = client.post("/me/identifier/confirm", json={"code": "123456"}, headers=signed_in)

    assert resp.status_code == 404


def test_asking_twice_confirms_the_second(client, db, person, signed_in, monkeypatch):
    """Somebody who asked twice meant the second one. The first is abandoned rather than
    ambiguous."""
    from src.services import otp

    monkeypatch.setattr(otp, "_send_email", lambda *a, **k: None)
    client.post("/me/identifier", json={"newEmail": "first@example.com"}, headers=signed_in)
    client.post("/me/identifier", json={"newPhone": "+15145558888"}, headers=signed_in)
    rows = db.query(PendingIdentifierChange).order_by(
        PendingIdentifierChange.requested_at.desc()
    ).all()

    client.post("/me/identifier/confirm", json={"code": rows[0].code}, headers=signed_in)

    db.expire_all()
    moved = db.get(User, person.id)
    assert (moved.email, moved.phone_number) == ("marie@example.com", "+15145558888")


def test_a_stranger_cannot_move_anybodys_identifier(client, db, person):
    assert client.post("/me/identifier", json={"newEmail": "x@example.com"}).status_code in (401, 403)
