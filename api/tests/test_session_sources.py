"""Tests for POST /sessions/{session_id}/sources (Story 2.3)."""
import io
import uuid
from unittest.mock import AsyncMock, patch

import pytest

from src.models.session import SessionModel
from src.models.session_source import SessionSource
from src.models.user import User
from src.services.jwt_service import issue_token


# ─── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def host(db):
    u = User(phone_number="+15141111111")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u, issue_token(str(u.id))


@pytest.fixture
def active_session(db, host):
    host_user, _ = host
    sess = SessionModel(
        host_user_id=host_user.id,
        livekit_room_name="salon-test-room",
        source_type="url",
        source_url="https://example.com",
        source_content="original content",
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
        livekit_room_name="salon-ended-room",
        source_type="url",
        source_url="https://example.com",
        source_content="content",
        status="ended",
    )
    db.add(sess)
    db.commit()
    db.refresh(sess)
    return sess


# ─── Auth guard ──────────────────────────────────────────────────────────────

def test_add_source_requires_auth(client, active_session):
    resp = client.post(
        f"/sessions/{active_session.id}/sources",
        data={"source_url": "https://example.com/new"},
    )
    assert resp.status_code == 401


# ─── Session ownership ───────────────────────────────────────────────────────

def test_add_source_wrong_session_returns_404(client, host):
    _, token = host
    resp = client.post(
        f"/sessions/{uuid.uuid4()}/sources",
        data={"source_url": "https://example.com/new"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


def test_add_source_non_host_returns_404(client, db, active_session):
    other = User(phone_number="+15148888888")
    db.add(other)
    db.commit()
    db.refresh(other)
    other_token = issue_token(str(other.id))

    resp = client.post(
        f"/sessions/{active_session.id}/sources",
        data={"source_url": "https://example.com/new"},
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert resp.status_code == 404


# ─── Session status check ────────────────────────────────────────────────────

@patch("src.routers.sessions.content_service.fetch_url_content", new_callable=AsyncMock, return_value="text")
def test_add_source_to_ended_session_returns_409(mock_content, client, host, ended_session):
    _, token = host
    resp = client.post(
        f"/sessions/{ended_session.id}/sources",
        data={"source_url": "https://example.com/new"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 409


# ─── Missing source validation ───────────────────────────────────────────────

def test_add_source_no_input_returns_400(client, host, active_session):
    _, token = host
    resp = client.post(
        f"/sessions/{active_session.id}/sources",
        data={},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400


# ─── URL source ──────────────────────────────────────────────────────────────

@patch("src.routers.sessions.content_service.fetch_url_content", new_callable=AsyncMock, return_value="New article text.")
def test_add_url_source_success(mock_content, client, host, active_session, db):
    _, token = host
    resp = client.post(
        f"/sessions/{active_session.id}/sources",
        data={"source_url": "https://example.com/new-article"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["sourceType"] == "url"
    assert data["contentLength"] == len("New article text.")
    assert data["sessionId"] == str(active_session.id)
    assert "sourceId" in data
    assert "createdAt" in data

    src = db.query(SessionSource).first()
    assert src.source_url == "https://example.com/new-article"
    assert src.source_content == "New article text."
    assert src.session_id == active_session.id


# ─── Document upload ─────────────────────────────────────────────────────────

@patch("src.routers.sessions.livekit_service.create_room", new_callable=AsyncMock)
@patch("src.routers.sessions.livekit_service.generate_participant_token", return_value="tok")
@patch("src.routers.sessions.livekit_service.new_room_name", return_value="room-doc")
def test_add_document_source_success(mock_name, mock_token, mock_room, client, host, active_session, db):
    _, token = host
    resp = client.post(
        f"/sessions/{active_session.id}/sources",
        files={"file": ("notes.txt", io.BytesIO(b"Meeting notes content."), "text/plain")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["sourceType"] == "document"
    assert data["contentLength"] > 0

    src = db.query(SessionSource).first()
    assert src.source_filename == "notes.txt"
    assert src.source_content == "Meeting notes content."


# ─── Multiple sources per session ────────────────────────────────────────────

@patch("src.routers.sessions.content_service.fetch_url_content", new_callable=AsyncMock, return_value="content")
def test_multiple_sources_accumulate(mock_content, client, host, active_session, db):
    _, token = host
    headers = {"Authorization": f"Bearer {token}"}
    urls = ["https://example.com/a", "https://example.com/b"]
    for url in urls:
        resp = client.post(
            f"/sessions/{active_session.id}/sources",
            data={"source_url": url},
            headers=headers,
        )
        assert resp.status_code == 201

    assert db.query(SessionSource).filter_by(session_id=active_session.id).count() == 2
