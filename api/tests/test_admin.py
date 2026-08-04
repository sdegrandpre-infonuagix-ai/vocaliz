"""Tests for the administration router — reading the participation records."""
from datetime import datetime, timedelta, timezone

import pytest

from src.config import settings
from src.models.salon_event import SalonEvent
from src.models.user import User
from src.services.jwt_service import issue_token

ADMIN_EMAIL = "s.degrandpre@vocaliz.net"
NOW = datetime(2026, 8, 2, 12, 0, tzinfo=timezone.utc)


def _user(db, email):
    u = User(email=email)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u, issue_token(str(u.id))


@pytest.fixture
def admin(db):
    return _user(db, ADMIN_EMAIL)


@pytest.fixture
def ordinary(db):
    return _user(db, "someone@example.com")


def _event(
    db, email, salon, *, user_type="host", entered=NOW, language=None, device="",
    identity=None,
):
    db.add(
        SalonEvent(
            # Stable per person by default, which is how a host behaves: they join every salon
            # as their own account UUID, so their salons aggregate into one entry. A test about
            # several identities — two anonymous guests, say — passes them explicitly.
            participant_identity=identity if identity is not None else email,
            email=email,
            user_type=user_type,
            salon_name=salon,
            entered_at=entered,
            first_spoken_language=language,
            device_type=device,
        )
    )
    db.commit()


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


# ─── Who may read this ────────────────────────────────────────────────────────

def test_participants_requires_a_token(client):
    """401 without a token, 403 with one that is not an admin's — the distinction matters."""
    assert client.get("/admin/participants").status_code == 401


def test_participants_rejects_a_non_admin_user(client, ordinary):
    """An authenticated user who is not on the list gets 403, not the data."""
    _, token = ordinary
    assert client.get("/admin/participants", headers=_auth(token)).status_code == 403


def test_participants_accepts_the_configured_admin(client, admin):
    _, token = admin
    assert client.get("/admin/participants", headers=_auth(token)).status_code == 200


def test_admin_match_ignores_case(client, db):
    """Mailboxes are case-insensitive in practice; a capitalised sign-in must still work."""
    _, token = _user(db, "S.Degrandpre@Vocaliz.NET")
    assert client.get("/admin/participants", headers=_auth(token)).status_code == 200


def test_a_user_with_no_email_is_not_an_admin(client, db):
    """Guards the blank-entry case: an empty admin_emails entry must not match nobody-ness."""
    original = settings.admin_emails
    settings.admin_emails = f"{ADMIN_EMAIL}, "  # trailing blank entry
    try:
        u = User(email="")
        db.add(u)
        db.commit()
        db.refresh(u)
        response = client.get("/admin/participants", headers=_auth(issue_token(str(u.id))))
        assert response.status_code == 403
    finally:
        settings.admin_emails = original


# ─── What it returns ──────────────────────────────────────────────────────────

def test_empty_table_returns_an_empty_list(client, admin):
    _, token = admin
    body = client.get("/admin/participants", headers=_auth(token)).json()
    assert body == {"total": 0, "returned": 0, "participants": []}


def test_emails_are_returned_in_clear(client, admin, db):
    """There is no column-level cipher, so the address comes back exactly as stored."""
    _, token = admin
    _event(db, "alice@example.com", "salon-a")
    body = client.get("/admin/participants", headers=_auth(token)).json()
    assert [p["email"] for p in body["participants"]] == ["alice@example.com"]


def test_one_person_in_several_salons_is_one_entry(client, admin, db):
    """Grouped by email: four participations by one person are one participant."""
    _, token = admin
    for i in range(4):
        _event(db, "alice@example.com", f"salon-{i}", entered=NOW + timedelta(minutes=i))
    body = client.get("/admin/participants", headers=_auth(token)).json()
    assert body["total"] == 1
    entry = body["participants"][0]
    assert entry["salonCount"] == 4
    assert entry["firstSeen"].startswith("2026-08-02T12:00")
    assert entry["lastSeen"].startswith("2026-08-02T12:03")


def test_both_roles_are_reported_for_the_same_person(client, admin, db):
    """Someone can host one salon and be a guest in another."""
    _, token = admin
    _event(db, "alice@example.com", "salon-a", user_type="host")
    _event(db, "alice@example.com", "salon-b", user_type="guest")
    body = client.get("/admin/participants", headers=_auth(token)).json()
    assert body["participants"][0]["userTypes"] == ["guest", "host"]


def test_languages_are_collected_and_nulls_dropped(client, admin, db):
    """A salon where nothing was heard must not surface as a null in the list."""
    _, token = admin
    _event(db, "alice@example.com", "salon-a", language="fr")
    _event(db, "alice@example.com", "salon-b", language="en")
    _event(db, "alice@example.com", "salon-c", language=None)
    body = client.get("/admin/participants", headers=_auth(token)).json()
    assert body["participants"][0]["languages"] == ["en", "fr"]


