"""Tests for Story 5.1 — Consultation de l'Historique de Salons.

A registered user sees a simple list of their past salons and partners,
as host or as an accepted guest, with no detailed message thread.
"""
from datetime import datetime, timedelta, timezone

import pytest

from src.models.invitation import Invitation
from src.models.salon import Salon
from src.models.user import User
from src.services.jwt_service import issue_token


# ─── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def user(db):
    u = User(email="15145550001@example.com", phone_number="+15145550001")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u, issue_token(str(u.id))


def _salon(db, host, *, source_url="https://example.com/a", status="ended", offset_min=0):
    now = datetime.now(tz=timezone.utc)
    s = Salon(
        host_user_id=host.id,
        livekit_room_name=f"room-{host.phone_number[-4:]}-{offset_min}",
        source_type="url",
        source_url=source_url,
        source_content="content",
        status=status,
        created_at=now - timedelta(minutes=offset_min),
        ended_at=(now - timedelta(minutes=offset_min) + timedelta(minutes=5)) if status == "ended" else None,
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def _invite(db, salon, host, guest_phone, *, guest_user=None, status="accepted"):
    inv = Invitation(
        salon_id=salon.id,
        host_user_id=host.id,
        guest_email=guest_phone.lstrip("+") + "@example.com",
        guest_user_id=guest_user.id if guest_user else None,
        invitation_type="salon_friend" if guest_user else "email_contact",
        join_token=f"tok-{salon.livekit_room_name}-{guest_phone}",
        status=status,
        expires_at=datetime.now(tz=timezone.utc) + timedelta(days=1),
    )
    db.add(inv)
    db.commit()
    db.refresh(inv)
    return inv


# ─── Tests ───────────────────────────────────────────────────────────────────

def test_history_requires_auth(client):
    resp = client.get("/salons")
    assert resp.status_code == 401


def test_history_empty_for_new_user(client, user):
    _, token = user
    resp = client.get("/salons", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json() == {"salons": []}


def test_history_lists_host_salon_with_guest_partner(client, db, user):
    host, token = user
    salon = _salon(db, host, source_url="https://news.example/story")
    _invite(db, salon, host, "+15145559999")

    resp = client.get("/salons", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    salons = resp.json()["salons"]
    assert len(salons) == 1
    item = salons[0]
    assert item["salonId"] == str(salon.id)
    assert item["role"] == "host"
    assert item["sourceUrl"] == "https://news.example/story"
    assert item["status"] == "ended"
    assert item["endedAt"] is not None
    assert len(item["partners"]) == 1
    assert item["partners"][0]["email"] == "15145559999@example.com"


def test_history_uses_registered_guest_phone_over_invite_phone(client, db, user):
    """When the guest is a registered user, their account phone is shown."""
    host, token = user
    guest = User(email="15145558888@example.com", phone_number="+15145558888")
    db.add(guest)
    db.commit()
    db.refresh(guest)

    salon = _salon(db, host)
    # Invite records a (possibly stale) contact phone; guest_user_id links the account.
    _invite(db, salon, host, "+10000000000", guest_user=guest)

    resp = client.get("/salons", headers={"Authorization": f"Bearer {token}"})
    partner = resp.json()["salons"][0]["partners"][0]
    assert partner["userId"] == str(guest.id)
    assert partner["email"] == "15145558888@example.com"


def test_history_includes_salons_where_user_was_guest(client, db, user):
    """A user who joined someone else's salon as an accepted guest sees it."""
    me, token = user
    other_host = User(email="15145557777@example.com", phone_number="+15145557777")
    db.add(other_host)
    db.commit()
    db.refresh(other_host)

    salon = _salon(db, other_host, source_url="https://example.com/hosted")
    _invite(db, salon, other_host, me.phone_number, guest_user=me, status="accepted")

    resp = client.get("/salons", headers={"Authorization": f"Bearer {token}"})
    salons = resp.json()["salons"]
    assert len(salons) == 1
    assert salons[0]["role"] == "guest"
    assert salons[0]["partners"][0]["email"] == "15145557777@example.com"


def test_history_excludes_pending_guest_invitations(client, db, user):
    """A pending (never accepted) invitation does not appear in the guest's history."""
    me, token = user
    other_host = User(email="15145556666@example.com", phone_number="+15145556666")
    db.add(other_host)
    db.commit()
    db.refresh(other_host)

    salon = _salon(db, other_host)
    _invite(db, salon, other_host, me.phone_number, guest_user=me, status="pending")

    resp = client.get("/salons", headers={"Authorization": f"Bearer {token}"})
    assert resp.json()["salons"] == []


def test_history_sorted_most_recent_first(client, db, user):
    host, token = user
    older = _salon(db, host, offset_min=60)
    newer = _salon(db, host, offset_min=1)

    resp = client.get("/salons", headers={"Authorization": f"Bearer {token}"})
    ids = [s["salonId"] for s in resp.json()["salons"]]
    assert ids == [str(newer.id), str(older.id)]


def test_history_no_message_thread_field(client, db, user):
    """The summary must not expose any message/transcript content (AC: sans fil de messages)."""
    host, token = user
    salon = _salon(db, host)
    _invite(db, salon, host, "+15145550002")

    item = client.get("/salons", headers={"Authorization": f"Bearer {token}"}).json()["salons"][0]
    for forbidden in ("messages", "transcript", "sourceContent", "content"):
        assert forbidden not in item
