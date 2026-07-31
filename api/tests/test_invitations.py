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
        json={"guestEmail": "15143333333@example.com"},
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
        json={"guestEmail": "not-an-email"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


# ─── Session ownership ───────────────────────────────────────────────────────

def test_invite_wrong_session_returns_404(client, db, host):
    _, token = host
    resp = client.post(
        f"/sessions/{uuid.uuid4()}/invitations",
        json={"guestEmail": "15143333333@example.com"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


# ─── SMS contact (unregistered phone) ────────────────────────────────────────

@patch("src.services.invitation_service._send_invitation_email")
def test_invite_sms_contact(mock_sms, client, host, active_session):
    _, token = host
    resp = client.post(
        f"/sessions/{active_session.id}/invitations",
        json={"guestEmail": "15149999999@example.com"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["invitationType"] == "email_contact"
    assert data["status"] == "pending"
    assert data["joinLink"] is not None
    assert "/join/" in data["joinLink"]
    mock_sms.assert_called_once()


# ─── Salon friend (registered user) ──────────────────────────────────────────

@patch("src.services.invitation_service._send_invitation_email")
def test_invite_salon_friend(mock_sms, client, host, active_session, guest_user):
    _, token = host
    resp = client.post(
        f"/sessions/{active_session.id}/invitations",
        json={"guestEmail": guest_user.email},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["invitationType"] == "salon_friend"
    assert data["joinLink"] is None
    mock_sms.assert_not_called()


# ─── Idempotency ─────────────────────────────────────────────────────────────

@patch("src.services.invitation_service._send_invitation_email")
def test_invite_idempotent_within_5_min(mock_sms, client, host, active_session):
    _, token = host
    payload = {"guestEmail": "15149999999@example.com"}
    headers = {"Authorization": f"Bearer {token}"}

    r1 = client.post(f"/sessions/{active_session.id}/invitations", json=payload, headers=headers)
    r2 = client.post(f"/sessions/{active_session.id}/invitations", json=payload, headers=headers)

    assert r1.status_code == 201
    assert r2.status_code == 201
    assert r1.json()["invitationId"] == r2.json()["invitationId"]
    # SMS sent only once
    assert mock_sms.call_count == 1


# ─── A failed send keeps the invitation ──────────────────────────────────────

@patch("src.services.invitation_service._send_invitation_email", side_effect=__import__('fastapi').HTTPException(503, "SES unavailable"))
def test_invite_keeps_invitation_when_email_fails(mock_send, client, host, active_session, db):
    """This test previously asserted the opposite — a 503 and no invitation row.

    Rolling back was wrong: the join link works over any channel, so discarding it
    because one channel failed left the host with nothing to share. The invitation is
    kept, the link is returned, and emailSent reports the failure.
    """
    from src.models.invitation import Invitation
    _, token = host
    resp = client.post(
        f"/sessions/{active_session.id}/invitations",
        json={"guestEmail": "15149999999@example.com"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    assert resp.json()["emailSent"] is False
    assert resp.json()["joinLink"]
    assert db.query(Invitation).count() == 1


# ─── GET /me/invitations ─────────────────────────────────────────────────────

@patch("src.services.invitation_service._send_invitation_email")
def test_list_invitations_returns_salon_friend_invites(mock_sms, client, host, active_session, guest_user, db):
    host_user, host_token = host
    guest_token = issue_token(str(guest_user.id))

    # Host invites the registered Salon user
    resp = client.post(
        f"/sessions/{active_session.id}/invitations",
        json={"guestEmail": guest_user.email},
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


@patch("src.services.invitation_service._send_invitation_email")
def test_list_invitations_empty_for_unrelated_user(mock_sms, client, db, host, active_session, guest_user):
    _, host_token = host
    # Invite the guest
    client.post(
        f"/sessions/{active_session.id}/invitations",
        json={"guestEmail": guest_user.email},
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


# ─── The link must survive a failed email ────────────────────────────────────

@patch("src.services.invitation_service._send_invitation_email")
def test_invitation_survives_failed_email(mock_send, client, host, active_session):
    """A failed send must still yield the link: the host can then share it by hand.

    Rolling the invitation back destroyed the join link at the exact moment it was most
    needed — and the link works over any channel, not just email.
    """
    from fastapi import HTTPException

    mock_send.side_effect = HTTPException(status_code=503, detail="SES indisponible")
    _, token = host

    resp = client.post(
        f"/sessions/{active_session.id}/invitations",
        json={"guestEmail": "unreachable@example.com"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["joinLink"]
    assert body["emailSent"] is False


@patch("src.services.invitation_service._send_invitation_email")
def test_invitation_reports_successful_delivery(mock_send, client, host, active_session):
    """emailSent tells the host whether they still need to share the link themselves."""
    _, token = host
    resp = client.post(
        f"/sessions/{active_session.id}/invitations",
        json={"guestEmail": "reachable@example.com"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.json()["emailSent"] is True


@patch("src.services.invitation_service._send_invitation_email")
def test_email_can_be_sent_afterwards(mock_send, client, host, active_session):
    """Sending is a separate step, and reuses the same token rather than minting one."""
    _, token = host
    headers = {"Authorization": f"Bearer {token}"}

    created = client.post(
        f"/sessions/{active_session.id}/invitations",
        json={"guestEmail": "later@example.com"},
        headers=headers,
    ).json()

    mock_send.reset_mock()
    resp = client.post(
        f"/sessions/{active_session.id}/invitations/{created['invitationId']}/email",
        headers=headers,
    )
    assert resp.status_code == 200
    mock_send.assert_called_once()
    # Same one-time token as the link already shown to the host.
    assert created["joinLink"].endswith(mock_send.call_args.args[1].split("/")[-1])
