"""A join link addressed to nobody, for a host with no way to reach their guest.

Every other invitation is built around a channel — an address to mail, a number to text. This
one has neither and is not sent anywhere: the host copies it and passes it on by hand.

Single-use is not new here and that is the point of several of these tests. Every join token
is spent once, at the moment the guest's microphone works, and a spent one answers 410. What
this file guards is that an invitation with no address behaves exactly like one with an
address, rather than quietly bypassing the checks that make a link one-time.
"""
import uuid

import pytest

from src.models.invitation import Invitation
from src.models.session import SessionModel
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
def session(db, host):
    host_user, _ = host
    s = SessionModel(
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


def _create(client, session, token):
    return client.post(
        f"/sessions/{session.id}/invitations/anonymous", headers=_auth(token)
    )


# ─── Creating one ────────────────────────────────────────────────────────────

def test_a_host_can_make_a_link_with_no_address(client, session, host):
    _, token = host
    resp = _create(client, session, token)
    assert resp.status_code == 201
    body = resp.json()
    assert body["joinLink"]
    assert body["guestEmail"] == ""
    assert body["guestPhone"] == ""
    assert body["invitationType"] == "anonymous_link"


def test_nothing_is_sent(client, session, host):
    """There is no address and no number, so reporting a delivery would be a lie. The host
    sharing the link by hand is the delivery."""
    _, token = host
    body = _create(client, session, token).json()
    assert body["emailSent"] is False
    assert body["smsSent"] is False


def test_no_telephone_code_is_reserved(client, session, host, db):
    """Codes are a finite pool of six digits and a PIN reaches a guest only by text message.
    Holding one for a link with no number to send it to spends a scarce code on a channel
    that cannot be used."""
    _, token = host
    body = _create(client, session, token).json()
    # The id arrives as a string; the column is a UUID.
    row = db.query(Invitation).filter(
        Invitation.id == uuid.UUID(body["invitationId"])
    ).one()
    assert row.phone_pin is None
    # Asserted on the row rather than the response: InvitationResponse does not declare
    # phonePin, so FastAPI strips it from every invitation — see the note in _build_response,
    # which claims the opposite. Unrelated to this feature and left alone.
    assert "phonePin" not in body


def test_the_guest_still_gets_a_name_to_wear(client, session, host):
    """Derived from the invitation, so an anonymous guest is still distinguishable from
    another anonymous guest in the same room."""
    _, token = host
    body = _create(client, session, token).json()
    assert body["participantName"].startswith("Guest ")
    assert body["participantIdentity"]


def test_two_links_are_two_different_guests(client, session, host):
    _, token = host
    first = _create(client, session, token).json()
    second = _create(client, session, token).json()
    assert first["joinLink"] != second["joinLink"]
    assert first["participantIdentity"] != second["participantIdentity"]


# ─── Used once, like any other ───────────────────────────────────────────────

def test_the_link_works_before_it_is_spent(client, session, host):
    _, token = host
    link = _create(client, session, token).json()["joinLink"]
    join_token = link.rsplit("/", 1)[-1]
    assert client.get(f"/invitations/guest-join/{join_token}").status_code == 200


def test_the_link_dies_once_the_guest_is_really_in(client, session, host):
    """Spent at the confirm, not at the credential fetch — a guest whose browser refuses the
    microphone must be able to reopen the link elsewhere."""
    _, token = host
    link = _create(client, session, token).json()["joinLink"]
    join_token = link.rsplit("/", 1)[-1]

    assert client.get(f"/invitations/guest-join/{join_token}").status_code == 200
    assert client.post(f"/invitations/guest-join/{join_token}/confirm").status_code == 200

    second = client.get(f"/invitations/guest-join/{join_token}")
    assert second.status_code == 410, "an anonymous link must be one-time like any other"


def test_confirming_twice_does_not_throw_the_guest_out(client, session, host):
    """A retry or a lost response must not eject somebody already in the room."""
    _, token = host
    join_token = _create(client, session, token).json()["joinLink"].rsplit("/", 1)[-1]
    client.post(f"/invitations/guest-join/{join_token}/confirm")
    assert client.post(f"/invitations/guest-join/{join_token}/confirm").status_code == 200


def test_an_anonymous_guest_records_no_participation(client, session, host, db):
    """There is nobody to attribute it to. salon_events is keyed on an address or a number,
    and inventing a placeholder would put a person who does not exist in the host's list —
    worse than an absence, because it would be counted."""
    from src.models.salon_event import SalonEvent

    _, token = host
    join_token = _create(client, session, token).json()["joinLink"].rsplit("/", 1)[-1]
    client.post(f"/invitations/guest-join/{join_token}/confirm")
    assert db.query(SalonEvent).count() == 0


# ─── Who may make one ────────────────────────────────────────────────────────

def test_a_stranger_cannot_make_a_link(client, session):
    assert client.post(f"/sessions/{session.id}/invitations/anonymous").status_code in (401, 403)


def test_another_host_cannot_make_a_link_for_this_salon(client, session, db):
    other = User(email="other@example.com")
    db.add(other)
    db.commit()
    db.refresh(other)
    resp = _create(client, session, issue_token(str(other.id)))
    assert resp.status_code == 404


def test_a_closed_salon_takes_no_new_guests(client, session, host, db):
    _, token = host
    session.status = "ended"
    db.commit()
    assert _create(client, session, token).status_code == 409


def test_an_unknown_salon_is_not_found(client, host):
    _, token = host
    resp = client.post(
        f"/sessions/{uuid.uuid4()}/invitations/anonymous", headers=_auth(token)
    )
    assert resp.status_code == 404


# ─── The addressed endpoint keeps its refusal ────────────────────────────────

def test_an_empty_addressed_invitation_is_still_refused(client, session, host):
    """The anonymous link is a separate endpoint on purpose. Somebody who meant to type an
    address and left the field blank should be told, not handed a link to a stranger."""
    _, token = host
    resp = client.post(f"/sessions/{session.id}/invitations", json={}, headers=_auth(token))
    assert resp.status_code == 422


# ─── The database rule itself ────────────────────────────────────────────────
#
# These exist because the constraint was invisible to the tests. It lived only in migration
# 016 and not on the model, so the test database never had it and an anonymous invitation —
# which carries no address by design — met the rule demanding one for the first time in
# production, as a 500 the moment a host clicked the button.

def test_an_addressed_invitation_still_needs_a_way_to_reach_someone(db):
    """The rule the original constraint existed for, and it must survive the change: a host who
    typed nothing gets a refusal, not a link addressed to nobody."""
    import sqlalchemy

    row = Invitation(
        session_id=uuid.uuid4(),
        host_user_id=uuid.uuid4(),
        guest_email="",
        guest_phone="",
        invitation_type="email_contact",
        join_token="t-addressed-empty",
        status="pending",
        expires_at=__import__("datetime").datetime.now(),
    )
    db.add(row)
    with pytest.raises(sqlalchemy.exc.IntegrityError):
        db.commit()
    db.rollback()


def test_an_anonymous_invitation_may_not_carry_an_address(db):
    """Narrower rather than weaker. An anonymous link with an address in it would be addressed
    while claiming not to be, and nothing downstream would know which it was."""
    import sqlalchemy

    row = Invitation(
        session_id=uuid.uuid4(),
        host_user_id=uuid.uuid4(),
        guest_email="someone@example.com",
        guest_phone="",
        invitation_type="anonymous_link",
        join_token="t-anon-addressed",
        status="pending",
        expires_at=__import__("datetime").datetime.now(),
    )
    db.add(row)
    with pytest.raises(sqlalchemy.exc.IntegrityError):
        db.commit()
    db.rollback()
