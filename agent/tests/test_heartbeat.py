"""Tests for Story 4.2 — agent metering heartbeat loop."""
import asyncio
import os
import sys
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import agent as salon  # noqa: E402


# ─── SalonAgent has heartbeat infrastructure ──────────────────────────────────

def test_salon_agent_has_start_heartbeat():
    a = salon.SalonAgent()
    assert hasattr(a, "start_heartbeat")
    assert callable(a.start_heartbeat)


def test_salon_agent_has_stop_heartbeat():
    a = salon.SalonAgent()
    assert hasattr(a, "stop_heartbeat")
    assert callable(a.stop_heartbeat)


def test_salon_agent_has_send_heartbeat():
    a = salon.SalonAgent()
    assert hasattr(a, "_send_heartbeat")
    assert callable(a._send_heartbeat)


def test_salon_agent_heartbeat_interval_is_30():
    a = salon.SalonAgent()
    assert a._heartbeat_interval == 30


def test_salon_agent_heartbeat_task_starts_as_none():
    a = salon.SalonAgent()
    assert a._heartbeat_task is None


# ─── start_heartbeat / stop_heartbeat ────────────────────────────────────────

def test_start_heartbeat_creates_task():
    a = salon.SalonAgent(
        salon_id="sess-1",
        api_url="http://api",
        host_token="tok",
    )

    async def _run():
        a.start_heartbeat()
        try:
            assert a._heartbeat_task is not None
            assert not a._heartbeat_task.done()
        finally:
            a.stop_heartbeat()

    asyncio.run(_run())


def test_stop_heartbeat_cancels_task():
    a = salon.SalonAgent(
        salon_id="sess-1",
        api_url="http://api",
        host_token="tok",
    )

    async def _run():
        a.start_heartbeat()
        task = a._heartbeat_task
        a.stop_heartbeat()
        assert a._heartbeat_task is None
        # Give the event loop a tick so the task actually cancels
        await asyncio.sleep(0)
        assert task.cancelled() or task.done()

    asyncio.run(_run())


def test_start_heartbeat_idempotent():
    """Calling start_heartbeat twice does not create a second task."""
    a = salon.SalonAgent(
        salon_id="sess-1",
        api_url="http://api",
        host_token="tok",
    )

    async def _run():
        a.start_heartbeat()
        first_task = a._heartbeat_task
        a.start_heartbeat()
        assert a._heartbeat_task is first_task
        a.stop_heartbeat()

    asyncio.run(_run())


# ─── _send_heartbeat ─────────────────────────────────────────────────────────

def test_send_heartbeat_posts_correct_url_and_payload():
    a = salon.SalonAgent(
        salon_id="sess-abc",
        api_url="http://api.test",
        host_token="bearer-tok",
    )

    mock_resp = MagicMock()
    mock_resp.status_code = 200

    async def _run():
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.post = AsyncMock(return_value=mock_resp)
            mock_client_cls.return_value = mock_client

            await a._send_heartbeat()

            mock_client.post.assert_called_once_with(
                "http://api.test/salons/sess-abc/heartbeat",
                json={"seconds": 30},
                headers={"Authorization": "Bearer bearer-tok"},
            )

    asyncio.run(_run())


def test_send_heartbeat_no_op_without_salon_context():
    """_send_heartbeat silently skips when salon context is missing."""
    a = salon.SalonAgent()

    async def _run():
        with patch("httpx.AsyncClient") as mock_client_cls:
            await a._send_heartbeat()
            mock_client_cls.assert_not_called()

    asyncio.run(_run())


def test_send_heartbeat_swallows_network_errors():
    """A network failure during heartbeat does not raise."""
    a = salon.SalonAgent(
        salon_id="sess-x",
        api_url="http://api.test",
        host_token="tok",
    )

    async def _run():
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.post = AsyncMock(side_effect=Exception("network error"))
            mock_client_cls.return_value = mock_client

            # Should not raise
            await a._send_heartbeat()

    asyncio.run(_run())


def test_send_heartbeat_swallows_non_200_response():
    """A 4xx/5xx response from heartbeat does not raise."""
    a = salon.SalonAgent(
        salon_id="sess-y",
        api_url="http://api.test",
        host_token="tok",
    )

    mock_resp = MagicMock()
    mock_resp.status_code = 409

    async def _run():
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.post = AsyncMock(return_value=mock_resp)
            mock_client_cls.return_value = mock_client

            await a._send_heartbeat()  # Should not raise

    asyncio.run(_run())


# ─── Winding the conversation down before the cap ────────────────────────────

@pytest.fixture
def agent_with_session():
    """A SalonAgent whose AgentSession is observable.

    `session` is a read-only property on the real Agent base class — `RuntimeError` if the
    agent is not running — so it cannot be set like a plain attribute. This is exactly the
    shape of the bug this file once missed entirely: a test double named `salon` stood in
    for a property that has never existed under that name, so `self.salon.generate_reply(...)`
    in production raised `AttributeError` on every real call while every test here passed.
    Patched at the class level instead, for the fixture's lifetime only.
    """
    a = salon.SalonAgent()
    a._salon_id = "sess-1"
    mock_session = MagicMock()
    # create=True: the test stub for livekit.agents.Agent (see conftest.py) is a bare
    # object with no `session` at all, real property or otherwise — patch.object refuses
    # to patch an attribute that does not already exist unless told this is deliberate.
    with patch.object(
        salon.SalonAgent,
        "session",
        new_callable=PropertyMock,
        return_value=mock_session,
        create=True,
    ):
        yield a


def test_no_announcement_while_time_remains(agent_with_session):
    a = agent_with_session
    a._maybe_announce_ending(salon.ENDING_WARNING_SECONDS + 30)
    a.session.generate_reply.assert_not_called()
    assert a._ending_announced is False


def test_announces_when_the_cap_is_near(agent_with_session):
    a = agent_with_session
    a._maybe_announce_ending(salon.ENDING_WARNING_SECONDS - 5)
    a.session.generate_reply.assert_called_once()
    # Phrased as instructions so the model answers in the language being spoken, and told
    # not to blame a timer — the participants did not ask about our billing.
    instructions = a.session.generate_reply.call_args.kwargs["instructions"]
    assert "language of the conversation" in instructions
    assert "quotas" in instructions


def test_announces_only_once(agent_with_session):
    a = agent_with_session
    a._maybe_announce_ending(30)
    a._maybe_announce_ending(10)
    a._maybe_announce_ending(0)
    assert a.session.generate_reply.call_count == 1


def test_missing_remaining_is_ignored(agent_with_session):
    """An older API, or a failed parse, must not trigger a spurious goodbye."""
    a = agent_with_session
    a._maybe_announce_ending(None)
    a.session.generate_reply.assert_not_called()


def test_a_failing_announcement_does_not_propagate(agent_with_session):
    """A working conversation must not be broken by a failed courtesy."""
    a = agent_with_session
    a.session.generate_reply.side_effect = RuntimeError("realtime unavailable")
    a._maybe_announce_ending(10)   # must not raise
    assert a._ending_announced is True


def test_the_real_session_property_is_used_not_a_fictional_one():
    """The exact regression this file missed: production called `self.salon`, which is
    not an attribute the real Agent base class has ever defined. Read out of the source
    rather than exercised, because exercising it *is* the five tests above — this is the
    one that would have caught the typo they didn't."""
    import inspect

    source = inspect.getsource(salon.SalonAgent._maybe_announce_ending)
    assert "self.session.generate_reply" in source
    assert "self.salon" not in source
