"""Tests for Story 4.2 — agent metering heartbeat loop."""
import asyncio
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

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
        session_id="sess-1",
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
        session_id="sess-1",
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
        session_id="sess-1",
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
        session_id="sess-abc",
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
                "http://api.test/sessions/sess-abc/heartbeat",
                json={"seconds": 30},
                headers={"Authorization": "Bearer bearer-tok"},
            )

    asyncio.run(_run())


def test_send_heartbeat_no_op_without_session_context():
    """_send_heartbeat silently skips when session context is missing."""
    a = salon.SalonAgent()

    async def _run():
        with patch("httpx.AsyncClient") as mock_client_cls:
            await a._send_heartbeat()
            mock_client_cls.assert_not_called()

    asyncio.run(_run())


def test_send_heartbeat_swallows_network_errors():
    """A network failure during heartbeat does not raise."""
    a = salon.SalonAgent(
        session_id="sess-x",
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
        session_id="sess-y",
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
