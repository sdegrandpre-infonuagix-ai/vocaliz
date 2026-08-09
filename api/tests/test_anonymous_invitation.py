"""There is no such thing as a join link addressed to nobody (Story 10.1, replacing FR27).

This file used to guard the opposite. A host with no way to reach their guest could mint a link
carrying no address and pass it on by hand, and the tests here checked that such a link behaved
exactly like an addressed one rather than quietly bypassing the checks that make a link
one-time.

What changed is not the link's mechanics — those were fine — but what a link with no identifier
on it left unanswerable. Nothing held the ten free minutes against a person: somebody who had
used theirs got them back by arriving again as a stranger, and no accounting downstream could
notice. So every way into a Salon now carries an address or a number, and the endpoint that
issued the exception answers 410.

Kept from the old file, because they were never about anonymity: a spent token is spent, an
invitation carries its own identity when it belongs to nobody's account, and the display name
never leaks the address. Those are properties of every invitation, and they are what the caller
invitation inherits by being an ordinary one.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from src.models.invitation import Invitation
from src.models.salon import Salon
from src.models.user import User
from src.services.jwt_service import issue_token


@pytest.fixture
def host(db):
    u = User(email="host@example.com")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u, issue_token(str(u.id))


@pytest.fixture
def salon(db, host):
    host_user, _ = host
    s = Salon(
        host_user_id=host_user.id,
        livekit_room_name="salon-anon",
        source_type="url",
        source_url="https://example.com",
        source_content="c",
        status="active",
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


# ─── The endpoint that is gone ───────────────────────────────────────────────

def test_a_link_with_no_address_can_no_longer_be_made(client, salon, host):
    """410 rather than 404. A client still calling this is running an old build, and "this
    is gone, here is what replaced it" is something somebody can act on where a not-found
    reads as a mistake in the URL."""
    _, token = host

    resp = client.post(f"/salons/{salon.id}/invitations/anonymous", headers=_auth(token))

    assert resp.status_code == 410
    assert "/salons/{salon_id}/invitations" in resp.json()["detail"]


def test_the_refusal_does_not_depend_on_the_salon_existing(client, host):
    """It is gone for everybody, not merely refused for this Salon. A 404 here would send
    somebody looking for a Salon that is not the problem."""
    _, token = host

    resp = client.post(f"/salons/{uuid.uuid4()}/invitations/anonymous", headers=_auth(token))

    assert resp.status_code == 410


def test_a_stranger_still_gets_nothing(client, salon):
    """Authentication is checked before the refusal is explained: an unauthenticated caller
    learns nothing about which endpoints exist."""
    resp = client.post(f"/salons/{salon.id}/invitations/anonymous")

    assert resp.status_code in (401, 403)


def test_nothing_is_created_by_the_attempt(client, salon, host, db):
    _, token = host
    client.post(f"/salons/{salon.id}/invitations/anonymous", headers=_auth(token))

    assert db.query(Invitation).count() == 0


# ─── The addressed endpoint keeps its refusal ────────────────────────────────

def test_an_empty_addressed_invitation_is_still_refused(client, salon, host):
    """Somebody who meant to type an address and left the field blank is told, rather than
    handed a link to a stranger. That refusal was worth keeping when there was an anonymous
    endpoint beside it, and it is the only behaviour now."""
    _, token = host
    resp = client.post(f"/salons/{salon.id}/invitations", json={}, headers=_auth(token))
    assert resp.status_code == 422


# ─── The database rule itself ────────────────────────────────────────────────
#
# These exist because the constraint was invisible to the tests. It lived only in migration
# 016 and not on the model, so the test database never had it and an anonymous invitation —
# which carried no address by design — met the rule demanding one for the first time in
# production, as a 500 the moment a host clicked the button.

def test_an_invitation_still_needs_a_way_to_reach_someone(db, salon, host):
    """The rule the original constraint existed for, and it outlives the exception that was
    carved out of it: a host who typed nothing gets a refusal, not a link addressed to
    nobody.

    Against a real Salon and a real host, so the failure can only be the CHECK. Bare UUIDs
    would raise too — on the foreign keys, which the test database enforces — and the test
    would pass while proving nothing about the rule it names."""
    import sqlalchemy

    host_user, _ = host
    row = Invitation(
        salon_id=salon.id,
        host_user_id=host_user.id,
        guest_email="",
        guest_phone="",
        invitation_type="email_contact",
        join_token="t-addressed-empty",
        status="pending",
        expires_at=datetime.now(),
    )
    db.add(row)
    with pytest.raises(sqlalchemy.exc.IntegrityError):
        db.commit()
    db.rollback()


def test_a_caller_invitation_must_carry_an_identifier_too(db, salon, host):
    """The kind of invitation that replaced the anonymous link. It is an ordinary one as far
    as the schema is concerned, which is the point: there is no longer a type exempt from the
    rule."""
    import sqlalchemy

    host_user, _ = host
    row = Invitation(
        salon_id=salon.id,
        host_user_id=host_user.id,
        guest_email="",
        guest_phone="",
        invitation_type="telephone_caller",
        join_token="t-caller-empty",
        status="pending",
        expires_at=datetime.now(),
    )
    db.add(row)
    with pytest.raises(sqlalchemy.exc.IntegrityError):
        db.commit()
    db.rollback()


def test_the_anonymous_shape_survives_in_the_schema_only(db, salon, host):
    """Rows written before Story 10.1 are still readable. The constraint keeps its old branch
    so a migration does not have to rewrite history it cannot reconstruct — what changed is
    that nothing issues one any more, which is a rule about the code and not about the past."""
    host_user, _ = host
    row = Invitation(
        salon_id=salon.id,
        host_user_id=host_user.id,
        guest_email="",
        guest_phone="",
        invitation_type="anonymous_link",
        join_token="t-historic",
        status="expired",
        expires_at=datetime.now(),
    )
    db.add(row)
    db.commit()

    assert db.query(Invitation).filter(Invitation.join_token == "t-historic").count() == 1


# ─── One person, one identity ────────────────────────────────────────────────
#
# A registered person had two identities: their account UUID when they joined through the app,
# and "guest-<invitation>" when they clicked the emailed link. The participant report showed
# that as two rows for one human, and three more if they were invited three times.

def _invitation(db, salon, host_user, **kw):
    row = Invitation(
        salon_id=salon.id,
        host_user_id=host_user.id,
        guest_email=kw.pop("email", "friend@example.com"),
        guest_phone=kw.pop("phone", ""),
        guest_user_id=kw.pop("guest_user_id", None),
        invitation_type=kw.pop("kind", "email_contact"),
        join_token=kw.pop("token", "t-identity"),
        status="pending",
        expires_at=datetime.now(tz=timezone.utc) + timedelta(hours=24),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def test_an_invitation_linked_to_an_account_joins_as_that_account(db, salon, host):
    """The fix. One registered person is one identity, whichever door they came through."""
    from src.services import livekit_service

    host_user, _ = host
    guest = User(email="member@example.com")
    db.add(guest)
    db.commit()
    db.refresh(guest)

    invitation = _invitation(db, salon, host_user, guest_user_id=guest.id, kind="salon_friend")
    assert livekit_service.identity_for(invitation) == str(guest.id)


def test_an_invitation_with_no_account_keeps_its_own_identity(db, salon, host):
    """Somebody with an address and no account has nothing else to be identified by."""
    from src.services import livekit_service

    host_user, _ = host
    invitation = _invitation(db, salon, host_user, guest_user_id=None)
    assert livekit_service.identity_for(invitation) == f"guest-{invitation.id}"


def test_the_display_name_is_untouched(db, salon, host):
    """Anonymity between participants rides on the label, not the identity. A registered guest
    is still shown as "Guest 3F2A" while being one countable person behind the scenes.

    Worth restating now that every invitation carries an identifier: what was removed is
    anonymous *access*, never anonymity in the room."""
    from src.services import livekit_service

    host_user, _ = host
    guest = User(email="shown@example.com")
    db.add(guest)
    db.commit()
    db.refresh(guest)
    invitation = _invitation(db, salon, host_user, guest_user_id=guest.id)

    assert livekit_service.identity_for(invitation) == str(guest.id)
    label = livekit_service.guest_display_name(invitation.id)
    assert label.startswith("Guest ")
    assert "shown@example.com" not in label


# ─── The link is still spent once ────────────────────────────────────────────

def test_the_link_works_before_it_is_spent(client, db, salon, host):
    host_user, _ = host
    invitation = _invitation(db, salon, host_user, token="t-live")

    resp = client.get(f"/invitations/guest-join/{invitation.join_token}")

    assert resp.status_code == 200


def test_the_link_dies_once_the_guest_is_really_in(client, db, salon, host):
    """Spent at the moment the microphone works, not when the page loads — a guest whose
    browser refuses the microphone can reopen the link elsewhere."""
    host_user, _ = host
    invitation = _invitation(db, salon, host_user, token="t-spend")

    client.post(f"/invitations/guest-join/{invitation.join_token}/confirm")

    assert client.get(f"/invitations/guest-join/{invitation.join_token}").status_code == 410


def test_confirming_twice_does_not_throw_the_guest_out(client, db, salon, host):
    """Idempotent and never fatal: a retry or a lost response must not remove somebody who is
    already in the room."""
    host_user, _ = host
    invitation = _invitation(db, salon, host_user, token="t-twice")

    client.post(f"/invitations/guest-join/{invitation.join_token}/confirm")
    again = client.post(f"/invitations/guest-join/{invitation.join_token}/confirm")

    assert again.status_code == 200


# ─── Arriving is what registers somebody ─────────────────────────────────────

def test_a_guest_who_arrives_is_registered(client, db, salon, host):
    """Their identifier keys their allowance from the moment they are genuinely present."""
    from src.signup import find_by_identifier

    host_user, _ = host
    invitation = _invitation(db, salon, host_user, email="arrived@example.com", token="t-reg")

    client.post(f"/invitations/guest-join/{invitation.join_token}/confirm")

    assert find_by_identifier(db, "arrived@example.com") is not None


def test_an_invitation_nobody_accepted_registers_nobody(client, db, salon, host):
    """An invitation that was never accepted is somebody who never arrived. Minting them an
    account would count a person who has not been in a Salon."""
    from src.signup import find_by_identifier

    host_user, _ = host
    _invitation(db, salon, host_user, email="never@example.com", token="t-unused")

    assert find_by_identifier(db, "never@example.com") is None


def test_a_returning_guest_is_the_same_person(client, db, salon, host):
    """Two invitations to two Salons, one address, one allowance. This is the quota surviving
    a new Salon, which is the whole acceptance criterion."""
    from src.signup import find_by_identifier

    host_user, _ = host
    first = _invitation(db, salon, host_user, email="regular@example.com", token="t-one")
    second = _invitation(db, salon, host_user, email="Regular@Example.COM", token="t-two")

    client.post(f"/invitations/guest-join/{first.join_token}/confirm")
    client.post(f"/invitations/guest-join/{second.join_token}/confirm")

    assert db.query(User).filter(User.email == "regular@example.com").count() == 1
    assert find_by_identifier(db, "regular@example.com") is not None
