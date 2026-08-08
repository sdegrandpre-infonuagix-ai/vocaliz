"""Tests for Story 4.2 — Accurate metering of conversation time."""
from datetime import datetime, timedelta, timezone

import pytest

from src.models.salon import Salon
from src.models.user import User
from src.services.jwt_service import issue_token


# ─── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def host(db):
    u = User(email="15148880010@example.com", phone_number="+15148880010")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u, issue_token(str(u.id))


def _active_salon(db, host_user, room_suffix="hb"):
    sess = Salon(
        host_user_id=host_user.id,
        livekit_room_name=f"salon-hb-room-{room_suffix}",
        source_type="url",
        source_content="content",
        status="active",
    )
    db.add(sess)
    db.commit()
    db.refresh(sess)
    return sess


# ─── POST /salons/{id}/heartbeat ───────────────────────────────────────────

def test_heartbeat_returns_200_and_trial_seconds_used(client, db, host):
    """A valid heartbeat increments trial_seconds_used and returns the new total."""
    host_user, token = host
    sess = _active_salon(db, host_user)

    resp = client.post(
        f"/salons/{sess.id}/heartbeat",
        json={"seconds": 30},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["salonId"] == str(sess.id)
    assert body["trialSecondsUsed"] == 30


def test_heartbeat_increments_host_trial_seconds_used(client, db, host):
    """After a heartbeat, host.trial_seconds_used grows by the reported seconds."""
    host_user, token = host
    sess = _active_salon(db, host_user)

    client.post(
        f"/salons/{sess.id}/heartbeat",
        json={"seconds": 30},
        headers={"Authorization": f"Bearer {token}"},
    )

    db.expire(host_user)
    db.refresh(host_user)
    assert host_user.trial_seconds_used == 30


def test_heartbeat_sets_last_heartbeat_at(client, db, host):
    """A heartbeat updates salon.last_heartbeat_at."""
    host_user, token = host
    sess = _active_salon(db, host_user)
    assert sess.last_heartbeat_at is None

    client.post(
        f"/salons/{sess.id}/heartbeat",
        json={"seconds": 30},
        headers={"Authorization": f"Bearer {token}"},
    )

    db.expire(sess)
    db.refresh(sess)
    assert sess.last_heartbeat_at is not None


def test_heartbeat_accumulates_across_multiple_calls(client, db, host):
    """Multiple heartbeats accumulate into trial_seconds_used."""
    host_user, token = host
    sess = _active_salon(db, host_user)

    for _ in range(3):
        client.post(
            f"/salons/{sess.id}/heartbeat",
            json={"seconds": 30},
            headers={"Authorization": f"Bearer {token}"},
        )

    db.expire(host_user)
    db.refresh(host_user)
    assert host_user.trial_seconds_used == 90


def test_heartbeat_on_ended_salon_returns_409(client, db, host):
    """Heartbeat on a finished salon is rejected."""
    host_user, token = host
    sess = _active_salon(db, host_user)
    sess.status = "ended"
    db.commit()

    resp = client.post(
        f"/salons/{sess.id}/heartbeat",
        json={"seconds": 30},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 409


def test_heartbeat_requires_auth(client, db, host):
    """Unauthenticated heartbeat is rejected."""
    host_user, _ = host
    sess = _active_salon(db, host_user)

    resp = client.post(f"/salons/{sess.id}/heartbeat", json={"seconds": 30})
    assert resp.status_code == 401


def test_heartbeat_wrong_user_returns_404(client, db, host):
    """A heartbeat from a non-host user is rejected."""
    host_user, _ = host
    sess = _active_salon(db, host_user)

    other = User(email="15148880099@example.com", phone_number="+15148880099")
    db.add(other)
    db.commit()
    db.refresh(other)
    other_token = issue_token(str(other.id))

    resp = client.post(
        f"/salons/{sess.id}/heartbeat",
        json={"seconds": 30},
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert resp.status_code == 404


def test_heartbeat_unknown_salon_returns_404(client, host):
    """A heartbeat for a non-existent salon returns 404."""
    _, token = host
    fake_id = "00000000-0000-0000-0000-000000000000"

    resp = client.post(
        f"/salons/{fake_id}/heartbeat",
        json={"seconds": 30},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


# ─── end_salon uses last_heartbeat_at as reference ─────────────────────────

def test_end_salon_after_heartbeat_only_adds_remaining_time(client, db, host):
    """After heartbeats, end_salon only adds time since the last heartbeat."""
    host_user, token = host
    sess = _active_salon(db, host_user)

    # Simulate: heartbeats already covered 60 s
    host_user.trial_seconds_used = 60
    db.commit()

    # last_heartbeat_at is 10 seconds ago
    sess.last_heartbeat_at = datetime.now(tz=timezone.utc) - timedelta(seconds=10)
    db.commit()

    resp = client.post(
        f"/salons/{sess.id}/end",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200

    db.expire(host_user)
    db.refresh(host_user)
    # Should have added ~10 s (the gap since last heartbeat), not the full salon duration
    assert host_user.trial_seconds_used >= 60
    # Should not have added more than 30 extra seconds (last_heartbeat_at was only 10 s ago)
    assert host_user.trial_seconds_used < 90


def test_end_salon_without_heartbeats_falls_back_to_created_at(client, db, host):
    """When no heartbeats exist, end_salon counts the full salon duration from created_at."""
    host_user, token = host
    sess = _active_salon(db, host_user)

    # No heartbeats — backdate created_at by 60 s
    sess.created_at = datetime.now(tz=timezone.utc) - timedelta(seconds=60)
    db.commit()

    resp = client.post(
        f"/salons/{sess.id}/end",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200

    db.expire(host_user)
    db.refresh(host_user)
    assert host_user.trial_seconds_used >= 60


# ─── Per-salon cap ─────────────────────────────────────────────────────────

def test_heartbeat_reports_time_left_in_the_salon(client, db, host):
    """The cap is per salon, distinct from the account's trial hour."""
    from src.config import settings

    host_user, token = host
    sess = _active_salon(db, host_user, "cap-remaining")
    resp = client.post(
        f"/salons/{sess.id}/heartbeat",
        json={"seconds": 30},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["salonEnded"] is False
    # A salon created moments ago has very nearly the whole cap left.
    assert settings.max_salon_seconds - 5 <= body["secondsRemaining"] <= settings.max_salon_seconds


def test_heartbeat_closes_a_salon_that_reached_the_cap(client, db, host):
    """Server-side enforcement: the agent is not trusted to stop itself.

    A worker that crashes or loses its connection would otherwise leave the room open and
    billing, which is exactly what the cap exists to prevent.
    """
    from src.config import settings

    host_user, token = host
    sess = _active_salon(db, host_user, "cap-hit")
    # Backdate creation past the cap.
    sess.created_at = datetime.now(tz=timezone.utc) - timedelta(
        seconds=settings.max_salon_seconds + 60
    )
    db.commit()

    resp = client.post(
        f"/salons/{sess.id}/heartbeat",
        json={"seconds": 30},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["salonEnded"] is True
    assert body["secondsRemaining"] == 0

    db.expire(sess)
    db.refresh(sess)
    assert sess.status == "ended"
    assert sess.ended_at is not None


def test_heartbeat_on_a_capped_salon_is_refused_afterwards(client, db, host):
    """Once closed, further heartbeats get the ordinary ended-salon refusal."""
    from src.config import settings

    host_user, token = host
    sess = _active_salon(db, host_user, "cap-twice")
    sess.created_at = datetime.now(tz=timezone.utc) - timedelta(
        seconds=settings.max_salon_seconds + 60
    )
    db.commit()
    headers = {"Authorization": f"Bearer {token}"}

    client.post(f"/salons/{sess.id}/heartbeat", json={"seconds": 30}, headers=headers)
    second = client.post(f"/salons/{sess.id}/heartbeat", json={"seconds": 30}, headers=headers)
    assert second.status_code == 409
