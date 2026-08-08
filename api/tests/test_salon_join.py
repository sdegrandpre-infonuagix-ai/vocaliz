"""Tests for POST /salons/{salon_id}/join (Story 2.6)."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from src.models.invitation import Invitation
from src.models.salon import Salon
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
def guest(db):
    u = User(email="15142222222@example.com", phone_number="+15142222222")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u, issue_token(str(u.id))


@pytest.fixture
def active_salon(db, host):
    host_user, _ = host
    sess = Salon(
        host_user_id=host_user.id,
        livekit_room_name="salon-join-room",
        source_type="url",
        source_url="https://example.com",
        source_content="content",
        status="active",
    )
    db.add(sess)
    db.commit()
    db.refresh(sess)
    return sess


@pytest.fixture
def ended_salon(db, host):
    host_user, _ = host
    sess = Salon(
        host_user_id=host_user.id,
        livekit_room_name="salon-ended",
        source_type="url",
        source_content="content",
        status="ended",
    )
    db.add(sess)
    db.commit()
    db.refresh(sess)
    return sess


@pytest.fixture
def pending_invitation(db, active_salon, guest):
    guest_user, _ = guest
    inv = Invitation(
        salon_id=active_salon.id,
        host_user_id=active_salon.host_user_id,
        guest_email=guest_user.phone_number.lstrip("+") + "@example.com",
        guest_user_id=guest_user.id,
        invitation_type="salon_friend",
        join_token="tok123",
        status="pending",
        expires_at=datetime.now(tz=timezone.utc) + timedelta(hours=24),
    )
    db.add(inv)
    db.commit()
    db.refresh(inv)
    return inv


# ─── Auth guard ──────────────────────────────────────────────────────────────

def test_join_requires_auth(client, active_salon):
    resp = client.post(f"/salons/{active_salon.id}/join")
    assert resp.status_code == 401


# ─── Salon status ───────────────────────────────────────────────────────────

def test_join_ended_salon_returns_409(client, host, ended_salon):
    _, token = host
    resp = client.post(
        f"/salons/{ended_salon.id}/join",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 409


def test_join_unknown_salon_returns_404(client, host):
    _, token = host
    resp = client.post(
        f"/salons/{uuid.uuid4()}/join",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


# ─── Host rejoins ────────────────────────────────────────────────────────────

def test_host_can_join_own_salon(client, host, active_salon):
    _, token = host
    resp = client.post(
        f"/salons/{active_salon.id}/join",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "participantToken" in data
    assert data["livekitRoomName"] == "salon-join-room"
    assert "livekitUrl" in data


# ─── Invited guest joins ──────────────────────────────────────────────────────

def test_invited_guest_can_join(client, guest, active_salon, pending_invitation, db):
    _, token = guest
    resp = client.post(
        f"/salons/{active_salon.id}/join",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "participantToken" in data

    # Invitation should be marked accepted
    db.refresh(pending_invitation)
    assert pending_invitation.status == "accepted"


def test_uninvited_user_cannot_join(client, db, active_salon):
    stranger = User(email="15149999999@example.com", phone_number="+15149999999")
    db.add(stranger)
    db.commit()
    db.refresh(stranger)
    token = issue_token(str(stranger.id))

    resp = client.post(
        f"/salons/{active_salon.id}/join",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


def test_expired_invitation_cannot_join(client, db, guest, active_salon):
    guest_user, token = guest
    inv = Invitation(
        salon_id=active_salon.id,
        host_user_id=active_salon.host_user_id,
        guest_email=guest_user.phone_number.lstrip("+") + "@example.com",
        guest_user_id=guest_user.id,
        invitation_type="salon_friend",
        join_token="expired-tok",
        status="pending",
        expires_at=datetime.now(tz=timezone.utc) - timedelta(hours=1),  # expired
    )
    db.add(inv)
    db.commit()

    resp = client.post(
        f"/salons/{active_salon.id}/join",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403
