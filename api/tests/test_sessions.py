"""Tests for session creation endpoint."""
import io
import pytest
from unittest.mock import AsyncMock, patch

from src.models.user import User
from src.services.jwt_service import issue_token


@pytest.fixture
def user(db):
    u = User(phone_number="+15141234567")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u, issue_token(str(u.id))


# ─── Auth guard ─────────────────────────────────────────────────────────────

def test_create_session_requires_auth(client):
    response = client.post("/sessions", data={"source_url": "https://example.com"})
    assert response.status_code == 401


# ─── Missing source validation ───────────────────────────────────────────────

@patch("src.routers.sessions.livekit_service.create_room", new_callable=AsyncMock)
@patch("src.routers.sessions.livekit_service.generate_participant_token", return_value="tok")
@patch("src.routers.sessions.livekit_service.new_room_name", return_value="salon-test")
def test_create_session_no_source(mock_name, mock_token, mock_room, client, user):
    _, token = user
    response = client.post("/sessions", data={}, headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 400
    assert "requis" in response.json()["detail"]


# ─── URL source ──────────────────────────────────────────────────────────────

@patch("src.routers.sessions.livekit_service.create_room", new_callable=AsyncMock)
@patch("src.routers.sessions.livekit_service.generate_participant_token", return_value="lk-tok")
@patch("src.routers.sessions.livekit_service.new_room_name", return_value="salon-abc")
@patch("src.routers.sessions.content_service.fetch_url_content", new_callable=AsyncMock, return_value="Article text.")
def test_create_session_url_success(mock_content, mock_name, mock_token, mock_room, client, user, db):
    _, token = user
    response = client.post(
        "/sessions",
        data={"source_url": "https://example.com/article"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["livekitRoomName"] == "salon-abc"
    assert data["hostToken"] == "lk-tok"
    assert data["sourceType"] == "url"
    assert "sessionId" in data
    assert "createdAt" in data

    from src.models.session import SessionModel
    session = db.query(SessionModel).first()
    assert session.source_url == "https://example.com/article"
    assert session.source_content == "Article text."


# ─── Document upload ─────────────────────────────────────────────────────────

@patch("src.routers.sessions.livekit_service.create_room", new_callable=AsyncMock)
@patch("src.routers.sessions.livekit_service.generate_participant_token", return_value="lk-tok")
@patch("src.routers.sessions.livekit_service.new_room_name", return_value="salon-doc")
def test_create_session_txt_upload(mock_name, mock_token, mock_room, client, user, db):
    _, token = user
    response = client.post(
        "/sessions",
        files={"file": ("test.txt", io.BytesIO(b"Plain text content."), "text/plain")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201
    assert response.json()["sourceType"] == "document"

    from src.models.session import SessionModel
    session = db.query(SessionModel).first()
    assert session.source_filename == "test.txt"
    assert session.source_content == "Plain text content."


@patch("src.routers.sessions.livekit_service.create_room", new_callable=AsyncMock)
@patch("src.routers.sessions.livekit_service.generate_participant_token", return_value="tok")
@patch("src.routers.sessions.livekit_service.new_room_name", return_value="salon-bad")
def test_create_session_unsupported_file_type(mock_name, mock_token, mock_room, client, user):
    _, token = user
    response = client.post(
        "/sessions",
        files={"file": ("test.docx", io.BytesIO(b"data"), "application/vnd.openxmlformats")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 415


# ─── Content service unit tests ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_extract_html_text_strips_scripts():
    from src.services.content_service import _extract_html_text
    html = "<html><body><script>alert(1)</script><p>Hello world</p></body></html>"
    result = _extract_html_text(html)
    assert "Hello world" in result
    assert "alert" not in result


def test_content_url_rejects_non_http():
    import asyncio
    from fastapi import HTTPException
    from src.services.content_service import fetch_url_content
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(fetch_url_content("ftp://bad"))
    assert exc_info.value.status_code == 400
