"""Closing sessions that outlived their cap, whatever their heartbeats say.

The cap used to be evaluated only when a heartbeat arrived, which meant it was not
evaluated at all in the most ordinary failure: a host closes their laptop, or the agent
worker dies. The session then stayed active for good, leaking an open session, a reserved
telephone code and a span of metered time never settled.
"""
import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from src.config import settings
from src.models.invitation import Invitation
from src.models.salon_code import CodeAvailable
from src.models.session import SessionModel
from src.models.user import User
from src.services import salon_code_service, session_lifecycle


@pytest.fixture
def host(db):
    u = User(email="sweep@example.com")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _session(db, host, *, age_seconds: int, room="salon-sweep", status="active"):
    s = SessionModel(
        host_user_id=host.id,
        livekit_room_name=room,
        source_type="url",
        source_content="c",
        status=status,
        created_at=datetime.now(tz=timezone.utc) - timedelta(seconds=age_seconds),
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def _sweep(db):
    with patch.object(
        session_lifecycle.livekit_service, "delete_room", new_callable=AsyncMock
    ) as delete_room:
        closed = asyncio.run(session_lifecycle.close_expired_sessions(db))
    return closed, delete_room


# ─── What gets closed ─────────────────────────────────────────────────────────

def test_a_session_past_the_cap_is_closed(db, host):
    session = _session(db, host, age_seconds=settings.max_session_seconds + 60)
    closed, _ = _sweep(db)
    assert closed == [str(session.id)]
    db.expire_all()
    assert db.get(SessionModel, session.id).status == "ended"


def test_a_session_inside_the_cap_is_left_alone(db, host):
    session = _session(db, host, age_seconds=60)
    closed, _ = _sweep(db)
    assert closed == []
    db.expire_all()
    assert db.get(SessionModel, session.id).status == "active"


def test_heartbeats_are_irrelevant(db, host):
    """Driven by age, not by silence. A session running eleven minutes is over whether or
    not somebody was talking a second ago — and the whole point is that no heartbeat is
    arriving at all."""
    session = _session(db, host, age_seconds=settings.max_session_seconds + 5)
    session.last_heartbeat_at = datetime.now(tz=timezone.utc)
    db.commit()
    closed, _ = _sweep(db)
    assert closed == [str(session.id)]


def test_an_already_ended_session_is_not_touched_again(db, host):
    _session(db, host, age_seconds=99999, status="ended")
    closed, _ = _sweep(db)
    assert closed == []


def test_the_room_is_deleted_which_is_what_stops_the_agent(db, host):
    """Marking the row ended only settles the accounting; deleting the room is what
    actually silences a worker still talking into it."""
    session = _session(db, host, age_seconds=settings.max_session_seconds + 1)
    _, delete_room = _sweep(db)
    delete_room.assert_awaited_once_with(session.livekit_room_name)


# ─── What the leak actually cost ──────────────────────────────────────────────

def test_the_telephone_code_returns_to_the_pool(db, host):
    """The visible symptom of the leak: a code reserved for a conversation that is over."""
    session = _session(db, host, age_seconds=settings.max_session_seconds + 1)
    code = salon_code_service.claim(db)
    db.add(
        Invitation(
            session_id=session.id,
            host_user_id=host.id,
            guest_email="guest@example.com",
            guest_phone="",
            invitation_type="email_contact",
            join_token="tok-sweep",
            phone_pin=code,
            status="pending",
            expires_at=datetime.now(tz=timezone.utc) + timedelta(hours=24),
        )
    )
    db.commit()

    _sweep(db)
    db.expire_all()
    assert db.get(CodeAvailable, code).available is True


def test_metered_time_is_settled(db, host):
    """A session abandoned mid-conversation used to leave its span unbilled for good."""
    _session(db, host, age_seconds=settings.max_session_seconds + 1)
    _sweep(db)
    db.expire_all()
    assert db.get(User, host.id).trial_seconds_used > 0


# ─── Robustness of the sweep itself ───────────────────────────────────────────

def test_one_stubborn_session_does_not_stop_the_others(db, host):
    """A sweep that aborts halfway is worse than no sweep: the remainder is silently
    skipped on every single run."""
    first = _session(db, host, age_seconds=settings.max_session_seconds + 10, room="salon-a")
    second = _session(db, host, age_seconds=settings.max_session_seconds + 20, room="salon-b")

    calls = {"n": 0}

    def _explode_once(session, db_):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("accounting failed")
        return None

    with patch.object(session_lifecycle, "finalize_session", side_effect=_explode_once), \
         patch.object(session_lifecycle.livekit_service, "delete_room", new_callable=AsyncMock):
        closed = asyncio.run(session_lifecycle.close_expired_sessions(db))

    assert len(closed) == 1, "the second session was still reached"
    assert {first.id, second.id}


def test_a_sweep_with_nothing_to_do_is_not_an_error(db):
    closed, _ = _sweep(db)
    assert closed == []


# ─── Through the maintenance function ─────────────────────────────────────────

def test_the_handler_action_reports_what_it_closed(db, host):
    """EventBridge invokes this every five minutes; the count is how anyone knows it ran."""
    from src import migrate_handler

    _session(db, host, age_seconds=settings.max_session_seconds + 1)

    with patch.object(
        session_lifecycle.livekit_service, "delete_room", new_callable=AsyncMock
    ), patch("src.database.SessionLocal", return_value=db), patch.object(db, "close"):
        result = migrate_handler.handler({"action": "sweep_sessions"}, None)

    assert result["status"] == "ok"
    assert result["closed"] == 1
