"""Tests for Story 4.2 — Accurate metering of conversation time.

Prepaid since the Epic 8 cutover: the heartbeat is the tick, so it charges what elapsed and
closes the Salon when the balance cannot cover what comes next. The host fixture therefore
has a balance — a host without one is a real and separate case, tested at the bottom, and
building every fixture that way would have every test here also testing exhaustion.
"""
from datetime import datetime, timedelta, timezone

import pytest

from src.credit import Tier
from src.ending import GUEST_NOTICE_SECONDS
from src.ledger import EventType, Pool, append
from src.models.salon import Salon
from src.models.user import User
from src.services.jwt_service import issue_token


# ─── Fixtures ────────────────────────────────────────────────────────────────

def _fund(db, user, cents):
    """Put paid balance on somebody, through the stream like everything else."""
    append(
        db,
        type=EventType.RECHARGED,
        subject_id=user.id,
        amount_cents=cents,
        pool=Pool.PAID,
    )
    db.commit()


@pytest.fixture
def host(db):
    u = User(email="15148880010@example.com", phone_number="+15148880010")
    db.add(u)
    db.commit()
    db.refresh(u)
    # Ten dollars: enough that no test here runs out by accident, so a Salon that closes in
    # one of them closed for the reason that test is about.
    _fund(db, u, 1000)
    return u, issue_token(str(u.id))


@pytest.fixture
def penniless_host(db):
    """A host with no balance at all — the case the cutover creates."""
    u = User(email="15148880011@example.com", phone_number="+15148880011")
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

