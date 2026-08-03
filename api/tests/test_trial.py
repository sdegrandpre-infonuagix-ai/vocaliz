"""Tests for Story 4.1 — One lifetime free trial hour per host."""
import time
from datetime import datetime, timedelta, timezone

import pytest

from src.models.session import SessionModel
from src.models.user import User
from src.services.jwt_service import issue_token


# ─── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def host(db):
    u = User(email="15148880001@example.com", phone_number="+15148880001")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u, issue_token(str(u.id))


def _active_session(db, host_user, room_suffix=""):
    sess = SessionModel(
        host_user_id=host_user.id,
        livekit_room_name=f"salon-trial-room{room_suffix}",
        source_type="url",
        source_content="content",
        status="active",
    )
    db.add(sess)
    db.commit()
    db.refresh(sess)
    return sess


# ─── GET /me/trial-status ─────────────────────────────────────────────────────

def test_trial_status_initial_values(client, host):
    """Fresh user has 0 seconds used, full 3600 remaining, not exhausted."""
    _, token = host
    resp = client.get("/me/trial-status", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["trialSecondsUsed"] == 0
    assert body["trialSecondsLimit"] == 3600
    assert body["trialSecondsRemaining"] == 3600
    assert body["trialExhausted"] is False


def test_trial_status_reflects_accumulated_time(client, db, host):
    """trial-status returns correct values after host accumulates some time."""
    host_user, token = host
    host_user.trial_seconds_used = 1800
    db.commit()

    resp = client.get("/me/trial-status", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["trialSecondsUsed"] == 1800
    assert body["trialSecondsRemaining"] == 1800
    assert body["trialExhausted"] is False


def test_trial_status_exhausted_when_at_limit(client, db, host):
    """trialExhausted becomes true when trial_seconds_used >= 3600."""
    host_user, token = host
    host_user.trial_seconds_used = 3600
    db.commit()

    resp = client.get("/me/trial-status", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["trialExhausted"] is True
    assert body["trialSecondsRemaining"] == 0


def test_trial_status_remaining_never_negative(client, db, host):
    """trialSecondsRemaining is always >= 0 even if usage exceeds limit."""
    host_user, token = host
    host_user.trial_seconds_used = 7200  # 2 hours
    db.commit()

    resp = client.get("/me/trial-status", headers={"Authorization": f"Bearer {token}"})
    body = resp.json()
    assert body["trialSecondsRemaining"] == 0
    assert body["trialExhausted"] is True


def test_trial_status_requires_auth(client):
    """Unauthenticated request is rejected."""
    resp = client.get("/me/trial-status")
    assert resp.status_code == 401


# ─── end_session increments trial time ───────────────────────────────────────

def test_end_session_increments_host_trial_time(client, db, host):
    """Ending a session adds its duration to the host's trial_seconds_used."""
    host_user, token = host
    sess = _active_session(db, host_user)

    # Backdate created_at so the session has a ~60 s duration when ended
    sess.created_at = datetime.now(tz=timezone.utc) - timedelta(seconds=60)
    db.commit()

    resp = client.post(
        f"/sessions/{sess.id}/end",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200

    db.expire(host_user)
    db.refresh(host_user)
    assert host_user.trial_seconds_used >= 60


def test_end_session_guest_time_never_counted(client, db, host):
    """Guest role never accumulates trial time — only the host's counter grows."""
    host_user, token = host
    other_guest = User(email="15148889999@example.com", phone_number="+15148889999")
    db.add(other_guest)
    db.commit()
    db.refresh(other_guest)

    assert other_guest.trial_seconds_used == 0

    sess = _active_session(db, host_user)
    sess.created_at = datetime.now(tz=timezone.utc) - timedelta(seconds=30)
    db.commit()
    client.post(
        f"/sessions/{sess.id}/end",
        headers={"Authorization": f"Bearer {token}"},
    )

    db.expire(other_guest)
    db.refresh(other_guest)
    assert other_guest.trial_seconds_used == 0


def test_end_session_accumulates_across_multiple_sessions(client, db, host):
    """Trial time is cumulative across multiple sessions."""
    host_user, token = host

    for i in range(3):
        sess = _active_session(db, host_user, room_suffix=str(i))
        sess.created_at = datetime.now(tz=timezone.utc) - timedelta(seconds=30)
        db.commit()
        client.post(f"/sessions/{sess.id}/end", headers={"Authorization": f"Bearer {token}"})

    db.expire(host_user)
    db.refresh(host_user)
    assert host_user.trial_seconds_used >= 90


# ─── Abandoned sessions must not be billed ───────────────────────────────────

def test_end_session_clamps_gap_since_last_heartbeat(client, db):
    """A session abandoned without heartbeats bills the grace window, not the whole gap.

    Closing the laptop stops the heartbeats but leaves the session active. Without the
    clamp, ending it later would charge the host for every hour in between.
    """
    from datetime import datetime, timedelta, timezone
    from src.config import settings
    from src.models.session import SessionModel
    from src.models.user import User
    from src.services.jwt_service import issue_token

    host = User(email="abandoned@example.com")
    db.add(host)
    db.commit()
    db.refresh(host)

    # Last sign of life four hours ago.
    stale = datetime.now(tz=timezone.utc) - timedelta(hours=4)
    sess = SessionModel(
        host_user_id=host.id,
        livekit_room_name="salon-abandoned",
        source_type="none",
        status="active",
        last_heartbeat_at=stale,
    )
    db.add(sess)
    db.commit()
    db.refresh(sess)

    resp = client.post(
        f"/sessions/{sess.id}/end",
        headers={"Authorization": f"Bearer {issue_token(str(host.id))}"},
    )
    assert resp.status_code == 200

    db.expire(host)
    db.refresh(host)
    assert host.trial_seconds_used == settings.metering_grace_seconds
    assert host.trial_seconds_used < 4 * 3600


def test_end_session_bills_full_span_within_grace(client, db):
    """A normally-ended session is unaffected: its gap is under the grace window."""
    from datetime import datetime, timedelta, timezone
    from src.models.session import SessionModel
    from src.models.user import User
    from src.services.jwt_service import issue_token

    host = User(email="normal@example.com")
    db.add(host)
    db.commit()
    db.refresh(host)

    recent = datetime.now(tz=timezone.utc) - timedelta(seconds=20)
    sess = SessionModel(
        host_user_id=host.id,
        livekit_room_name="salon-normal",
        source_type="none",
        status="active",
        last_heartbeat_at=recent,
    )
    db.add(sess)
    db.commit()

    client.post(
        f"/sessions/{sess.id}/end",
        headers={"Authorization": f"Bearer {issue_token(str(host.id))}"},
    )
    db.expire(host)
    db.refresh(host)
    assert 18 <= host.trial_seconds_used <= 25
