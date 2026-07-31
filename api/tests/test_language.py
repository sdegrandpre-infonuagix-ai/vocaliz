"""Tests for GET /me/profile and PATCH /me/language (Story 2.9)."""
import pytest

from src.models.user import User
from src.services.jwt_service import issue_token


@pytest.fixture
def user(db):
    u = User(email="15149990001@example.com", phone_number="+15149990001")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u, issue_token(str(u.id))


# ─── GET /me/profile ──────────────────────────────────────────────────────────

def test_get_profile_requires_auth(client):
    resp = client.get("/me/profile")
    assert resp.status_code == 401


def test_get_profile_returns_user_fields(client, user):
    u, token = user
    resp = client.get("/me/profile", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["userId"] == str(u.id)
    assert data["phoneNumber"] == u.phone_number
    assert data["detectedLanguage"] is None


def test_get_profile_returns_detected_language_when_set(client, db, user):
    u, token = user
    u.detected_language = "fr"
    db.commit()
    resp = client.get("/me/profile", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["detectedLanguage"] == "fr"


# ─── PATCH /me/language ───────────────────────────────────────────────────────

def test_patch_language_requires_auth(client):
    resp = client.patch("/me/language", json={"language": "fr"})
    assert resp.status_code == 401


def test_patch_language_sets_language(client, db, user):
    u, token = user
    resp = client.patch(
        "/me/language",
        json={"language": "fr"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["detectedLanguage"] == "fr"

    db.refresh(u)
    assert u.detected_language == "fr"


def test_patch_language_update_en(client, db, user):
    u, token = user
    resp = client.patch(
        "/me/language",
        json={"language": "en"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["detectedLanguage"] == "en"


def test_patch_language_rejects_invalid_code(client, user):
    _, token = user
    resp = client.patch(
        "/me/language",
        json={"language": "not a language code 123!!"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


def test_patch_language_accepts_bcp47_subtag(client, user):
    _, token = user
    resp = client.patch(
        "/me/language",
        json={"language": "en-CA"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["detectedLanguage"] == "en-ca"
