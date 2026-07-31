"""Tests for GET /sessions/{session_id} (Story 2.4)."""
import uuid

import pytest

from src.models.session import SessionModel
from src.models.session_source import SessionSource
from src.models.user import User
from src.services.jwt_service import issue_token


@pytest.fixture
def host(db):
    u = User(email="15141111111@example.com", phone_number="+15141111111")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u, issue_token(str(u.id))


@pytest.fixture
def session_with_content(db, host):
    host_user, _ = host
    sess = SessionModel(
        host_user_id=host_user.id,
        livekit_room_name="salon-detail-room",
        source_type="url",
        source_url="https://example.com/article",
        source_content="This is the article text about a very interesting topic.",
        status="active",
    )
    db.add(sess)
    db.commit()
    db.refresh(sess)
    return sess


# ─── Auth guard ──────────────────────────────────────────────────────────────

def test_get_session_requires_auth(client, session_with_content):
    resp = client.get(f"/sessions/{session_with_content.id}")
    assert resp.status_code == 401


# ─── Ownership check ─────────────────────────────────────────────────────────

def test_get_session_non_host_returns_404(client, db, session_with_content):
    other = User(email="15148888888@example.com", phone_number="+15148888888")
    db.add(other)
    db.commit()
    db.refresh(other)
    token = issue_token(str(other.id))

    resp = client.get(f"/sessions/{session_with_content.id}", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 404


def test_get_session_unknown_id_returns_404(client, host):
    _, token = host
    resp = client.get(f"/sessions/{uuid.uuid4()}", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 404


# ─── Happy path ──────────────────────────────────────────────────────────────

def test_get_session_returns_content(client, host, session_with_content):
    _, token = host
    resp = client.get(
        f"/sessions/{session_with_content.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["sessionId"] == str(session_with_content.id)
    assert data["sourceContent"] == "This is the article text about a very interesting topic."
    assert data["sourceUrl"] == "https://example.com/article"
    assert data["sourceType"] == "url"
    assert data["status"] == "active"
    assert data["additionalSources"] == []


def test_get_session_includes_additional_sources(client, host, session_with_content, db):
    _, token = host
    extra = SessionSource(
        session_id=session_with_content.id,
        host_user_id=session_with_content.host_user_id,
        source_type="document",
        source_content="Extra document content.",
    )
    db.add(extra)
    db.commit()

    resp = client.get(
        f"/sessions/{session_with_content.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    sources = resp.json()["additionalSources"]
    assert len(sources) == 1
    assert sources[0]["sourceType"] == "document"
    assert sources[0]["contentLength"] == len("Extra document content.")
    # Content is returned so the agent can introduce contrasting perspectives (Story 2.5)
    assert sources[0]["sourceContent"] == "Extra document content."


def test_get_session_additional_sources_include_url(client, host, session_with_content, db):
    _, token = host
    extra = SessionSource(
        session_id=session_with_content.id,
        host_user_id=session_with_content.host_user_id,
        source_type="url",
        source_url="https://example.com/contrast",
        source_content="A contrasting perspective.",
    )
    db.add(extra)
    db.commit()

    resp = client.get(
        f"/sessions/{session_with_content.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    src = resp.json()["additionalSources"][0]
    assert src["sourceUrl"] == "https://example.com/contrast"
    assert src["sourceContent"] == "A contrasting perspective."