def test_most_recent_participant_comes_first(client, admin, db):
    _, token = admin
    _event(db, "old@example.com", "salon-a", entered=NOW)
    _event(db, "recent@example.com", "salon-b", entered=NOW + timedelta(hours=1))
    body = client.get("/admin/participants", headers=_auth(token)).json()
    assert [p["email"] for p in body["participants"]] == [
        "recent@example.com",
        "old@example.com",
    ]


# ─── Pagination ───────────────────────────────────────────────────────────────

def test_total_counts_everyone_while_returned_counts_the_page(client, admin, db):
    """A truncated answer must be visible as truncated, not read as the whole list."""
    _, token = admin
    for i in range(5):
        _event(db, f"p{i}@example.com", f"salon-{i}", entered=NOW + timedelta(minutes=i))
    body = client.get("/admin/participants?limit=2", headers=_auth(token)).json()
    assert body["total"] == 5
    assert body["returned"] == 2
    assert len(body["participants"]) == 2


def test_offset_walks_the_list(client, admin, db):
    _, token = admin
    for i in range(3):
        _event(db, f"p{i}@example.com", f"salon-{i}", entered=NOW + timedelta(minutes=i))
    page = client.get("/admin/participants?limit=1&offset=1", headers=_auth(token)).json()
    assert [p["email"] for p in page["participants"]] == ["p1@example.com"]


def test_limit_is_bounded(client, admin):
    """No caller can ask for an unbounded export in one request."""
    _, token = admin
    assert client.get("/admin/participants?limit=5000", headers=_auth(token)).status_code == 422


# ─── Devices ─────────────────────────────────────────────────────────────────

def test_devices_are_collected_across_salons(client, admin, db):
    """Hosting from a laptop and joining from a phone are both true of the same person, so this
    is a list and not the most recent one."""
    _, token = admin
    _event(db, "alice@example.com", "salon-a", device="mac")
    _event(db, "alice@example.com", "salon-b", device="iphone")
    body = client.get("/admin/participants", headers=_auth(token)).json()
    assert body["participants"][0]["devices"] == ["iphone", "mac"]


def test_a_participation_with_no_device_adds_nothing(client, admin, db):
    """Somebody who joined by telephone has no device in this sense, and a blank must not
    surface as an empty entry in the list."""
    _, token = admin
    _event(db, "alice@example.com", "salon-a", device="windows")
    _event(db, "alice@example.com", "salon-b", device="")
    body = client.get("/admin/participants", headers=_auth(token)).json()
    assert body["participants"][0]["devices"] == ["windows"]


def test_a_person_seen_on_one_device_twice_lists_it_once(client, admin, db):
    _, token = admin
    _event(db, "alice@example.com", "salon-a", device="ipad")
    _event(db, "alice@example.com", "salon-b", device="ipad")
    body = client.get("/admin/participants", headers=_auth(token)).json()
    assert body["participants"][0]["devices"] == ["ipad"]


def test_devices_are_absent_rather_than_missing_for_older_rows(client, admin, db):
    """Everything recorded before the column existed reads as empty, and the field is still
    present so a caller never has to test for its absence."""
    _, token = admin
    _event(db, "alice@example.com", "salon-a")
    body = client.get("/admin/participants", headers=_auth(token)).json()
    assert body["participants"][0]["devices"] == []


# ─── Grouped on the identity, not on the contact ─────────────────────────────

def test_two_anonymous_guests_are_two_entries(client, admin, db):
    """The defect this grouping fixes. Both have no address and no number, so grouping on
    contact details folded every anonymous guest in the system into one line labelled with
    nothing — and the more of them there were, the more wrong it got."""
    _, token = admin
    _event(db, "", "salon-a", identity="guest-aaa", user_type="guest")
    _event(db, "", "salon-b", identity="guest-bbb", user_type="guest")
    body = client.get("/admin/participants", headers=_auth(token)).json()
    assert body["total"] == 2
    assert {p["participantIdentity"] for p in body["participants"]} == {"guest-aaa", "guest-bbb"}


def test_the_identity_is_returned(client, admin, db):
    """Returned so one person's rows can be traced by reading rather than by deduction — which
    is how the duplicate identity in production had to be found."""
    _, token = admin
    _event(db, "alice@example.com", "salon-a", identity="acct-1")
    body = client.get("/admin/participants", headers=_auth(token)).json()
    assert body["participants"][0]["participantIdentity"] == "acct-1"


def test_the_total_counts_what_the_page_groups_on(client, admin, db):
    """Otherwise "returned of total" compares two different things and a truncated list looks
    complete, or a complete one looks truncated."""
    _, token = admin
    _event(db, "", "salon-a", identity="guest-1", user_type="guest")
    _event(db, "", "salon-b", identity="guest-2", user_type="guest")
    _event(db, "alice@example.com", "salon-c", identity="acct-1")
    body = client.get("/admin/participants", headers=_auth(token)).json()
    assert body["total"] == 3 == body["returned"]
