"""Inviting by email, by text message, or by both — and being recorded either way."""
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from src.models.invitation import Invitation
from src.models.salon_event import SalonEvent
from src.models.session import SessionModel
from src.models.user import User
from src.services import salon_event_service, sms_service
from src.services.jwt_service import issue_token

PHONE = "+15145550123"


@pytest.fixture
def host(db):
    u = User(email="host@example.com")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u, issue_token(str(u.id))


@pytest.fixture
def session(db, host):
    user, _ = host
    s = SessionModel(
        host_user_id=user.id,
        livekit_room_name="salon-invite",
        source_type="url",
        source_content="content",
        status="active",
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def _invite(client, token, session, **body):
    return client.post(
        f"/sessions/{session.id}/invitations",
        json=body,
        headers={"Authorization": f"Bearer {token}"},
    )


# ─── One of the two is required ───────────────────────────────────────────────

def test_neither_contact_is_rejected(client, host, session):
    """A row identifying nobody is the one state the schema forbids outright."""
    _, token = host
    assert _invite(client, token, session).status_code == 422


def test_blank_strings_count_as_neither(client, host, session):
    """A form submitted with both fields empty must not look like a phone invitation."""
    _, token = host
    assert _invite(client, token, session, guestEmail="", guestPhone="  ").status_code == 422


def test_a_phone_number_alone_is_enough(client, host, session):
    _, token = host
    with patch.object(sms_service, "send_invitation_sms", return_value=True):
        response = _invite(client, token, session, guestPhone=PHONE)
    assert response.status_code == 201
    body = response.json()
    assert body["guestPhone"] == PHONE
    assert body["guestEmail"] == ""


def test_an_email_alone_is_still_enough(client, host, session):
    _, token = host
    with patch("src.services.invitation_service._send_invitation_email"):
        body = _invite(client, token, session, guestEmail="guest@example.com").json()
    assert body["guestEmail"] == "guest@example.com"
    assert body["guestPhone"] == ""


# ─── Both channels when both are given ────────────────────────────────────────

def test_both_channels_are_used_when_both_are_supplied(client, host, session):
    """The point of giving both is that it arrives, so neither is skipped."""
    _, token = host
    with patch("src.services.invitation_service._send_invitation_email") as email, \
         patch.object(sms_service, "send_invitation_sms", return_value=True) as sms:
        body = _invite(
            client, token, session, guestEmail="guest@example.com", guestPhone=PHONE
        ).json()
    email.assert_called_once()
    sms.assert_called_once()
    assert body["emailSent"] is True
    assert body["smsSent"] is True


def test_no_text_is_sent_when_no_number_was_given(client, host, session):
    _, token = host
    with patch("src.services.invitation_service._send_invitation_email"), \
         patch.object(sms_service, "send_invitation_sms") as sms:
        body = _invite(client, token, session, guestEmail="guest@example.com").json()
    sms.assert_not_called()
    assert body["smsSent"] is False


def test_one_channel_failing_does_not_take_the_other_down(client, host, session):
    """The link is returned whatever happens — a failed send costs convenience only."""
    _, token = host
    with patch("src.services.invitation_service._send_invitation_email"), \
         patch.object(sms_service, "send_invitation_sms", return_value=False):
        body = _invite(
            client, token, session, guestEmail="guest@example.com", guestPhone=PHONE
        ).json()
    assert body["emailSent"] is True
    assert body["smsSent"] is False
    assert body["joinLink"]


# ─── The number itself ────────────────────────────────────────────────────────

def test_a_number_without_a_country_code_is_rejected(client, host, session):
    """A carrier would guess, and a text about a conversation starting now is not worth
    guessing on."""
    _, token = host
    assert _invite(client, token, session, guestPhone="5145550123").status_code == 422


def test_punctuation_is_accepted_and_normalised(client, host, session):
    _, token = host
    with patch.object(sms_service, "send_invitation_sms", return_value=True):
        body = _invite(client, token, session, guestPhone="+1 (514) 555-0123").json()
    assert body["guestPhone"] == PHONE


def test_the_text_leads_with_the_link(client):
    """Advice that pushes the one actionable thing below the fold is worse than none."""
    message = sms_service.invitation_text("https://x/join/tok")
    assert message.index("https://x/join/tok") < message.index("Safari")


def test_the_text_carries_the_transcription_notice_in_both_languages(client):
    message = sms_service.invitation_text("https://x/join/tok")
    assert "transcribed and kept" in message
    assert "transcrit et conserve" in message


# ─── Being recorded by whichever half you have ────────────────────────────────

def test_a_guest_with_only_a_number_is_recorded(db, session):
    salon_event_service.record_entry(
        db,
        participant_identity="test-identity",
        phone=PHONE, user_type="guest", salon_name=session.livekit_room_name
    )
    row = db.query(SalonEvent).one()
    assert row.phone == PHONE
    assert row.email == ""


def test_a_participation_with_no_identity_is_refused(db, session):
    """Not raised — refused. Failing to note something must never keep anyone out.

    "Identity" now means the LiveKit identity, not an address. A participation with neither an
    email nor a number is perfectly valid — that is an anonymous guest — but one with nothing
    to attribute it to is not.
    """
    salon_event_service.record_entry(
        db,
        participant_identity="",
        email="someone@example.com",
        user_type="guest",
        salon_name=session.livekit_room_name,
    )
    assert db.query(SalonEvent).count() == 0


def test_two_identities_are_two_participants(db, session):
    """What separates participants is the identity the room saw, not the channel they were
    reached by. Two invitations are two identities and therefore two rows — which is what
    happened in the room, whether one was emailed and the other texted or not."""
    salon_event_service.record_entry(
        db,
        participant_identity="guest-one",
        email="a@example.com", user_type="guest", salon_name=session.livekit_room_name
    )
    salon_event_service.record_entry(
        db,
        participant_identity="guest-two",
        phone=PHONE, user_type="guest", salon_name=session.livekit_room_name
    )
    assert db.query(SalonEvent).count() == 2


def test_one_identity_rejoining_is_one_participant(db, session):
    """The other half of the same rule, and the reason the key changed: re-entering a salon
    updates the row instead of adding a second. Previously an address supplied on the second
    call and not the first would have created a new row."""
    salon_event_service.record_entry(
        db,
        participant_identity="guest-one",
        user_type="guest", salon_name=session.livekit_room_name
    )
    salon_event_service.record_entry(
        db,
        participant_identity="guest-one",
        email="learned@example.com",
        user_type="guest", salon_name=session.livekit_room_name
    )
    rows = db.query(SalonEvent).all()
    assert len(rows) == 1
    # An anonymous guest who signs up mid-salon becomes reachable, and the row says so.
    assert rows[0].email == "learned@example.com"


def test_first_salon_matches_on_the_half_we_hold(db, session):
    """An empty email must not match every other participant who also lacks one."""
    salon_event_service.record_entry(
        db,
        participant_identity="test-identity",
        phone=PHONE, user_type="guest", salon_name="salon-elsewhere"
    )
    salon_event_service.record_entry(
        db,
        participant_identity="test-identity",
        phone="+15145559999", user_type="guest", salon_name=session.livekit_room_name
    )
    invitation = Invitation(
        session_id=session.id,
        host_user_id=session.host_user_id,
        guest_email="",
        guest_phone="+15145559999",
        invitation_type="email_contact",
        join_token="tok-phone",
        status="pending",
        expires_at=datetime.now(tz=timezone.utc) + timedelta(hours=24),
    )
    db.add(invitation)
    db.commit()
    db.refresh(invitation)

    # This number has been in no other salon, even though another phone-only guest has.
    assert salon_event_service.is_first_salon(
        db,
        salon_name=session.livekit_room_name,
        participant_identity=f"guest-{invitation.id}",
    )


# ─── The code the host has to read aloud ──────────────────────────────────────
#
# Built by the service since migration 022 and absent from InvitationResponse until now, so
# FastAPI dropped it on the way out. The code was minted, reserved and mailed to the guest, and
# the one person who might have to say it out loud — the host — could not see it. That matters
# more now that /call exists: dialling in is the only door for somebody with no link.

def test_the_host_can_read_the_telephone_code(client, host, session):
    """The whole point of returning it. A guest who calls rather than clicks has no link to
    read from, and the host is the only person who can tell them the number."""
    _, token = host
    resp = client.post(
        f"/sessions/{session.id}/invitations",
        headers={"Authorization": f"Bearer {token}"},
        json={"guestEmail": "dial@example.com"},
    )
    assert resp.status_code == 201
    pin = resp.json()["phonePin"]
    assert pin and pin.isdigit() and len(pin) == 6


def test_the_code_the_host_reads_is_the_code_that_works(client, host, session, db):
    """Two codes for one invitation — one shown, one stored — would send a caller to a Salon
    that does not answer, and the host would have no way to know why."""
    from src.models.invitation import Invitation
    import uuid as _uuid

    _, token = host
    body = client.post(
        f"/sessions/{session.id}/invitations",
        headers={"Authorization": f"Bearer {token}"},
        json={"guestEmail": "dial2@example.com"},
    ).json()

    row = db.query(Invitation).filter(
        Invitation.id == _uuid.UUID(body["invitationId"])
    ).one()
    assert body["phonePin"] == row.phone_pin
