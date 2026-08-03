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
@patch(
    "src.routers.sessions.content_service.fetch_url_document",
    new_callable=AsyncMock,
    return_value=("Article text.", {"article_date": "", "author": "", "publisher": ""}),
)
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


# ─── One open session per host ───────────────────────────────────────────────

@patch("src.services.livekit_service.delete_room", new_callable=AsyncMock)
@patch("src.routers.sessions.livekit_service.create_room", new_callable=AsyncMock)
@patch("src.routers.sessions.livekit_service.generate_participant_token", return_value="tok")
def test_creating_a_session_closes_the_previous_one(
    mock_token, mock_room, mock_delete, client, db, user
):
    """A host may never hold two open sessions.

    A stale session keeps its agent alive and talking, so joining the new room could
    surface the previous agent — the failure this rule exists to prevent.
    """
    from src.models.session import SessionModel

    _, token = user
    headers = {"Authorization": f"Bearer {token}"}

    first = client.post("/sessions", data={}, headers=headers).json()["sessionId"]
    second = client.post("/sessions", data={}, headers=headers).json()["sessionId"]
    assert first != second

    db.expire_all()
    sessions = {str(s.id): s.status for s in db.query(SessionModel).all()}
    assert sessions[first] == "ended"
    assert sessions[second] == "active"


@patch("src.services.livekit_service.delete_room", new_callable=AsyncMock)
@patch("src.routers.sessions.livekit_service.create_room", new_callable=AsyncMock)
@patch("src.routers.sessions.livekit_service.generate_participant_token", return_value="tok")
def test_previous_room_is_deleted_not_just_marked_ended(
    mock_token, mock_room, mock_delete, client, db, user
):
    """Deleting the room is what stops the old agent; the row only settles accounting."""
    from src.models.session import SessionModel

    _, token = user
    headers = {"Authorization": f"Bearer {token}"}

    client.post("/sessions", data={}, headers=headers)
    first_room = db.query(SessionModel).first().livekit_room_name

    client.post("/sessions", data={}, headers=headers)

    mock_delete.assert_awaited()
    assert first_room in [call.args[0] for call in mock_delete.await_args_list]


@patch("src.services.livekit_service.delete_room", new_callable=AsyncMock)
@patch("src.routers.sessions.livekit_service.create_room", new_callable=AsyncMock)
@patch("src.routers.sessions.livekit_service.generate_participant_token", return_value="tok")
def test_another_host_session_is_left_alone(
    mock_token, mock_room, mock_delete, client, db, user
):
    """Cleanup is scoped to the caller: it must never close someone else's session."""
    from src.models.session import SessionModel
    from src.models.user import User
    from src.services.jwt_service import issue_token

    other = User(email="other.host@example.com")
    db.add(other)
    db.commit()
    db.refresh(other)
    theirs = SessionModel(
        host_user_id=other.id,
        livekit_room_name="salon-theirs",
        source_type="none",
        status="active",
    )
    db.add(theirs)
    db.commit()

    _, token = user
    client.post("/sessions", data={}, headers={"Authorization": f"Bearer {token}"})

    db.expire(theirs)
    db.refresh(theirs)
    assert theirs.status == "active"


# ─── Live captions need the token to allow it ────────────────────────────────

def test_participant_token_allows_updating_own_attributes():
    """Captions depend on it, and its absence fails silently.

    A participant announces the language it is reading by setting its own caption_lang
    attribute. Without canUpdateOwnMetadata the server refuses the call, the agent sees
    nobody asking for a translation, and captions come back in the language they were
    spoken — which is indistinguishable from a translator that is not working.
    """
    import jwt as pyjwt

    from src.config import settings
    from src.services import livekit_service

    token = livekit_service.generate_participant_token("salon-x", "user-1")
    claims = pyjwt.decode(token, settings.livekit_api_secret, algorithms=["HS256"])
    assert claims["video"]["canUpdateOwnMetadata"] is True


# ─── Public configuration ────────────────────────────────────────────────────

def test_config_is_readable_without_a_token(client):
    """The sign-in screen reads it, so requiring a token would make it unusable."""
    assert client.get("/config").status_code == 200


def test_sms_is_off_by_default(client):
    """Text messaging waits on an AWS review. Off is the safe direction: a host never
    sees a channel that cannot deliver."""
    assert client.get("/config").json() == {"smsEnabled": False}


def test_config_follows_the_setting(client):
    from src.config import settings

    original = settings.sms_enabled
    settings.sms_enabled = True
    try:
        assert client.get("/config").json()["smsEnabled"] is True
    finally:
        settings.sms_enabled = original


def test_a_phone_invitation_is_still_accepted_while_the_field_is_hidden(client, db):
    """The flag governs what is offered, not what is allowed.

    Hiding the field is a client concern; refusing the request would also break the API
    for anyone testing the path before the review clears.
    """
    from unittest.mock import patch

    from src.models.session import SessionModel
    from src.models.user import User
    from src.services import sms_service
    from src.services.jwt_service import issue_token

    user = User(email="flaghost@example.com")
    db.add(user)
    db.commit()
    db.refresh(user)
    sess = SessionModel(
        host_user_id=user.id,
        livekit_room_name="salon-flag",
        source_type="url",
        source_content="c",
        status="active",
    )
    db.add(sess)
    db.commit()
    db.refresh(sess)

    with patch.object(sms_service, "send_invitation_sms", return_value=True):
        response = client.post(
            f"/sessions/{sess.id}/invitations",
            json={"guestPhone": "+15145550123"},
            headers={"Authorization": f"Bearer {issue_token(str(user.id))}"},
        )
    assert response.status_code == 201


def test_a_room_holds_a_host_three_guests_and_the_agent():
    """Two guests more than before. The cap is what LiveKit enforces, so it is the only
    place this limit is real."""
    from src.config import settings

    assert settings.livekit_room_max_participants == 5
