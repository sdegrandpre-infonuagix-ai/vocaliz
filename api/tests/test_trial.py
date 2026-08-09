"""What an account has, and what ending a Salon does to the usage counter.

The free trial hour this file was written for is retired (FR51 replaces FR19). What is left
of it is a counter that gates nothing, and a balance that does.
"""
import time
from datetime import datetime, timedelta, timezone

import pytest

from src.models.salon import Salon
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


def _active_salon(db, host_user, room_suffix=""):
    sess = Salon(
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


# ─── GET /me/balance ──────────────────────────────────────────────────────────
#
# This was /me/trial-status, and reported a free hour everybody got. There is no trial:
# usage is prepaid. A duration is no longer a property of the account either — it is a
# property of the account *and* the mode, which is why the minutes come per tier.


def test_balance_starts_at_the_welcome_credit(client, db):
    """Registering grants it, so somebody who has just signed up has five dollars."""
    from src.credit import WELCOME_CREDIT_CENTS
    from src.signup import register

    person = register(db, email="fresh@example.com")
    db.commit()

    body = client.get(
        "/me/balance", headers={"Authorization": f"Bearer {issue_token(str(person.id))}"}
    ).json()

    assert body["giftedCents"] == WELCOME_CREDIT_CENTS
    assert body["paidCents"] == 0
    assert body["totalCents"] == WELCOME_CREDIT_CENTS


def test_the_two_pools_are_named_rather_than_summed(client, db, host):
    """From a single number, "how much of this is yours?" has no answer — and that is the
    question a refund asks."""
    from src.ledger import EventType, Pool, append

    host_user, token = host
    append(
        db,
        type=EventType.RECHARGED,
        subject_id=host_user.id,
        amount_cents=250,
        pool=Pool.PAID,
    )
    db.commit()

    body = client.get("/me/balance", headers={"Authorization": f"Bearer {token}"}).json()

    assert body["paidCents"] == 250
    assert body["giftedCents"] == 0
    assert body["totalCents"] == 250


def test_what_it_buys_is_answered_per_tier(client, db, host):
    """The question somebody actually has. Ten dollars is 3 h 20 of Base and 26 minutes of
    Mode C, and one duration could not have meant both."""
    from src.ledger import EventType, Pool, append

    host_user, token = host
    append(
        db,
        type=EventType.RECHARGED,
        subject_id=host_user.id,
        amount_cents=1000,
        pool=Pool.PAID,
    )
    db.commit()

    minutes = client.get(
        "/me/balance", headers={"Authorization": f"Bearer {token}"}
    ).json()["minutesByTier"]

    assert minutes["Base"] == 200
    assert minutes["Mode C"] == 26


def test_seconds_used_is_reported_but_gates_nothing(client, db, host):
    """Kept as a usage counter — the participant report answers questions with it — and no
    longer a limit anybody runs into."""
    host_user, token = host
    host_user.trial_seconds_used = 9999
    db.commit()

    body = client.get("/me/balance", headers={"Authorization": f"Bearer {token}"}).json()

    assert body["secondsUsed"] == 9999


def test_balance_requires_auth(client):
    assert client.get("/me/balance").status_code == 401


# ─── end_salon increments trial time ───────────────────────────────────────

def test_end_salon_increments_host_trial_time(client, db, host):
    """Ending a salon adds its duration to the host's trial_seconds_used."""
    host_user, token = host
    sess = _active_salon(db, host_user)

    # Backdate created_at so the salon has a ~60 s duration when ended
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


def test_end_salon_guest_time_never_counted(client, db, host):
    """Guest role never accumulates trial time — only the host's counter grows."""
    host_user, token = host
    other_guest = User(email="15148889999@example.com", phone_number="+15148889999")
    db.add(other_guest)
    db.commit()
    db.refresh(other_guest)

    assert other_guest.trial_seconds_used == 0

    sess = _active_salon(db, host_user)
    sess.created_at = datetime.now(tz=timezone.utc) - timedelta(seconds=30)
    db.commit()
    client.post(
        f"/salons/{sess.id}/end",
        headers={"Authorization": f"Bearer {token}"},
    )

    db.expire(other_guest)
    db.refresh(other_guest)
    assert other_guest.trial_seconds_used == 0


def test_end_salon_accumulates_across_multiple_salons(client, db, host):
    """Trial time is cumulative across multiple salons."""
    host_user, token = host

    for i in range(3):
        sess = _active_salon(db, host_user, room_suffix=str(i))
        sess.created_at = datetime.now(tz=timezone.utc) - timedelta(seconds=30)
        db.commit()
        client.post(f"/salons/{sess.id}/end", headers={"Authorization": f"Bearer {token}"})

    db.expire(host_user)
    db.refresh(host_user)
    assert host_user.trial_seconds_used >= 90


# ─── Abandoned salons must not be billed ───────────────────────────────────

def test_end_salon_clamps_gap_since_last_heartbeat(client, db):
    """A salon abandoned without heartbeats bills the grace window, not the whole gap.

    Closing the laptop stops the heartbeats but leaves the salon active. Without the
    clamp, ending it later would charge the host for every hour in between.
    """
    from datetime import datetime, timedelta, timezone
    from src.config import settings
    from src.models.salon import Salon
    from src.models.user import User
    from src.services.jwt_service import issue_token

    host = User(email="abandoned@example.com")
    db.add(host)
    db.commit()
    db.refresh(host)

    # Last sign of life four hours ago.
    stale = datetime.now(tz=timezone.utc) - timedelta(hours=4)
    sess = Salon(
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
        f"/salons/{sess.id}/end",
        headers={"Authorization": f"Bearer {issue_token(str(host.id))}"},
    )
    assert resp.status_code == 200

    db.expire(host)
    db.refresh(host)
    assert host.trial_seconds_used == settings.metering_grace_seconds
    assert host.trial_seconds_used < 4 * 3600


def test_end_salon_bills_full_span_within_grace(client, db):
    """A normally-ended salon is unaffected: its gap is under the grace window."""
    from datetime import datetime, timedelta, timezone
    from src.models.salon import Salon
    from src.models.user import User
    from src.services.jwt_service import issue_token

    host = User(email="normal@example.com")
    db.add(host)
    db.commit()
    db.refresh(host)

    recent = datetime.now(tz=timezone.utc) - timedelta(seconds=20)
    sess = Salon(
        host_user_id=host.id,
        livekit_room_name="salon-normal",
        source_type="none",
        status="active",
        last_heartbeat_at=recent,
    )
    db.add(sess)
    db.commit()

    client.post(
        f"/salons/{sess.id}/end",
        headers={"Authorization": f"Bearer {issue_token(str(host.id))}"},
    )
    db.expire(host)
    db.refresh(host)
    assert 18 <= host.trial_seconds_used <= 25
