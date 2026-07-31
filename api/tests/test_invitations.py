"""Tests for the invitation endpoints (Story 2.2)."""
import uuid
from unittest.mock import patch

import pytest

from src.models.session import SessionModel
from src.models.user import User
from src.services.jwt_service import issue_token


# ─── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def host(db):
    u = User(email="15141111111@example.com", phone_number="+15141111111")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u, issue_token(str(u.id))


@pytest.fixture
def guest_user(db):
    """A registered Salon user who can receive in-app invitations."""
    u = User(email="15142222222@example.com", phone_number="+15142222222")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


@pytest.fixture
def active_session(db, host):
    host_user, _ = host
    sess = SessionModel(
        host_user_id=host_user.id,
        livekit_room_name="salon-test-room",
        source_type="url",
        source_url="https://example.com",
        source_content="content",
        status="active",
    )
    db.add(sess)
    db.commit()
    db.refresh(sess)
    return sess


# ─── Auth guard ──────────────────────────────────────────────────────────────

def test_invite_requires_auth(client, active_session):
    resp = client.post(
        f"/sessions/{active_session.id}/invitations",
        json={"guestPhoneNumber": "+15143333333"},
    )
    assert resp.status_code == 401


def test_list_invitations_requires_auth(client):
    resp = client.get("/me/invitations")
    assert resp.status_code == 401


# ─── Phone validation ────────────────────────────────────────────────────────

def test_invite_rejects_invalid_phone(client, host, active_session):
    _, token = host
    resp = client.post(
        f"/sessions/{active_session.id}/invitations",
        json={"guestPhoneNumber": "not-a-phone"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


# ─── Session ownership ───────────────────────────────────────────────────────

def test_invite_wrong_session_returns_404(client, db, host):
    _, token = host
    resp = client.post(
        f"/sessions/{uuid.uuid4()}/invitations",
        json={"guestPhoneNumber": "+15143333333"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


# ─── SMS contact (unregistered phone) ────────────────────────────────────────

@patch("src.services.invitation_service._send_invitation_sms")
def test_invite_sms_contact(mock_sms, client, host, active_session):
    _, token = host
    resp = client.post(
        f"/sessions/{active_session.id}/invitations",
        json={"guestPhoneNumber": "+15149999999"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["invitationType"] == "sms_contact"
    assert data["status"] == "pending"
    assert data["joinLink"] is not None
    assert "/join/" in data["joinLink"]
    mock_sms.assert_called_once()


# ─── Salon friend (registered user) ──────────────────────────────────────────

@patch("src.services.invitation_service._send_invitation_sms")
def test_invite_salon_friend(mock_sms, client, host, active_session, guest_user):
    _, token = host
    resp = client.post(
        f"/sessions/{active_session.id}/invitations",
        json={"guestPhoneNumber": guest_user.phone_number},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["invitationType"] == "salon_friend"
    assert data["joinLink"] is None
    mock_sms.assert_not_called()


# ─── Idempotency ─────────────────────────────────────────────────────────────

@patch("src.services.invitation_service._send_invitation_sms")
def test_invite_idempotent_within_5_min(mock_sms, client, host, active_session):
    _, token = host
    payload = {"guestPhoneNumber": "+15149999999"}
    headers = {"Authorization": f"Bearer {token}"}

    r1 = client.post(f"/sessions/{active_session.id}/invitations", json=payload, headers=headers)
    r2 = client.post(f"/sessions/{active_session.id}/invitations", json=payload, headers=headers)

    assert r1.status_code == 201
    assert r2.status_code == 201
    assert r1.json()["invitationId"] == r2.json()["invitationId"]
    # SMS sent only once
    assert mock_sms.call_count == 1


# ─── SMS failure returns 503 without orphaning invitation ────────────────────

@patch("src.services.invitation_service._send_invitation_sms", side_effect=__import__('fastapi').HTTPException(503, "SMS unavailable"))
def test_invite_sms_failure_returns_503_no_orphan(mock_sms, client, host, active_session, db):
    from src.models.invitation import Invitation
    _, token = host
    resp = client.post(
        f"/sessions/{active_session.id}/invitations",
        json={"guestPhoneNumber": "+15149999999"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 503
    # No orphaned invitation row should remain
    assert db.query(Invitation).count() == 0


# ─── GET /me/invitations ─────────────────────────────────────────────────────

@patch("src.services.invitation_service._send_invitation_sms")
def test_list_invitations_returns_salon_friend_invites(mock_sms, client, host, active_session, guest_user, db):
    host_user, host_token = host
    guest_token = issue_token(str(guest_user.id))

    # Host invites the registered Salon user
    resp = client.post(
        f"/sessions/{active_session.id}/invitations",
        json={"guestPhoneNumber": guest_user.phone_number},
        headers={"Authorization": f"Bearer {host_token}"},
    )
    assert resp.status_code == 201

    # Guest polls their pending invitations
    list_resp = client.get("/me/invitations", headers={"Authorization": f"Bearer {guest_token}"})
    assert list_resp.status_code == 200
    invitations = list_resp.json()
    assert len(invitations) == 1
    inv = invitations[0]
    assert inv["livekitRoomName"] == "salon-test-room"
    assert inv["hostPhone"] == host_user.phone_number


@patch("src.services.invitation_service._send_invitation_sms")
def test_list_invitations_empty_for_unrelated_user(mock_sms, client, db, host, active_session, guest_user):
    _, host_token = host
    # Invite the guest
    client.post(
        f"/sessions/{active_session.id}/invitations",
        json={"guestPhoneNumber": guest_user.phone_number},
        headers={"Authorization": f"Bearer {host_token}"},
    )
    # A third user sees nothing
    other = User(email="15148888888@example.com", phone_number="+15148888888")
    db.add(other)
    db.commit()
    db.refresh(other)
    other_token = issue_token(str(other.id))

    resp = client.get("/me/invitations", headers={"Authorization": f"Bearer {other_token}"})
    assert resp.status_code == 200
    assert resp.json() == []
