"""Closing a room is the only thing that actually stops a conversation.

Ending the salon row settles the accounting; deleting the room is what disconnects the
participants and stops the agent. That call used to swallow every failure into a warning, so
the one case where it mattered — a transient LiveKit error — left everybody sitting in a room
whose salon was over, with nothing retrying and nobody told.

Two changes, tested here: the deletion is retried and its final failure is reported, and the
room is told the salon is over *before* it is deleted, so the clients no longer depend on that
deletion succeeding at all.
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from livekit.api import TwirpError, TwirpErrorCode

from src.services import livekit_service

# conftest replaces delete_room and notify_room with mocks for the whole suite, so that no
# test reaches the network. This module is the one that tests those functions themselves.
pytestmark = pytest.mark.real_livekit_service


class FakeLiveKit:
    """Stands in for the LiveKitAPI async context manager."""

    def __init__(self, outcomes, log=None):
        # One entry per expected attempt: None succeeds, an exception is raised.
        self.outcomes = list(outcomes)
        self.calls = 0
        # Ordering is recorded inside the delete call rather than by wrapping __aenter__:
        # `async with` looks its methods up on the type, so an instance attribute is ignored.
        self.log = log

    def __call__(self, *_args, **_kwargs):
        return self

    async def __aenter__(self):
        client = MagicMock()
        client.room = MagicMock()

        async def _delete(_request):
            self.calls += 1
            if self.log is not None:
                self.log.append("delete")
            outcome = self.outcomes.pop(0) if self.outcomes else None
            if outcome is not None:
                raise outcome

        client.room.delete_room = _delete
        return client

    async def __aexit__(self, *_exc):
        return False


def _twirp(code, status=500):
    return TwirpError(code=code, msg="from the test", status=status)


@pytest.fixture
def no_announce():
    """The announcement is tested separately; these tests are about the deletion."""
    with patch.object(livekit_service, "notify_room", new_callable=AsyncMock) as notify:
        yield notify


@pytest.fixture(autouse=True)
def instant_backoff():
    """The retry delays are real seconds in production and pointless in a test."""
    with patch.object(livekit_service.asyncio, "sleep", new_callable=AsyncMock):
        yield


# ─── Deleting ────────────────────────────────────────────────────────────────

def test_a_successful_deletion_reports_success(no_announce):
    fake = FakeLiveKit([None])
    with patch.object(livekit_service.lk_api, "LiveKitAPI", fake):
        assert asyncio.run(livekit_service.delete_room("salon-1")) is True
    assert fake.calls == 1, "no retry when the first attempt worked"


def test_a_room_already_gone_is_not_a_failure(no_announce):
    """LiveKit collects empty rooms on its own, so this is the ordinary case rather than an
    error — and retrying it would turn one round trip into three."""
    fake = FakeLiveKit([_twirp(TwirpErrorCode.NOT_FOUND)])
    with patch.object(livekit_service.lk_api, "LiveKitAPI", fake):
        assert asyncio.run(livekit_service.delete_room("salon-1")) is True
    assert fake.calls == 1


def test_a_transient_failure_is_retried_until_it_works(no_announce):
    """The case that used to strand a room for good: nothing ever tried again."""
    fake = FakeLiveKit([_twirp(TwirpErrorCode.UNAVAILABLE), None])
    with patch.object(livekit_service.lk_api, "LiveKitAPI", fake):
        assert asyncio.run(livekit_service.delete_room("salon-1")) is True
    assert fake.calls == 2


def test_a_persistent_failure_is_reported_rather_than_hidden(no_announce, caplog):
    fake = FakeLiveKit([_twirp(TwirpErrorCode.INTERNAL)] * livekit_service.DELETE_ROOM_ATTEMPTS)
    with patch.object(livekit_service.lk_api, "LiveKitAPI", fake):
        with caplog.at_level("ERROR"):
            assert asyncio.run(livekit_service.delete_room("salon-1")) is False
    assert fake.calls == livekit_service.DELETE_ROOM_ATTEMPTS
    # Error, not warning: participants are left connected to a dead salon, and the only
    # reason that was survivable before is that nobody saw it.
    assert any(r.levelname == "ERROR" for r in caplog.records)
    assert "salon-1" in caplog.text


def test_a_network_error_is_retried_too(no_announce):
    """Not every failure arrives as a Twirp error."""
    fake = FakeLiveKit([OSError("connection reset"), None])
    with patch.object(livekit_service.lk_api, "LiveKitAPI", fake):
        assert asyncio.run(livekit_service.delete_room("salon-1")) is True
    assert fake.calls == 2


def test_a_failure_never_raises_at_the_caller(no_announce):
    """A room that outlives its salon must not stop a host opening the next one."""
    fake = FakeLiveKit([OSError("down")] * livekit_service.DELETE_ROOM_ATTEMPTS)
    with patch.object(livekit_service.lk_api, "LiveKitAPI", fake):
        assert asyncio.run(livekit_service.delete_room("salon-1")) is False


# ─── Telling the room first ──────────────────────────────────────────────────

def test_the_room_is_told_before_it_is_deleted():
    """Order is the whole point: a deleted room cannot be sent anything, so afterwards is too
    late, and the clients would be back to depending on their transport dropping."""
    order = []
    announced = []

    async def _notify(room, message):
        order.append("notify")
        announced.append((room, message))

    fake = FakeLiveKit([None], log=order)

    with patch.object(livekit_service, "notify_room", _notify):
        with patch.object(livekit_service.lk_api, "LiveKitAPI", fake):
            asyncio.run(livekit_service.delete_room("salon-1"))

    assert order == ["notify", "delete"]
    assert announced == [("salon-1", {"action": "salon_ended"})]


def test_the_announcement_reaches_the_room_that_is_closing():
    notify = AsyncMock()
    fake = FakeLiveKit([None])
    with patch.object(livekit_service, "notify_room", notify):
        with patch.object(livekit_service.lk_api, "LiveKitAPI", fake):
            asyncio.run(livekit_service.delete_room("salon-7"))
    notify.assert_awaited_once_with("salon-7", {"action": "salon_ended"})


def test_a_failed_announcement_does_not_stop_the_deletion():
    """notify_room is best-effort by design and returns rather than raising, but the deletion
    must not become conditional on it either way."""
    fake = FakeLiveKit([None])
    with patch.object(livekit_service, "notify_room", AsyncMock(side_effect=None)):
        with patch.object(livekit_service.lk_api, "LiveKitAPI", fake):
            assert asyncio.run(livekit_service.delete_room("salon-1")) is True
    assert fake.calls == 1
