"""Handing a Salon to the orchestrator that will hold its text.

One call, made in the same breath as the LiveKit room, because the room and the conversation
are two halves of one act. What these tests hold to account is mostly what happens when it
goes wrong: a host must be able to open a Salon while the orchestrator is restarting, missing,
draining, or slow, and the record must say plainly that nobody took it.

The property behind all of them: **the orchestrator is not on the critical path of starting a
conversation.** A Salon that opens without translation is worse than one that works and vastly
better than a host who cannot begin.
"""
import asyncio
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import httpx
import pytest

from src.config import settings
from src.services import orchestrator_client

SALON_ID = uuid4()
HOST_ID = uuid4()
ROOM = "vocaliz-abc123"


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setattr(settings, "orchestrator_base_url", "http://orchestrator:8080")
    return "http://orchestrator:8080"


def _responds(status: int):
    """An httpx client whose PUT answers with one status and nothing else."""
    client = AsyncMock()
    client.put = AsyncMock(return_value=httpx.Response(status_code=status))
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    return client


def _host():
    """`asyncio.run` rather than an async test, which is how this suite drives async code."""
    return asyncio.run(
        orchestrator_client.host_salon(
            salon_id=SALON_ID, room_name=ROOM, host_id=HOST_ID
        )
    )


# ── Nothing configured ────────────────────────────────────────────────────────


def test_no_orchestrator_configured_makes_no_request(monkeypatch):
    """Inert rather than failing. The ECS service is not deployed; a default address
    resolving to nothing would turn every salon creation into a wait for a connection
    refused, which is a worse way of saying "not built yet" than doing nothing."""
    monkeypatch.setattr(settings, "orchestrator_base_url", "")

    with patch("httpx.AsyncClient") as client:
        assert _host() is None

    client.assert_not_called()


# ── The ordinary case ─────────────────────────────────────────────────────────


def test_the_address_that_accepted_the_salon_is_what_comes_back(configured):
    with patch("httpx.AsyncClient", return_value=_responds(200)):
        assert _host() == configured


def test_the_request_names_the_salon_and_carries_the_room(configured):
    """The room name is recorded rather than used — room names are derived from the Salon and
    the participant. It is what makes a log line about this Salon joinable to a log line about
    that room at three in the morning."""
    client = _responds(200)

    with patch("httpx.AsyncClient", return_value=client):
        _host()

    url, = client.put.await_args.args
    assert url == f"{configured}/salons/{SALON_ID}"
    assert client.put.await_args.kwargs["json"] == {
        "livekitRoomName": ROOM,
        "hostId": str(HOST_ID),
    }


def test_nothing_of_the_conversation_is_sent(configured):
    """Text only, and barely that: the request names a Salon and a room. A field that could
    carry sound, or anything anybody said, would be the boundary eroding one convenience at
    a time."""
    client = _responds(200)

    with patch("httpx.AsyncClient", return_value=client):
        _host()

    assert set(client.put.await_args.kwargs["json"]) == {"livekitRoomName", "hostId"}


# ── When it goes wrong ────────────────────────────────────────────────────────


def test_an_unreachable_orchestrator_does_not_stop_a_salon(configured):
    """The one that matters. A host must be able to open a Salon while a second service is
    restarting — it opens without translation, and the null record says so."""
    client = _responds(200)
    client.put.side_effect = httpx.ConnectError("nobody there")

    with patch("httpx.AsyncClient", return_value=client):
        assert _host() is None


def test_a_timeout_is_survived_like_any_other_failure(configured):
    client = _responds(200)
    client.put.side_effect = httpx.ReadTimeout("too slow")

    with patch("httpx.AsyncClient", return_value=client):
        assert _host() is None


def test_a_draining_instance_is_not_recorded_as_holding_the_salon(configured):
    """503 is not an error: that instance is finishing what it holds. With one instance there
    is nowhere else to go, so the Salon opens without translation rather than pretending an
    instance on its way out is responsible for it."""
    with patch("httpx.AsyncClient", return_value=_responds(503)):
        assert _host() is None


def test_a_refusal_is_not_recorded_either(configured):
    with patch("httpx.AsyncClient", return_value=_responds(500)):
        assert _host() is None


def test_a_trailing_slash_does_not_produce_a_double_one(monkeypatch):
    monkeypatch.setattr(settings, "orchestrator_base_url", "http://orchestrator:8080/")
    client = _responds(200)

    with patch("httpx.AsyncClient", return_value=client):
        _host()

    assert client.put.await_args.args[0] == f"http://orchestrator:8080/salons/{SALON_ID}"