def test_heartbeat_reports_the_time_the_balance_buys(client, db, host):
    """What is left is money, not a clock.

    This used to assert a ten-minute cap. That cap is retired: how long somebody may talk
    depends on what they pay per hour, and one number could not mean both Base at 3.00 and
    Mode C at 22.50. `secondsRemaining` is now what the balance buys at the rate in force,
    which is the figure the agent needs to wind a conversation down.
    """
    host_user, token = host
    sess = _active_salon(db, host_user, "money-remaining")

    resp = client.post(
        f"/salons/{sess.id}/heartbeat",
        json={"seconds": 30},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["salonEnded"] is False
    # 998 cents left at Base (300/h) → 11976 s, far past the ten minutes this once allowed.
    assert body["secondsRemaining"] == 11976


def test_heartbeat_closes_a_salon_whose_balance_ran_out(client, db, host):
    """Server-side enforcement: the agent is not trusted to stop itself.

    A worker that keeps talking past what somebody can pay for would otherwise bill
    realtime voice against nothing, which is what the balance check exists to prevent.
    Age is no longer a reason to close — see the sweep for what catches abandonment.
    """
    host_user, token = host
    sess = _active_salon(db, host_user, "broke-hit")
    # Two cents: enough for this heartbeat, not enough for the block after it.
    _fund(db, host_user, -998)
    db.commit()

    resp = client.post(
        f"/salons/{sess.id}/heartbeat",
        json={"seconds": 30},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    # Closing, not closed: the guests are owed their fifteen seconds first.
    assert body["balanceExhausted"] is True
    assert body["salonEnded"] is False
    assert body["closingInSeconds"] == GUEST_NOTICE_SECONDS

    db.expire(sess)
    db.refresh(sess)
    assert sess.status == "active"
    assert sess.closing_at is not None


def test_heartbeat_on_a_closed_salon_is_refused_afterwards(client, db, host):
    """Once the deadline has passed and the Salon is actually closed, further heartbeats
    get the ordinary ended-salon refusal."""
    host_user, token = host
    sess = _active_salon(db, host_user, "broke-twice")
    _fund(db, host_user, -998)
    db.commit()
    headers = {"Authorization": f"Bearer {token}"}

    # First: schedules the close and speaks the notice.
    client.post(f"/salons/{sess.id}/heartbeat", json={"seconds": 30}, headers=headers)
    # Backdate the deadline rather than waiting fifteen real seconds for it.
    sess.closing_at = datetime.now(tz=timezone.utc) - timedelta(seconds=1)
    db.commit()
    second = client.post(f"/salons/{sess.id}/heartbeat", json={"seconds": 30}, headers=headers)
    assert second.json()["salonEnded"] is True

    third = client.post(f"/salons/{sess.id}/heartbeat", json={"seconds": 30}, headers=headers)
    assert third.status_code == 409


# ─── Prepaid metering (FR63), since the Epic 8 cutover ───────────────────────
#
# The heartbeat is the tick. Everything below is behaviour that did not exist while
# billing was post-paid: money comes off as the conversation happens, and running out
# ends it rather than accruing a debt.


def test_a_heartbeat_charges_the_balance_for_what_elapsed(client, db, host):
    """Thirty seconds of Base is 300 cents/hour × 30 / 3600 = 2 cents."""
    host_user, token = host

    resp = client.post(
        f"/salons/{_active_salon(db, host_user, 'charge').id}/heartbeat",
        json={"seconds": 30},
        headers={"Authorization": f"Bearer {token}"},
    )

    body = resp.json()
    assert body["chargedCents"] == 2
    assert body["balanceCents"] == 998


def test_the_host_tier_is_what_is_charged(client, db, host):
    """Not a flat rate. Mode C is 2250 cents/hour, so the same thirty seconds costs more."""
    host_user, token = host
    salon = _active_salon(db, host_user, "tier")
    salon.host_tier = Tier.MODE_C.value
    db.commit()

    resp = client.post(
        f"/salons/{salon.id}/heartbeat",
        json={"seconds": 30},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.json()["chargedCents"] == 18


def test_charges_accumulate_across_heartbeats(client, db, host):
    host_user, token = host
    salon = _active_salon(db, host_user, "accumulate")
    headers = {"Authorization": f"Bearer {token}"}

    for _ in range(3):
        resp = client.post(
            f"/salons/{salon.id}/heartbeat", json={"seconds": 30}, headers=headers
        )

    assert resp.json()["balanceCents"] == 994


def test_the_time_a_balance_buys_is_reported(client, db, host):
    """The number somebody actually wants. Ten dollars of Base is a little under 3 h 20."""
    host_user, token = host

    resp = client.post(
        f"/salons/{_active_salon(db, host_user, 'left').id}/heartbeat",
        json={"seconds": 30},
        headers={"Authorization": f"Bearer {token}"},
    )

    # 998 cents at 300/h → 11976 s.
    assert resp.json()["balanceSecondsRemaining"] == 11976


def test_a_salon_with_no_balance_behind_it_is_scheduled_to_close(client, db, penniless_host):
    """No consumption without coverage (FR63). Ending is the designed outcome — the
    alternative is a conversation carrying on while it accrues something nobody
    authorised. It ends after the notice, not during it."""
    host_user, token = penniless_host

    resp = client.post(
        f"/salons/{_active_salon(db, host_user, 'broke').id}/heartbeat",
        json={"seconds": 30},
        headers={"Authorization": f"Bearer {token}"},
    )

    body = resp.json()
    assert body["balanceExhausted"] is True
    assert body["closingInSeconds"] == GUEST_NOTICE_SECONDS
    assert body["chargedCents"] == 0


def test_age_alone_no_longer_closes_a_salon(client, db, host):
    """The retirement, asserted rather than assumed. An old Salon with money behind it and
    a heartbeat arriving is a conversation in progress — this used to be cut off at ten
    minutes regardless, which under prepaid billing meant cutting off somebody who had paid
    for three more hours."""
    from src.config import settings

    host_user, token = host
    salon = _active_salon(db, host_user, "old-but-funded")
    salon.created_at = datetime.now(tz=timezone.utc) - timedelta(seconds=99999)
    db.commit()

    body = client.post(
        f"/salons/{salon.id}/heartbeat",
        json={"seconds": 30},
        headers={"Authorization": f"Bearer {token}"},
    ).json()

    assert body["salonEnded"] is False
    assert body["balanceExhausted"] is False


def test_nothing_is_charged_for_a_heartbeat_reporting_no_time(client, db, host):
    """A zero-second heartbeat is a sign of life, not consumption."""
    host_user, token = host

    body = client.post(
        f"/salons/{_active_salon(db, host_user, 'zero').id}/heartbeat",
        json={"seconds": 0},
        headers={"Authorization": f"Bearer {token}"},
    ).json()

    assert body["chargedCents"] == 0
    assert body["balanceCents"] == 1000


# ─── The closing sequence (FR55) ─────────────────────────────────────────────


def test_guests_are_told_before_the_room_disappears(client, db, penniless_host):
    """Fifteen seconds, and the notice states the fact without the cause. Never the host,
    never a balance — somebody's financial situation does not become audible to the people
    they invited."""
    host_user, token = penniless_host

    body = client.post(
        f"/salons/{_active_salon(db, host_user, 'notice').id}/heartbeat",
        json={"seconds": 30},
        headers={"Authorization": f"Bearer {token}"},
    ).json()

    assert body["closingNotice"] == "The Salon will close in 15 seconds."
    assert "balance" not in body["closingNotice"].lower()
    assert host_user.email not in body["closingNotice"]


def test_the_closing_sequence_is_not_billed(client, db, host):
    """The one bounded exemption to "no consumption without coverage": announcing the end
    is the only thing a spent balance may still buy. Charging for it would mean billing
    somebody to be told they have run out."""
    host_user, token = host
    salon = _active_salon(db, host_user, "free-close")
    _fund(db, host_user, -998)
    db.commit()
    headers = {"Authorization": f"Bearer {token}"}

    client.post(f"/salons/{salon.id}/heartbeat", json={"seconds": 30}, headers=headers)
    during = client.post(
        f"/salons/{salon.id}/heartbeat", json={"seconds": 30}, headers=headers
    ).json()

    assert during["chargedCents"] == 0


def test_the_deadline_is_not_pushed_back_by_later_heartbeats(client, db, penniless_host):
    """Set once. A deadline that moved with every heartbeat would never arrive, and the
    Salon would sit fifteen seconds from closing for ever."""
    host_user, token = penniless_host
    salon = _active_salon(db, host_user, "deadline")
    headers = {"Authorization": f"Bearer {token}"}

    client.post(f"/salons/{salon.id}/heartbeat", json={"seconds": 30}, headers=headers)
    db.expire(salon)
    db.refresh(salon)
    first_deadline = salon.closing_at

    client.post(f"/salons/{salon.id}/heartbeat", json={"seconds": 30}, headers=headers)
    db.expire(salon)
    db.refresh(salon)

    assert salon.closing_at == first_deadline


def test_a_host_running_low_is_warned_while_there_is_still_time(client, db, host):
    """Warned at five minutes rather than three: the conversation of everybody they are
    hosting depends on their balance, so they need longer to decide."""
    host_user, token = host
    # 20 cents at Base (300/h) → 240 s, under the host's 300 s threshold and over the
    # participant's 180 s one.
    _fund(db, host_user, -980)
    db.commit()

    body = client.post(
        f"/salons/{_active_salon(db, host_user, 'warn').id}/heartbeat",
        json={"seconds": 30},
        headers={"Authorization": f"Bearer {token}"},
    ).json()

    assert body["balanceAlert"] is not None
    assert "close for you and for your" in body["balanceAlert"]


def test_the_warning_is_given_once_not_on_every_tick(client, db, host):
    """Somebody asked twelve times a minute stops hearing it."""
    host_user, token = host
    salon = _active_salon(db, host_user, "warn-once")
    _fund(db, host_user, -980)
    db.commit()
    headers = {"Authorization": f"Bearer {token}"}

    first = client.post(
        f"/salons/{salon.id}/heartbeat", json={"seconds": 5}, headers=headers
    ).json()
    second = client.post(
        f"/salons/{salon.id}/heartbeat", json={"seconds": 5}, headers=headers
    ).json()

    assert first["balanceAlert"] is not None
    assert second["balanceAlert"] is None


def test_a_comfortable_balance_is_not_warned_about(client, db, host):
    host_user, token = host

    body = client.post(
        f"/salons/{_active_salon(db, host_user, 'no-warn').id}/heartbeat",
        json={"seconds": 30},
        headers={"Authorization": f"Bearer {token}"},
    ).json()

    assert body["balanceAlert"] is None
