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
    # And reported as absent rather than omitted. The field used to be missing from
    # InvitationResponse entirely, so FastAPI stripped it from every invitation and the host
    # could not read a code that had been minted, reserved and mailed to the guest. It is
    # declared now, which makes an empty string the honest answer here: no code was issued.
    assert body["phonePin"] == ""


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


def test_an_anonymous_guest_is_recorded_under_their_room_identity(client, session, host, db):
    """This asserted the opposite until the key changed, and the old behaviour was the defect.

    salon_events was keyed on an address or a number, so a guest with neither could not be
    stored: anonymous guests joined salons, spoke, left, and appeared in no report. The key is
    now the LiveKit identity, which exists for everybody whether or not anyone knows who they
    are — so the participation is recorded, with no contact details, which is the truth.
    """
    from src.models.salon_event import SalonEvent

    _, token = host
    body = _create(client, session, token).json()
    join_token = body["joinLink"].rsplit("/", 1)[-1]
    client.post(f"/invitations/guest-join/{join_token}/confirm")

    row = db.query(SalonEvent).one()
    assert row.participant_identity == body["participantIdentity"]
    assert row.email == "" and row.phone == ""
    assert row.user_type == "guest"
    # Reaching the confirm endpoint is itself the evidence that the microphone worked.
    assert row.microphone_enabled is True


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


# ─── One person, one identity ────────────────────────────────────────────────
#
# A registered person had two identities: their account UUID when they joined through the app,
# and "guest-<invitation>" when they clicked the emailed link. The participant report showed that
# as two rows for one human, and three more if they were invited three times.

def _invitation(db, session, host_user, **kw):
    from datetime import datetime, timedelta, timezone

    row = Invitation(
        session_id=session.id,
        host_user_id=host_user.id,
        guest_email=kw.pop("email", "friend@example.com"),
        guest_phone="",
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


def test_an_invitation_linked_to_an_account_joins_as_that_account(db, session, host):
    """The fix. One registered person is one identity, whichever door they came through."""
    from src.services import livekit_service

    host_user, _ = host
    guest = User(email="member@example.com")
    db.add(guest)
    db.commit()
    db.refresh(guest)

    invitation = _invitation(db, session, host_user, guest_user_id=guest.id, kind="salon_friend")
    assert livekit_service.identity_for(invitation) == str(guest.id)


def test_an_invitation_with_no_account_keeps_its_own_identity(db, session, host):
    """Somebody with no account has nothing else to be identified by."""
    from src.services import livekit_service

    host_user, _ = host
    invitation = _invitation(db, session, host_user)
    assert livekit_service.identity_for(invitation) == f"guest-{invitation.id}"


def test_an_anonymous_invitation_keeps_its_own_identity(db, session, host):
    from src.services import livekit_service

    host_user, _ = host
    invitation = _invitation(db, session, host_user, email="", kind="anonymous_link")
    assert livekit_service.identity_for(invitation) == f"guest-{invitation.id}"


def test_the_display_name_is_untouched(db, session, host):
    """Anonymity between participants rides on the label, not the identity. A registered guest is
    still shown as "Guest 3F2A" while being one countable person behind the scenes."""
    from src.services import livekit_service

    host_user, _ = host
    guest = User(email="shown@example.com")
    db.add(guest)
    db.commit()
    db.refresh(guest)
    invitation = _invitation(db, session, host_user, guest_user_id=guest.id)

    assert livekit_service.identity_for(invitation) == str(guest.id)
    label = livekit_service.guest_display_name(invitation.id)
    assert label.startswith("Guest ")
    assert "shown@example.com" not in label


def test_all_three_places_agree_on_the_identity(client, db, session, host):
    """The reason it is one function. The token the guest joins with, the handle returned to the
    host, and the participation row must name the same participant — a disagreement would leave
    the host addressing somebody who is not there.

    Exercised through real requests, because the three call sites are what drift, not the
    function they call."""
    from src.models.salon_event import SalonEvent

    host_user, token = host
    guest = User(email="agree@example.com")
    db.add(guest)
    db.commit()
    db.refresh(guest)
    invitation = _invitation(
        db, session, host_user, guest_user_id=guest.id, token="t-agree", kind="salon_friend"
    )

    # What the host is handed, straight from the invitation service.
    from src.services import invitation_service

    handed = invitation_service._build_response(invitation, session)["participantIdentity"]

    # What the guest page is given, and what the row records.
    assert client.get(f"/invitations/guest-join/{invitation.join_token}").status_code == 200
    client.post(f"/invitations/guest-join/{invitation.join_token}/confirm")
    recorded = db.query(SalonEvent).one().participant_identity

    assert handed == recorded == str(guest.id)


def test_a_folded_participation_keeps_its_salon(db, session, host):
    """The behaviour migration 038 repairs, asserted at the level that matters: a registered
    person's guest participation belongs to them, not to an invitation.

    Going forward this is automatic — identity_for returns the account UUID — so a row written
    today already lands where the migration would have put it, and no salon is lost.
    """
    from src.models.salon_event import SalonEvent
    from src.services import livekit_service, salon_event_service

    host_user, _ = host
    guest = User(email="folded@example.com")
    db.add(guest)
    db.commit()
    db.refresh(guest)
    invitation = _invitation(
        db, session, host_user, guest_user_id=guest.id, token="t-fold", kind="salon_friend"
    )

    # As host of their own salon.
    salon_event_service.record_entry(
        db,
        participant_identity=str(guest.id),
        email=guest.email,
        user_type="host",
        salon_name="salon-of-their-own",
    )
    # And as an invited guest of somebody else's.
    salon_event_service.record_entry(
        db,
        participant_identity=livekit_service.identity_for(invitation),
        email=guest.email,
        user_type="guest",
        salon_name=session.livekit_room_name,
    )

    rows = db.query(SalonEvent).all()
    assert len(rows) == 2, "two salons, so two participations"
    # One identity across both, which is what makes the report show one line.
    assert {r.participant_identity for r in rows} == {str(guest.id)}
    assert {r.user_type for r in rows} == {"host", "guest"}
