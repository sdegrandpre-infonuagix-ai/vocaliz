"""Tests for POST /salons/{salon_id}/sources (Story 2.3)."""
import io
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from unittest.mock import AsyncMock, patch as _patch

from src.models.salon import Salon
from src.models.salon_source import SalonSource
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
def active_salon(db, host):
    host_user, _ = host
    sess = Salon(
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
def ended_salon(db, host):
    host_user, _ = host
    sess = Salon(
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

def test_add_source_requires_auth(client, active_salon):
    resp = client.post(
        f"/salons/{active_salon.id}/sources",
        data={"source_url": "https://example.com/new"},
    )
    assert resp.status_code == 401


# ─── Salon ownership ───────────────────────────────────────────────────────

def test_add_source_wrong_salon_returns_404(client, host):
    _, token = host
    resp = client.post(
        f"/salons/{uuid.uuid4()}/sources",
        data={"source_url": "https://example.com/new"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


def test_add_source_non_host_returns_404(client, db, active_salon):
    other = User(email="15148888888@example.com", phone_number="+15148888888")
    db.add(other)
    db.commit()
    db.refresh(other)
    other_token = issue_token(str(other.id))

    resp = client.post(
        f"/salons/{active_salon.id}/sources",
        data={"source_url": "https://example.com/new"},
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert resp.status_code == 404


# ─── Salon status check ────────────────────────────────────────────────────

@patch(
    "src.routers.salons.content_service.fetch_url_document",
    new_callable=AsyncMock,
    return_value=("text", {"article_date": "", "author": "", "publisher": ""}),
)
def test_add_source_to_ended_salon_returns_409(mock_content, client, host, ended_salon):
    _, token = host
    resp = client.post(
        f"/salons/{ended_salon.id}/sources",
        data={"source_url": "https://example.com/new"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 409


# ─── Missing source validation ───────────────────────────────────────────────

def test_add_source_no_input_returns_400(client, host, active_salon):
    _, token = host
    resp = client.post(
        f"/salons/{active_salon.id}/sources",
        data={},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400


# ─── URL source ──────────────────────────────────────────────────────────────

@patch(
    "src.routers.salons.content_service.fetch_url_document",
    new_callable=AsyncMock,
    return_value=("New article text.", {"article_date": "", "author": "", "publisher": ""}),
)
def test_add_url_source_success(mock_content, client, host, active_salon, db):
    _, token = host
    resp = client.post(
        f"/salons/{active_salon.id}/sources",
        data={"source_url": "https://example.com/new-article"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["sourceType"] == "url"
    assert data["contentLength"] == len("New article text.")
    assert data["salonId"] == str(active_salon.id)
    assert "sourceId" in data
    assert "createdAt" in data

    src = db.query(SalonSource).first()
    assert src.source_url == "https://example.com/new-article"
    assert src.source_content == "New article text."
    assert src.salon_id == active_salon.id


# ─── Live notification to the agent ──────────────────────────────────────────

@_patch("src.routers.salons.livekit_service.notify_room", new_callable=AsyncMock)
@_patch(
    "src.routers.salons.content_service.fetch_url_document",
    new_callable=AsyncMock,
    # (text, metadata). A page that carries no provenance is the ordinary case.
    return_value=("Mid-salon article.", {"article_date": "", "author": "", "publisher": ""}),
)
def test_add_source_notifies_the_room(mock_content, mock_notify, client, host, active_salon):
    """The agent reads sources once at job start, so it must be told about new ones.

    Without this message a source added mid-conversation would never reach the agent,
    leaving FR3 satisfied only in the database.
    """
    _, token = host
    resp = client.post(
        f"/salons/{active_salon.id}/sources",
        data={"source_url": "https://example.com/mid"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201

    mock_notify.assert_awaited_once()
    room_name, message = mock_notify.await_args.args
    assert room_name == active_salon.livekit_room_name
    assert message["action"] == "source_added"
    assert message["sourceId"] == resp.json()["sourceId"]


# ─── Document upload ─────────────────────────────────────────────────────────

@patch("src.routers.salons.livekit_service.create_room", new_callable=AsyncMock)
@patch("src.routers.salons.livekit_service.generate_participant_token", return_value="tok")
@patch("src.routers.salons.livekit_service.new_room_name", return_value="room-doc")
def test_add_document_source_success(mock_name, mock_token, mock_room, client, host, active_salon, db):
    _, token = host
    resp = client.post(
        f"/salons/{active_salon.id}/sources",
        files={"file": ("notes.txt", io.BytesIO(b"Meeting notes content."), "text/plain")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["sourceType"] == "document"
    assert data["contentLength"] > 0

    src = db.query(SalonSource).first()
    assert src.source_filename == "notes.txt"
    assert src.source_content == "Meeting notes content."


# ─── Multiple sources per salon ────────────────────────────────────────────

@patch(
    "src.routers.salons.content_service.fetch_url_document",
    new_callable=AsyncMock,
    return_value=("content", {"article_date": "", "author": "", "publisher": ""}),
)
def test_multiple_sources_accumulate(mock_content, client, host, active_salon, db):
    _, token = host
    headers = {"Authorization": f"Bearer {token}"}
    urls = ["https://example.com/a", "https://example.com/b"]
    for url in urls:
        resp = client.post(
            f"/salons/{active_salon.id}/sources",
            data={"source_url": url},
            headers=headers,
        )
        assert resp.status_code == 201

    assert db.query(SalonSource).filter_by(salon_id=active_salon.id).count() == 2
