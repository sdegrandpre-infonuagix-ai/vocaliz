"""Tests for GET /invitations/guest-join/{join_token} (Story 3.1)."""
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from src.models.invitation import Invitation
from src.models.session import SessionModel
from src.models.user import User
from src.services.jwt_service import issue_token


# ─── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def host(db):
    u = User(email="15145550001@example.com", phone_number="+15145550001")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u, issue_token(str(u.id))


@pytest.fixture
def active_session(db, host):
    host_user, _ = host
    sess = SessionModel(
        host_user_id=host_user.id,
        livekit_room_name="salon-guest-room",
        source_type="url",
        source_url="https://example.com",
        source_content="content",
        status="active",
    )
    db.add(sess)
    db.commit()
    db.refresh(sess)
    return sess


def _make_invitation(db, host_user, session, *, status="pending", expired=False, token=None):
    expires = (
        datetime.now(tz=timezone.utc) - timedelta(hours=1)
        if expired
        else datetime.now(tz=timezone.utc) + timedelta(hours=24)
    )
    inv = Invitation(
        session_id=session.id,
        host_user_id=host_user.id,
        guest_email="15145559999@example.com",
        guest_user_id=None,
        invitation_type="email_contact",
        join_token=token or secrets.token_urlsafe(32),
        status=status,
        expires_at=expires,
    )
    db.add(inv)
    db.commit()
    db.refresh(inv)
    return inv


# ─── Success case ─────────────────────────────────────────────────────────────

def test_guest_join_returns_livekit_credentials(client, db, host, active_session):
    """Valid pending token returns LiveKit credentials."""
    host_user, _ = host
    inv = _make_invitation(db, host_user, active_session)
    resp = client.get(f"/invitations/guest-join/{inv.join_token}")
    assert resp.status_code == 200
    body = resp.json()
    assert "participantToken" in body
    assert body["participantToken"]
    assert body["livekitRoomName"] == active_session.livekit_room_name
    assert "livekitUrl" in body
    assert body["sessionId"] == str(active_session.id)


def test_guest_join_requires_no_authentication(client, db, host, active_session):
    """Endpoint must be accessible without any Authorization header."""
    host_user, _ = host
    inv = _make_invitation(db, host_user, active_session)
    resp = client.get(f"/invitations/guest-join/{inv.join_token}")
    assert resp.status_code == 200


# ─── One-time use ─────────────────────────────────────────────────────────────

def test_guest_join_marks_token_as_accepted(client, db, host, active_session):
    """After a successful join, the invitation status becomes 'accepted'."""
    host_user, _ = host
    inv = _make_invitation(db, host_user, active_session)
    client.get(f"/invitations/guest-join/{inv.join_token}")
    db.expire(inv)
    db.refresh(inv)
    assert inv.status == "accepted"


def test_guest_join_second_use_returns_410(client, db, host, active_session):
    """Attempting to reuse an already-used token returns 410 Gone."""
    host_user, _ = host
    inv = _make_invitation(db, host_user, active_session, status="accepted")
    resp = client.get(f"/invitations/guest-join/{inv.join_token}")
    assert resp.status_code == 410
    assert "déjà été utilisé" in resp.json()["detail"]


def test_guest_join_concurrent_use_blocked(client, db, host, active_session):
    """A token that has been used once cannot be redeemed by a second caller."""
    host_user, _ = host
    token = secrets.token_urlsafe(32)
    inv = _make_invitation(db, host_user, active_session, token=token)
    # First call succeeds
    r1 = client.get(f"/invitations/guest-join/{token}")
    assert r1.status_code == 200
    # Second call blocked
    r2 = client.get(f"/invitations/guest-join/{token}")
    assert r2.status_code == 410


# ─── Error cases ──────────────────────────────────────────────────────────────

def test_guest_join_unknown_token_returns_404(client):
    """Unknown token returns 404 Not Found."""
    resp = client.get(f"/invitations/guest-join/{secrets.token_urlsafe(32)}")
    assert resp.status_code == 404


def test_guest_join_expired_token_returns_410(client, db, host, active_session):
    """Expired token returns 410 Gone."""
    host_user, _ = host
    inv = _make_invitation(db, host_user, active_session, expired=True)
    resp = client.get(f"/invitations/guest-join/{inv.join_token}")
    assert resp.status_code == 410
    assert "expiré" in resp.json()["detail"]


def test_guest_join_ended_session_returns_410(client, db, host):
    """Token for an ended session returns 410."""
    host_user, _ = host
    sess = SessionModel(
        host_user_id=host_user.id,
        livekit_room_name="salon-ended-guest",
        source_type="url",
        source_content="content",
        status="ended",
        ended_at=datetime.now(tz=timezone.utc),
    )
    db.add(sess)
    db.commit()
    db.refresh(sess)
    inv = _make_invitation(db, host_user, sess)
    resp = client.get(f"/invitations/guest-join/{inv.join_token}")
    assert resp.status_code == 410
    assert "n'est plus disponible" in resp.json()["detail"]


# ─── Web page ─────────────────────────────────────────────────────────────────

def test_guest_web_page_returns_html(client):
    """GET /join/{token} serves the HTML page (no auth, any token value)."""
    resp = client.get(f"/join/{secrets.token_urlsafe(32)}")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]


def test_guest_web_page_contains_badge(client):
    """Served HTML contains the 'Sans Installation' badge."""
    resp = client.get(f"/join/{secrets.token_urlsafe(32)}")
    assert "Sans Installation" in resp.text


def test_guest_web_page_is_responsive(client):
    """HTML contains a responsive viewport meta tag."""
    resp = client.get(f"/join/{secrets.token_urlsafe(32)}")
    assert "viewport" in resp.text
    assert "width=device-width" in resp.text


# ─── Story 3.2: clean disconnect on browser close ─────────────────────────────

def test_guest_web_page_handles_beforeunload(client):
    """HTML registers a beforeunload listener to disconnect cleanly on tab close."""
    resp = client.get(f"/join/{secrets.token_urlsafe(32)}")
    assert "beforeunload" in resp.text


def test_guest_web_page_handles_pagehide(client):
    """HTML registers a pagehide listener (reliable mobile fallback for tab close)."""
    resp = client.get(f"/join/{secrets.token_urlsafe(32)}")
    assert "pagehide" in resp.text


def test_guest_web_page_disconnect_nulls_room(client):
    """Unload handler sets room to null after disconnect to prevent double-disconnect."""
    resp = client.get(f"/join/{secrets.token_urlsafe(32)}")
    # The onPageUnload function should null out the room reference
    assert "room = null" in resp.text


# ─── Host console page ───────────────────────────────────────────────────────

def test_host_console_is_served(client):
    """The host console is the only surface that can add a source mid-session today."""
    resp = client.get("/host")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "Console hôte" in resp.text
