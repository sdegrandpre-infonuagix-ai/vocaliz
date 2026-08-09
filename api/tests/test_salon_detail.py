"""Tests for GET /salons/{salon_id} (Story 2.4)."""
import uuid

import pytest

from src.models.salon import Salon
from src.models.salon_source import SalonSource
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
def salon_with_content(db, host):
    host_user, _ = host
    sess = Salon(
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

def test_get_salon_requires_auth(client, salon_with_content):
    resp = client.get(f"/salons/{salon_with_content.id}")
    assert resp.status_code == 401


# ─── Ownership check ─────────────────────────────────────────────────────────

def test_get_salon_non_host_returns_404(client, db, salon_with_content):
    other = User(email="15148888888@example.com", phone_number="+15148888888")
    db.add(other)
    db.commit()
    db.refresh(other)
    token = issue_token(str(other.id))

    resp = client.get(f"/salons/{salon_with_content.id}", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 404


def test_get_salon_unknown_id_returns_404(client, host):
    _, token = host
    resp = client.get(f"/salons/{uuid.uuid4()}", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 404


# ─── Happy path ──────────────────────────────────────────────────────────────

def test_get_salon_returns_content(client, host, salon_with_content):
    _, token = host
    resp = client.get(
        f"/salons/{salon_with_content.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["salonId"] == str(salon_with_content.id)
    assert data["sourceContent"] == "This is the article text about a very interesting topic."
    assert data["sourceUrl"] == "https://example.com/article"
    assert data["sourceType"] == "url"
    assert data["status"] == "active"
    assert data["additionalSources"] == []


def test_get_salon_includes_additional_sources(client, host, salon_with_content, db):
    _, token = host
    extra = SalonSource(
        salon_id=salon_with_content.id,
        host_user_id=salon_with_content.host_user_id,
        source_type="document",
        source_content="Extra document content.",
    )
    db.add(extra)
    db.commit()

    resp = client.get(
        f"/salons/{salon_with_content.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    sources = resp.json()["additionalSources"]
    assert len(sources) == 1
    assert sources[0]["sourceType"] == "document"
    assert sources[0]["contentLength"] == len("Extra document content.")
    # Content is returned so the agent can introduce contrasting perspectives (Story 2.5)
    assert sources[0]["sourceContent"] == "Extra document content."


# ─── The interpreter's voice ───────────────────────────────────────────────────

def test_get_salon_reports_the_chosen_voice(client, host, salon_with_content, db):
    salon_with_content.agent_voice = "orion"
    db.commit()
    resp = client.get(
        f"/salons/{salon_with_content.id}",
        headers={"Authorization": f"Bearer {host[1]}"},
    )
    assert resp.json()["agentVoice"] == "orion"


def test_get_salon_reports_the_hosts_chosen_tier(client, host, salon_with_content, db):
    salon_with_content.host_tier = "Mode C"
    db.commit()
    resp = client.get(
        f"/salons/{salon_with_content.id}",
        headers={"Authorization": f"Bearer {host[1]}"},
    )
    assert resp.json()["hostTier"] == "Mode C"


def test_get_salon_defaults_the_tier_to_base(client, host, salon_with_content):
    resp = client.get(
        f"/salons/{salon_with_content.id}",
        headers={"Authorization": f"Bearer {host[1]}"},
    )
    assert resp.json()["hostTier"] == "Base"


def test_get_salon_defaults_the_voice_to_ara(client, host, salon_with_content):
    """Null on the row, not the literal string — so a Salon that never touched this
    setting stays visibly distinct from one that chose "ara" on purpose. The default is
    applied here, on the way out."""
    resp = client.get(
        f"/salons/{salon_with_content.id}",
        headers={"Authorization": f"Bearer {host[1]}"},
    )
    assert resp.json()["agentVoice"] == "ara"


def test_get_salon_additional_sources_include_url(client, host, salon_with_content, db):
    _, token = host
    extra = SalonSource(
        salon_id=salon_with_content.id,
        host_user_id=salon_with_content.host_user_id,
        source_type="url",
        source_url="https://example.com/contrast",
        source_content="A contrasting perspective.",
    )
    db.add(extra)
    db.commit()

    resp = client.get(
        f"/salons/{salon_with_content.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    src = resp.json()["additionalSources"][0]
    assert src["sourceUrl"] == "https://example.com/contrast"
    assert src["sourceContent"] == "A contrasting perspective."

