"""The host's two controls over the voice agent, exercised as real requests.

These exist because of what they failed to catch. The endpoints were written, reviewed, and
deployed with a NameError on their first line: `_host_salon` called `uuid.UUID` in a module
that imports uuid inside each function instead, so every request died at 500 — the pause, and
the removal that showed its confirmation dialog and then quietly did nothing.

Five hundred and eighteen tests passed. None of them sent a request to either endpoint. That is
the gap being closed here: a handler that is never called is a handler nobody has run.
"""
import uuid
from unittest.mock import AsyncMock, patch

import pytest

from src.models.salon import Salon
from src.models.user import User
from src.services.jwt_service import issue_token


@pytest.fixture
def host(db):
    u = User(email="agenthost@example.com")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u, issue_token(str(u.id))


@pytest.fixture
def salon(db, host):
    host_user, _ = host
    s = Salon(
        host_user_id=host_user.id,
        livekit_room_name="salon-agent-controls",
        source_type="url",
        source_url="https://example.com",
        source_content="c",
        status="active",
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


# ─── Reading the state ───────────────────────────────────────────────────────

def test_the_state_can_be_read(client, salon, host):
    """The request that never happened. It is what would have surfaced the NameError."""
    _, token = host
    with patch(
        "src.services.livekit_service.agent_is_present", new_callable=AsyncMock
    ) as present:
        present.return_value = True
        resp = client.get(f"/salons/{salon.id}/agent", headers=_auth(token))
    assert resp.status_code == 200
    # Listening. A Salon starts that way: pausing is a control the host may reach for, not a
    # gate they must open first.
    assert resp.json() == {"present": True, "muted": False}


def test_a_new_salon_starts_with_its_agent_listening(db, host):
    """Tried the other way for an afternoon and reversed. A Salon that says nothing until
    somebody finds a button reads as broken, and finding the button was the first thing every
    new host had to do."""
    from src.models.salon import Salon

    host_user, _ = host
    fresh = Salon(
        host_user_id=host_user.id,
        livekit_room_name="salon-fresh",
        source_type="url",
        source_content="c",
        status="active",
    )
    db.add(fresh)
    db.commit()
    db.refresh(fresh)
    assert fresh.agent_muted is False


def test_the_detail_reports_the_pause_so_the_agent_can_read_it(client, salon, host):
    """Still read at start-up, because an agent can join a Salon its host has since paused —
    a restarted job, or one removed and brought back. Rejoining that room talking would undo
    the pause without anybody asking."""
    _, token = host
    resp = client.get(f"/salons/{salon.id}", headers=_auth(token))
    assert resp.status_code == 200
    assert resp.json()["agentMuted"] is False


def test_presence_comes_from_livekit_not_from_a_column(client, salon, host):
    """An agent can leave for reasons nothing here initiated, so presence is asked of the room
    rather than remembered. This proves the endpoint actually consults it."""
    _, token = host
    with patch(
        "src.services.livekit_service.agent_is_present", new_callable=AsyncMock
    ) as present:
        present.return_value = False
        body = client.get(f"/salons/{salon.id}/agent", headers=_auth(token)).json()
    assert body["present"] is False


def test_an_unparseable_id_is_not_found_rather_than_a_crash(client, host):
    """The exact shape of the bug: a bad id used to reach uuid.UUID and take the process with
    it. It has to answer 404."""
    _, token = host
    assert client.get("/salons/not-a-uuid/agent", headers=_auth(token)).status_code == 404


# ─── Pausing ─────────────────────────────────────────────────────────────────

def test_pausing_records_it_and_tells_the_room(client, salon, host, db):
    _, token = host
    with patch(
        "src.services.livekit_service.notify_room", new_callable=AsyncMock
    ) as notify:
        resp = client.post(
            f"/salons/{salon.id}/agent/mute",
            json={"muted": True},
            headers=_auth(token),
        )
    assert resp.status_code == 200
    assert resp.json()["muted"] is True
    db.refresh(salon)
    assert salon.agent_muted is True
    # The agent does the muting itself: only it can stop its own input, and silencing its
    # published track from here would leave it listening.
    notify.assert_awaited_once_with(
        salon.livekit_room_name, {"action": "agent_mute", "muted": True}
    )


def test_resuming_clears_it(client, salon, host, db):
    _, token = host
    with patch("src.services.livekit_service.notify_room", new_callable=AsyncMock):
        client.post(
            f"/salons/{salon.id}/agent/mute", json={"muted": True}, headers=_auth(token)
        )
        client.post(
            f"/salons/{salon.id}/agent/mute", json={"muted": False}, headers=_auth(token)
        )
    db.refresh(salon)
    assert salon.agent_muted is False


def test_a_paused_agent_is_still_reported_as_present(client, salon, host):
    """Paused and gone are different states, and the two buttons undo them differently."""
    _, token = host
    with patch("src.services.livekit_service.notify_room", new_callable=AsyncMock):
        client.post(
            f"/salons/{salon.id}/agent/mute", json={"muted": True}, headers=_auth(token)
        )
    with patch(
        "src.services.livekit_service.agent_is_present", new_callable=AsyncMock
    ) as present:
        present.return_value = True
        body = client.get(f"/salons/{salon.id}/agent", headers=_auth(token)).json()
    assert body == {"present": True, "muted": True}


# ─── Removing and bringing one back ──────────────────────────────────────────

def test_removing_takes_the_agent_out(client, salon, host):
    """The button that showed its warning and then did nothing."""
    _, token = host
    with patch(
        "src.services.livekit_service.remove_agent", new_callable=AsyncMock
    ) as remove:
        remove.return_value = True
        resp = client.post(f"/salons/{salon.id}/agent/disconnect", headers=_auth(token))
    assert resp.status_code == 200
    assert resp.json() == {"present": False, "muted": False}
    remove.assert_awaited_once_with(salon.livekit_room_name)


def test_removing_clears_the_pause(client, salon, host, db):
    """A removed agent is not a paused one. Leaving the flag set would bring the next agent
    back already silent, which is not what the host asked for."""
    _, token = host
    with patch("src.services.livekit_service.notify_room", new_callable=AsyncMock):
        client.post(
            f"/salons/{salon.id}/agent/mute", json={"muted": True}, headers=_auth(token)
        )
    with patch("src.services.livekit_service.remove_agent", new_callable=AsyncMock):
        client.post(f"/salons/{salon.id}/agent/disconnect", headers=_auth(token))
    db.refresh(salon)
    assert salon.agent_muted is False


def test_bringing_one_back_dispatches_a_fresh_agent(client, salon, host):
    _, token = host
    with patch(
        "src.services.livekit_service.dispatch_agent", new_callable=AsyncMock
    ) as dispatch:
        resp = client.post(f"/salons/{salon.id}/agent/connect", headers=_auth(token))
    assert resp.status_code == 200
    assert resp.json() == {"present": True, "muted": False}
    dispatch.assert_awaited_once()
    assert dispatch.await_args.args[0] == salon.livekit_room_name


def test_a_closed_salon_takes_no_new_agent(client, salon, host, db):
    _, token = host
    salon.status = "ended"
    db.commit()
    with patch("src.services.livekit_service.dispatch_agent", new_callable=AsyncMock):
        resp = client.post(f"/salons/{salon.id}/agent/connect", headers=_auth(token))
    assert resp.status_code == 409


# ─── Who may do any of this ──────────────────────────────────────────────────

@pytest.mark.parametrize(
    "path,method",
    [
        ("/agent", "get"),
        ("/agent/disconnect", "post"),
        ("/agent/connect", "post"),
    ],
)
def test_a_stranger_is_refused(client, salon, path, method):
    resp = getattr(client, method)(f"/salons/{salon.id}{path}")
    assert resp.status_code in (401, 403)


def test_another_host_cannot_touch_this_agent(client, salon, db):
    """The agent belongs to somebody's conversation, not to anybody who knows the id."""
    other = User(email="other-host@example.com")
    db.add(other)
    db.commit()
    db.refresh(other)
    with patch("src.services.livekit_service.remove_agent", new_callable=AsyncMock) as remove:
        resp = client.post(
            f"/salons/{salon.id}/agent/disconnect",
            headers=_auth(issue_token(str(other.id))),
        )
    assert resp.status_code == 404
    remove.assert_not_awaited()


def test_an_unknown_salon_is_not_found(client, host):
    _, token = host
    resp = client.get(f"/salons/{uuid.uuid4()}/agent", headers=_auth(token))
    assert resp.status_code == 404
