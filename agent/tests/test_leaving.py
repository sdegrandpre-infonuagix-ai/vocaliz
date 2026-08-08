"""Ending a salon and leaving it are two different things, and only the first happened.

Reported: the agent brings the salon to an end on inactivity or at the ten-minute cap, then
stays in the room. Every server path does delete the room, which disconnects everybody — but
`livekit_service.delete_room` swallows its own failures and only logs a warning, so the moment
leaving mattered most was the moment nothing made it happen.

Three things end a salon, and each has to end in departure: the exit flow calling end_salon,
the cap reported on a heartbeat, and the room disconnecting under the agent.
"""
import asyncio
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import agent as salon  # noqa: E402


def _agent(**kw):
    a = salon.SalonAgent(
        salon_id="sess-1", api_url="http://api.test", host_token="tok", **kw
    )
    departures = []
    a.set_departure(departures.append)
    return a, departures


def _http(status: int, body: dict | None = None):
    """Patch httpx.AsyncClient the way the heartbeat tests do."""
    resp = MagicMock()
    resp.status_code = status
    resp.json = MagicMock(return_value=body if body is not None else {})
    client = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    client.post = AsyncMock(return_value=resp)
    patcher = patch("httpx.AsyncClient")
    started = patcher.start()
    started.return_value = client
    return patcher


# ─── The plumbing ────────────────────────────────────────────────────────────

def test_an_agent_has_somewhere_to_go():
    a, _ = _agent()
    assert callable(a.leave)


def test_leaving_without_a_departure_set_does_not_raise():
    """A job context is only present in the entrypoint. Unit-constructed agents have none,
    and a missing exit must not become an exception inside a callback nobody awaits."""
    bare = salon.SalonAgent(salon_id="s", api_url="http://x", host_token="t")
    bare.leave("no context")  # must not raise


def test_leaving_twice_departs_once():
    """The cap, the exit flow and an empty room can all fire for one conversation, and
    shutting a job down twice would raise where nothing is listening."""
    a, departures = _agent()
    a.leave("first")
    a.leave("second")
    assert len(departures) == 1


def test_a_broken_departure_does_not_propagate():
    a, _ = _agent()

    def _explode(_reason):
        raise RuntimeError("shutdown refused")

    a.set_departure(_explode)
    a.leave("try anyway")  # must not raise


def test_leaving_stops_the_heartbeat():
    """Metering a conversation that is over would keep billing it."""
    a, _ = _agent()

    async def _run():
        a.start_heartbeat()
        assert a._heartbeat_task is not None
        a.leave("done")
        assert a._heartbeat_task is None

    asyncio.run(_run())


# ─── Ending the salon explicitly ───────────────────────────────────────────

def test_ending_the_salon_leaves_the_room():
    """The reported bug: the salon ends and the agent stays."""
    a, departures = _agent()
    patcher = _http(200)
    try:
        assert asyncio.run(a.end_salon()) == "salon_ended"
    finally:
        patcher.stop()
    assert len(departures) == 1


def test_a_salon_already_over_is_still_a_reason_to_leave():
    """409 means the cap, the host or a previous call got there first. The salon being over
    is precisely the case for leaving, so treating it as an error kept the agent seated."""
    a, departures = _agent()
    patcher = _http(409, {"detail": "This salon has already ended."})
    try:
        assert asyncio.run(a.end_salon()) == "salon_ended"
    finally:
        patcher.stop()
    assert len(departures) == 1


def test_a_network_failure_does_not_make_the_agent_leave():
    """Deliberate. An unreachable API says nothing about whether the conversation is over,
    and hanging up on people mid-sentence over a transient error is the worse mistake."""
    a, departures = _agent()
    with patch("httpx.AsyncClient", side_effect=RuntimeError("no network")):
        assert asyncio.run(a.end_salon()) == "error:network"
    assert departures == []


def test_a_server_error_does_not_make_the_agent_leave():
    a, departures = _agent()
    patcher = _http(500, {"detail": "boom"})
    try:
        assert asyncio.run(a.end_salon()).startswith("error:")
    finally:
        patcher.stop()
    assert departures == []


def test_no_salon_context_means_no_departure():
    a = salon.SalonAgent()
    departures = []
    a.set_departure(departures.append)
    assert asyncio.run(a.end_salon()) == "no_salon_context"
    assert departures == []


# ─── The cap, reported on a heartbeat ────────────────────────────────────────

def test_the_cap_reported_on_a_heartbeat_makes_the_agent_leave():
    """The API closes a salon that reached its cap and says so in the reply. That flag was
    ignored, so the only thing that could stop the agent was a room deletion that fails
    silently."""
    a, departures = _agent()
    patcher = _http(200, {"salonEnded": True, "secondsRemaining": 0})
    try:
        asyncio.run(a._send_heartbeat())
    finally:
        patcher.stop()
    assert len(departures) == 1


def test_a_heartbeat_with_time_left_does_not_end_anything():
    a, departures = _agent()
    patcher = _http(200, {"salonEnded": False, "secondsRemaining": 300})
    try:
        asyncio.run(a._send_heartbeat())
    finally:
        patcher.stop()
    assert departures == []
    assert not a._ending_announced


def test_the_ending_is_still_announced_before_the_cap():
    """Leaving must not have replaced the warning: a conversation cut off mid-sentence with
    no wind-down is the experience this announcement exists to prevent."""
    a, departures = _agent()
    a.salon = MagicMock()
    patcher = _http(200, {"salonEnded": False, "secondsRemaining": 5})
    try:
        asyncio.run(a._send_heartbeat())
    finally:
        patcher.stop()
    assert a._ending_announced
    assert departures == [], "warned, not gone"


def test_a_capped_salon_does_not_also_get_a_farewell_speech():
    """Once the API says the salon is over the room is already being torn down; generating
    a reply into it would be talking to nobody."""
    a, departures = _agent()
    a.salon = MagicMock()
    patcher = _http(200, {"salonEnded": True, "secondsRemaining": 0})
    try:
        asyncio.run(a._send_heartbeat())
    finally:
        patcher.stop()
    a.salon.generate_reply.assert_not_called()
    assert len(departures) == 1
