"""Tests for Story 5.2 — Starting a new session with a previous partner.

A registered user can list their previous partners and quick-start a new session
with one already identified, without repeating the full invitation flow.
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from src.models.invitation import Invitation
from src.models.session import SessionModel
from src.models.user import User
from src.services.jwt_service import issue_token


# ─── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def user(db):
    u = User(email="15145550001@example.com", phone_number="+15145550001")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u, issue_token(str(u.id))


def _session(db, host, *, offset_min=0):
    now = datetime.now(tz=timezone.utc)
    s = SessionModel(
        host_user_id=host.id,
        livekit_room_name=f"room-{host.phone_number[-4:]}-{offset_min}",
        source_type="url",
        source_url="https://example.com/a",
        source_content="content",
        status="ended",
        created_at=now - timedelta(minutes=offset_min),
        ended_at=now - timedelta(minutes=offset_min) + timedelta(minutes=5),
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def _invite(db, session, host, guest_phone, *, guest_user=None, status="accepted"):
    inv = Invitation(
        session_id=session.id,
        host_user_id=host.id,
        guest_email=guest_phone.lstrip("+") + "@example.com",
        guest_user_id=guest_user.id if guest_user else None,
        invitation_type="salon_friend" if guest_user else "email_contact",
        join_token=f"tok-{session.livekit_room_name}-{guest_phone}",
        status=status,
        expires_at=datetime.now(tz=timezone.utc) + timedelta(days=1),
    )
    db.add(inv)
    db.commit()
    db.refresh(inv)
    return inv


# ─── GET /me/partners ────────────────────────────────────────────────────────

def test_partners_requires_auth(client):
    assert client.get("/me/partners").status_code == 401


def test_partners_empty_for_new_user(client, user):
    _, token = user
    resp = client.get("/me/partners", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json() == {"partners": []}


def test_partners_lists_hosted_guest(client, db, user):
    host, token = user
    session = _session(db, host)
    _invite(db, session, host, "+15145559999")

    resp = client.get("/me/partners", headers={"Authorization": f"Bearer {token}"})
    partners = resp.json()["partners"]
    assert len(partners) == 1
    assert partners[0]["email"] == "15145559999@example.com"
    assert partners[0]["sessionCount"] == 1


def test_partners_dedupes_across_sessions_and_counts(client, db, user):
    """The same partner across two sessions appears once with sessionCount 2."""
    host, token = user
    guest = User(email="15145558888@example.com", phone_number="+15145558888")
    db.add(guest)
    db.commit()
    db.refresh(guest)

    s1 = _session(db, host, offset_min=60)
    s2 = _session(db, host, offset_min=1)
    _invite(db, s1, host, guest.phone_number, guest_user=guest)
    _invite(db, s2, host, guest.phone_number, guest_user=guest)

    partners = client.get("/me/partners", headers={"Authorization": f"Bearer {token}"}).json()["partners"]
    assert len(partners) == 1
    assert partners[0]["userId"] == str(guest.id)
    assert partners[0]["sessionCount"] == 2


def test_partners_includes_host_when_user_was_guest(client, db, user):
    me, token = user
    other_host = User(email="15145557777@example.com", phone_number="+15145557777")
    db.add(other_host)
    db.commit()
    db.refresh(other_host)

    session = _session(db, other_host)
    _invite(db, session, other_host, me.phone_number, guest_user=me, status="accepted")

    partners = client.get("/me/partners", headers={"Authorization": f"Bearer {token}"}).json()["partners"]
    assert len(partners) == 1
    assert partners[0]["email"] == "15145557777@example.com"


def test_partners_sorted_most_recent_first(client, db, user):
    host, token = user
    old = _session(db, host, offset_min=120)
    new = _session(db, host, offset_min=1)
    _invite(db, old, host, "+15140000001")
    _invite(db, new, host, "+15140000002")

    partners = client.get("/me/partners", headers={"Authorization": f"Bearer {token}"}).json()["partners"]
    emails = [p["email"] for p in partners]
    assert emails == ["15140000002@example.com", "15140000001@example.com"]


# ─── POST /sessions quick-start with partner_email ───────────────────────────

def test_quick_start_auto_invites_registered_partner(client, db, user):
    """Creating a session with partner_email auto-invites that partner (salon_friend)."""
    host, token = user
    partner = User(email="15145556666@example.com", phone_number="+15145556666")
    db.add(partner)
    db.commit()

    with (
        patch("src.services.content_service.fetch_url_content", return_value="content"),
        patch("src.services.livekit_service.new_room_name", return_value="salon-room-qs1"),
        patch("src.services.livekit_service.create_room"),
        patch("src.services.livekit_service.generate_participant_token", return_value="tok"),
    ):
        resp = client.post(
            "/sessions",
            data={"source_url": "https://example.com/x", "partner_email": "15145556666@example.com"},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert resp.status_code == 201
    body = resp.json()
    assert body["invitation"] is not None
    assert body["invitation"]["guestEmail"] == "15145556666@example.com"
    assert body["invitation"]["invitationType"] == "salon_friend"
    assert body["invitation"]["status"] == "pending"

    # An invitation row was actually created for the new session.
    import uuid as _uuid
    inv = db.query(Invitation).filter(
        Invitation.session_id == _uuid.UUID(body["sessionId"])
    ).first()
    assert inv is not None
    assert inv.guest_user_id == partner.id


def test_quick_start_email_contact_sends_link(client, db, user):
    """A previous SMS contact (unregistered) is invited via SMS with a join link."""
    host, token = user

    with (
        patch("src.services.content_service.fetch_url_content", return_value="content"),
        patch("src.services.livekit_service.new_room_name", return_value="salon-room-qs2"),
        patch("src.services.livekit_service.create_room"),
        patch("src.services.livekit_service.generate_participant_token", return_value="tok"),
        patch("src.services.invitation_service._send_invitation_email") as mock_email,
    ):
        resp = client.post(
            "/sessions",
            data={"source_url": "https://example.com/x", "partner_email": "15147778888@example.com"},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert resp.status_code == 201
    body = resp.json()
    assert body["invitation"]["invitationType"] == "email_contact"
    assert body["invitation"]["joinLink"] is not None
    mock_email.assert_called_once()


def test_create_session_without_partner_has_no_invitation(client, user):
    """Omitting partner_email keeps the original behaviour (no auto-invite)."""
    _, token = user
    with (
        patch("src.services.content_service.fetch_url_content", return_value="content"),
        patch("src.services.livekit_service.new_room_name", return_value="salon-room-qs3"),
        patch("src.services.livekit_service.create_room"),
        patch("src.services.livekit_service.generate_participant_token", return_value="tok"),
    ):
        resp = client.post(
            "/sessions",
            data={"source_url": "https://example.com/x"},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 201
    assert resp.json()["invitation"] is None


def test_quick_start_rejects_invalid_partner_email(client, user):
    """A malformed partner_email yields 400, not a 500."""
    _, token = user
    with (
        patch("src.services.content_service.fetch_url_content", return_value="content"),
        patch("src.services.livekit_service.new_room_name", return_value="salon-room-qs4"),
        patch("src.services.livekit_service.create_room"),
        patch("src.services.livekit_service.generate_participant_token", return_value="tok"),
    ):
        resp = client.post(
            "/sessions",
            data={"source_url": "https://example.com/x", "partner_email": "not-a-phone"},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 400
