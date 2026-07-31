"""Tests for session creation endpoint."""
import io
import pytest
from unittest.mock import AsyncMock, patch

from src.models.user import User
from src.services.jwt_service import issue_token


@pytest.fixture
def user(db):
    u = User(email="15141234567@example.com", phone_number="+15141234567")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u, issue_token(str(u.id))


# ─── Auth guard ─────────────────────────────────────────────────────────────

def test_create_session_requires_auth(client):
    response = client.post("/sessions", data={"source_url": "https://example.com"})
    assert response.status_code == 401


# ─── Source-less session ─────────────────────────────────────────────────────

@patch("src.routers.sessions.livekit_service.create_room", new_callable=AsyncMock)
@patch("src.routers.sessions.livekit_service.generate_participant_token", return_value="tok")
@patch("src.routers.sessions.livekit_service.new_room_name", return_value="salon-test")
def test_create_session_no_source(mock_name, mock_token, mock_room, client, user):
    """A session may start with no document and no URL — the agent then asks the
    participants what they want to discuss."""
    _, token = user
    response = client.post("/sessions", data={}, headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 201
    body = response.json()
    assert body["sourceType"] == "none"
    assert body["livekitRoomName"] == "salon-test"
    assert body["hostToken"] == "tok"


@patch("src.routers.sessions.livekit_service.create_room", new_callable=AsyncMock)
@patch("src.routers.sessions.livekit_service.generate_participant_token", return_value="tok")
@patch("src.routers.sessions.livekit_service.new_room_name", return_value="salon-test")
def test_create_session_no_source_persists_empty_content(
    mock_name, mock_token, mock_room, client, db, user
):
    """No source means no extracted content to inject into the agent prompt."""
    from src.models.session import SessionModel
    _, token = user
    client.post("/sessions", data={}, headers={"Authorization": f"Bearer {token}"})
    session = db.query(SessionModel).first()
    assert session.source_type == "none"
    assert session.source_content is None
    assert session.source_url is None
    assert session.source_filename is None


# ─── Agent dispatch ──────────────────────────────────────────────────────────

@patch("src.routers.sessions.livekit_service.dispatch_agent", new_callable=AsyncMock)
@patch("src.routers.sessions.livekit_service.create_room", new_callable=AsyncMock)
@patch("src.routers.sessions.livekit_service.generate_participant_token", return_value="tok")
@patch("src.routers.sessions.livekit_service.new_room_name", return_value="salon-test")
def test_create_session_dispatches_agent_with_context(
    mock_name, mock_token, mock_room, mock_dispatch, client, user
):
    """The agent is useless without session context, so creation must dispatch it.

    Passing the context through job metadata (not room metadata) keeps the host token
    away from participants.
    """
    _, token = user
    response = client.post("/sessions", data={}, headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 201

    mock_dispatch.assert_awaited_once()
    kwargs = mock_dispatch.await_args.kwargs
    assert mock_dispatch.await_args.args[0] == "salon-test"
    assert kwargs["session_id"] == response.json()["sessionId"]

    # Must be a Salon API JWT for the host, not the LiveKit participant token: the agent
    # authenticates against our REST API with it.
    from src.services.jwt_service import decode_token
    host, _ = user
    assert kwargs["host_token"] != "tok"
    assert decode_token(kwargs["host_token"])["sub"] == str(host.id)


@pytest.mark.real_livekit_service
@pytest.mark.asyncio
@patch("src.services.livekit_service.lk_api.LiveKitAPI")
async def test_dispatch_agent_swallows_livekit_failure(mock_api):
    """Dispatch failure must not raise: the room exists and participants can still talk.

    Exercises the real service, not a mock of it — patching dispatch_agent itself would
    bypass the try/except this asserts.
    """
    from src.services import livekit_service

    mock_api.side_effect = RuntimeError("livekit unreachable")
    assert await livekit_service.dispatch_agent(
        "salon-test", session_id="s1", host_token="tok"
    ) is None


@pytest.mark.real_livekit_service
@pytest.mark.asyncio
@patch("src.services.livekit_service.lk_api.LiveKitAPI")
async def test_notify_room_swallows_livekit_failure(mock_api):
    """Same for notifications: a lost source_added message must not fail the request."""
    from src.services import livekit_service

    mock_api.side_effect = RuntimeError("livekit unreachable")
    assert await livekit_service.notify_room("salon-test", {"action": "source_added"}) is None


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


@pytest.mark.asyncio
async def test_fetch_url_rejects_ssrf_loopback():
    from fastapi import HTTPException
    from src.services.content_service import fetch_url_content
    with pytest.raises(HTTPException) as exc_info:
        await fetch_url_content("http://127.0.0.1/admin")
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_fetch_url_rejects_ssrf_link_local():
    from fastapi import HTTPException
    from src.services.content_service import fetch_url_content
    with pytest.raises(HTTPException) as exc_info:
        await fetch_url_content("http://169.254.169.254/latest/meta-data/")
    assert exc_info.value.status_code == 400
