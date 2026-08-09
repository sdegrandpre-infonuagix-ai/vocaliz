"""Closing salons nobody has been heard from, whatever their age.

This runs because the alternative is not running at all in the most ordinary failure: a
host closes their laptop, or the agent worker dies. The salon then stayed active for good,
leaking an open salon, a reserved telephone code and a span of metered time never settled.

**Silence, not age.** This used to close salons past a ten-minute cap. That cap is retired:
a Salon now runs as long as its balance covers it, and how long that is depends on the mode
— closing on age would cut off somebody mid-sentence who had paid for three more hours.
What is left to catch is abandonment, and silence is what abandonment looks like.
"""
import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from src.config import settings
from src.models.invitation import Invitation
from src.models.salon_code import CodeAvailable
from src.models.salon import Salon
from src.models.user import User
from src.services import salon_code_service, salon_lifecycle


@pytest.fixture
def host(db):
    u = User(email="sweep@example.com")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _salon(db, host, *, silent_seconds: int, room="salon-sweep", status="active"):
    """A Salon last heard from `silent_seconds` ago.

    Written onto created_at and left without a heartbeat, which is the shape the sweep
    falls back to and the one a Salon opened but never joined actually has.
    """
    s = Salon(
        host_user_id=host.id,
        livekit_room_name=room,
        source_type="url",
        source_content="c",
        status=status,
        created_at=datetime.now(tz=timezone.utc) - timedelta(seconds=silent_seconds),
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def _sweep(db):
    with patch.object(
        salon_lifecycle.livekit_service, "delete_room", new_callable=AsyncMock
    ) as delete_room:
        closed = asyncio.run(salon_lifecycle.close_expired_salons(db))
    return closed, delete_room


# ─── What gets closed ─────────────────────────────────────────────────────────

def test_a_salon_past_the_cap_is_closed(db, host):
    salon = _salon(db, host, silent_seconds=settings.abandoned_salon_seconds + 60)
    closed, _ = _sweep(db)
    assert closed == [str(salon.id)]
    db.expire_all()
    assert db.get(Salon, salon.id).status == "ended"


def test_a_salon_inside_the_cap_is_left_alone(db, host):
    salon = _salon(db, host, silent_seconds=60)
    closed, _ = _sweep(db)
    assert closed == []
    db.expire_all()
    assert db.get(Salon, salon.id).status == "active"


def test_a_long_salon_still_being_heard_from_is_left_alone(db, host):
    """The reversal, and the reason for it. This used to assert the opposite — that age
    closed a Salon whether or not somebody had just spoken. Under prepaid billing that cut
    off a paying conversation mid-sentence, so what closes a Salon is now silence. An old
    Salon whose heartbeat arrived a second ago is a conversation in progress."""
    salon = _salon(db, host, silent_seconds=99999)
    salon.last_heartbeat_at = datetime.now(tz=timezone.utc)
    db.commit()

    closed, _ = _sweep(db)

    assert closed == []
    db.expire_all()
    assert db.get(Salon, salon.id).status == "active"


def test_an_already_ended_salon_is_not_touched_again(db, host):
    _salon(db, host, silent_seconds=99999, status="ended")
    closed, _ = _sweep(db)
    assert closed == []


def test_the_room_is_deleted_which_is_what_stops_the_agent(db, host):
    """Marking the row ended only settles the accounting; deleting the room is what
    actually silences a worker still talking into it."""
    salon = _salon(db, host, silent_seconds=settings.abandoned_salon_seconds + 1)
    _, delete_room = _sweep(db)
    delete_room.assert_awaited_once_with(salon.livekit_room_name)


# ─── What the leak actually cost ──────────────────────────────────────────────

def test_the_telephone_code_returns_to_the_pool(db, host):
    """The visible symptom of the leak: a code reserved for a conversation that is over."""
    salon = _salon(db, host, silent_seconds=settings.abandoned_salon_seconds + 1)
    code = salon_code_service.claim(db)
    db.add(
        Invitation(
            salon_id=salon.id,
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
    """A salon abandoned mid-conversation used to leave its span unbilled for good."""
    _salon(db, host, silent_seconds=settings.abandoned_salon_seconds + 1)
    _sweep(db)
    db.expire_all()
    assert db.get(User, host.id).trial_seconds_used > 0


# ─── Robustness of the sweep itself ───────────────────────────────────────────

def test_one_stubborn_salon_does_not_stop_the_others(db, host):
    """A sweep that aborts halfway is worse than no sweep: the remainder is silently
    skipped on every single run."""
    first = _salon(db, host, silent_seconds=settings.abandoned_salon_seconds + 10, room="salon-a")
    second = _salon(db, host, silent_seconds=settings.abandoned_salon_seconds + 20, room="salon-b")

    calls = {"n": 0}

    def _explode_once(salon, db_):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("accounting failed")
        return None

    with patch.object(salon_lifecycle, "finalize_salon", side_effect=_explode_once), \
         patch.object(salon_lifecycle.livekit_service, "delete_room", new_callable=AsyncMock):
        closed = asyncio.run(salon_lifecycle.close_expired_salons(db))

    assert len(closed) == 1, "the second salon was still reached"
    assert {first.id, second.id}


def test_a_sweep_with_nothing_to_do_is_not_an_error(db):
    closed, _ = _sweep(db)
    assert closed == []


# ─── Through the maintenance function ─────────────────────────────────────────

def test_the_handler_action_reports_what_it_closed(db, host):
    """EventBridge invokes this every five minutes; the count is how anyone knows it ran."""
    from src import migrate_handler

    _salon(db, host, silent_seconds=settings.abandoned_salon_seconds + 1)

    with patch.object(
        salon_lifecycle.livekit_service, "delete_room", new_callable=AsyncMock
    ), patch("src.database.SessionLocal", return_value=db), patch.object(db, "close"):
        result = migrate_handler.handler({"action": "sweep_salons"}, None)

    assert result["status"] == "ok"
    assert result["closed"] == 1


# ─── A call nobody answered ───────────────────────────────────────────────────
#
# Ringing the front desk opens a Salon and mails the desk an invitation. If nobody clicks it,
# the caller sits alone with an agent for the full ten-minute cap — realtime-model time billed
# for a call that was never picked up.

def _desk_call(db, *, age_seconds: int, answered: bool):
    """A Salon opened by the front page, with the desk's invitation in the given state."""
    from datetime import datetime, timedelta, timezone

    from src.config import settings as cfg
    from src.models.invitation import Invitation
    from src.models.salon import Salon
    from src.models.user import User

    desk = db.query(User).filter(User.email == cfg.front_desk_email).first()
    if desk is None:
        desk = User(email=cfg.front_desk_email)
        db.add(desk)
        db.commit()
        db.refresh(desk)

    born = datetime.now(tz=timezone.utc) - timedelta(seconds=age_seconds)
    salon = Salon(
        host_user_id=desk.id,
        livekit_room_name=f"salon-desk-{age_seconds}-{answered}",
        source_type="none",
        source_content="",
        status="active",
        created_at=born,
    )
    db.add(salon)
    db.commit()
    db.refresh(salon)

    db.add(
        Invitation(
            salon_id=salon.id,
            host_user_id=desk.id,
            guest_email=cfg.front_desk_email,
            guest_phone="",
            invitation_type="email_contact",
            join_token=f"tok-desk-{age_seconds}-{answered}",
            status="accepted" if answered else "pending",
            expires_at=datetime.now(tz=timezone.utc) + timedelta(hours=24),
        )
    )
    db.commit()
    return salon


@pytest.mark.asyncio
async def test_an_unanswered_call_is_given_up_on_before_the_cap(db):
    """Five minutes, not ten. Nobody clicked the link, so nobody is coming."""
    salon = _desk_call(db, age_seconds=settings.unanswered_call_seconds + 5, answered=False)
    with patch.object(
        salon_lifecycle.livekit_service, "delete_room", new_callable=AsyncMock
    ):
        closed = await salon_lifecycle.close_expired_salons(db)
    assert str(salon.id) in closed


@pytest.mark.asyncio
async def test_an_answered_call_is_not_given_up_on(db):
    """Somebody picked up. It is a conversation now, and it runs as long as the balance
    covers it — the five-minute rule above is about nobody arriving, not about duration.

    Heartbeating, because that is what an answered call that is still going actually does.
    Without one it would be closed by the abandonment rule instead, and rightly: a call
    picked up five minutes ago that has said nothing since is not in progress."""
    salon = _desk_call(db, age_seconds=settings.unanswered_call_seconds + 5, answered=True)
    salon.last_heartbeat_at = datetime.now(tz=timezone.utc)
    db.commit()
    with patch.object(
        salon_lifecycle.livekit_service, "delete_room", new_callable=AsyncMock
    ):
        closed = await salon_lifecycle.close_expired_salons(db)
    assert str(salon.id) not in closed


@pytest.mark.asyncio
async def test_a_call_still_ringing_is_left_alone(db):
    """Under five minutes is somebody who has not read their email yet."""
    salon = _desk_call(db, age_seconds=30, answered=False)
    with patch.object(
        salon_lifecycle.livekit_service, "delete_room", new_callable=AsyncMock
    ):
        closed = await salon_lifecycle.close_expired_salons(db)
    assert str(salon.id) not in closed


@pytest.mark.asyncio
async def test_a_salon_in_both_lists_is_closed_once(db):
    """Old enough for the cap and unanswered as well. Finalising twice would bill a salon
    that had already been settled."""
    salon = _desk_call(db, age_seconds=settings.abandoned_salon_seconds + 60, answered=False)
    with patch.object(
        salon_lifecycle.livekit_service, "delete_room", new_callable=AsyncMock
    ):
        closed = await salon_lifecycle.close_expired_salons(db)
    assert closed.count(str(salon.id)) == 1
