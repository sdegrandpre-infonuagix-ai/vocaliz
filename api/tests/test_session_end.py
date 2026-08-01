"""Tests for POST /sessions/{session_id}/end (Story 2.11)."""
import uuid
from datetime import datetime, timezone

import pytest

from src.models.session import SessionModel
from src.models.user import User
from src.services.jwt_service import issue_token


# ─── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def host(db):
    u = User(email="15143330000@example.com", phone_number="+15143330000")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u, issue_token(str(u.id))


@pytest.fixture
def other_user(db):
    u = User(email="15143331111@example.com", phone_number="+15143331111")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u, issue_token(str(u.id))


@pytest.fixture
def active_session(db, host):
    host_user, _ = host
    sess = SessionModel(
        host_user_id=host_user.id,
        livekit_room_name="salon-end-test-room",
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
def ended_session(db, host):
    host_user, _ = host
    sess = SessionModel(
        host_user_id=host_user.id,
        livekit_room_name="salon-already-ended",
        source_type="url",
        source_content="content",
        status="ended",
        ended_at=datetime.now(tz=timezone.utc),
    )
    db.add(sess)
    db.commit()
    db.refresh(sess)
    return sess


# ─── Tests ────────────────────────────────────────────────────────────────────

def test_end_session_success(client, host, active_session):
    """Host can end their active session."""
    _, token = host
    resp = client.post(
        f"/sessions/{active_session.id}/end",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["sessionId"] == str(active_session.id)
    assert body["status"] == "ended"
    assert "endedAt" in body
    assert body["endedAt"] is not None


def test_end_session_persists_status(client, host, active_session, db):
    """Session status is persisted as 'ended' in the database."""
    _, token = host
    client.post(
        f"/sessions/{active_session.id}/end",
        headers={"Authorization": f"Bearer {token}"},
    )
    db.expire(active_session)
    db.refresh(active_session)
    assert active_session.status == "ended"
    assert active_session.ended_at is not None


def test_end_session_persists_ended_at_timestamp(client, host, active_session, db):
    """ended_at timestamp is populated and timezone-aware."""
    _, token = host
    before = datetime.now(tz=timezone.utc)
    client.post(
        f"/sessions/{active_session.id}/end",
        headers={"Authorization": f"Bearer {token}"},
    )
    after = datetime.now(tz=timezone.utc)
    db.expire(active_session)
    db.refresh(active_session)
    assert active_session.ended_at is not None
    ts = active_session.ended_at
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    assert before <= ts <= after


def test_end_already_ended_session_returns_409(client, host, ended_session):
    """Calling end on an already-ended session returns 409 Conflict."""
    _, token = host
    resp = client.post(
        f"/sessions/{ended_session.id}/end",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 409
    assert "already ended" in resp.json()["detail"]


def test_end_session_by_non_host_returns_404(client, other_user, active_session):
    """Non-host cannot end someone else's session (returns 404, not 403)."""
    _, token = other_user
    resp = client.post(
        f"/sessions/{active_session.id}/end",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


def test_end_session_unauthenticated_returns_401(client, active_session):
    """Unauthenticated request is rejected."""
    resp = client.post(f"/sessions/{active_session.id}/end")
    assert resp.status_code == 401


def test_end_session_invalid_uuid_returns_404(client, host):
    """Malformed session ID returns 404."""
    _, token = host
    resp = client.post(
        "/sessions/not-a-uuid/end",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


def test_end_session_unknown_uuid_returns_404(client, host):
    """Unknown session UUID returns 404."""
    _, token = host
    resp = client.post(
        f"/sessions/{uuid.uuid4()}/end",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404
