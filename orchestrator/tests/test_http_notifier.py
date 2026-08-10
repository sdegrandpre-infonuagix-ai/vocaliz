"""The `Notifier` port, answered by calling the API back.

httpx is mocked throughout — this is about what the adapter asks for, not that httpx works.
Every failure path is checked because the one rule the module docstring states is absolute:
this must never raise, since the poll behind it is the correctness guarantee and a courtesy
that could break a Salon would defeat its own purpose.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from adapters.http_notifier import HttpNotifier


@pytest.fixture
def client():
    fake = MagicMock()
    fake.post = AsyncMock(return_value=MagicMock(status_code=200))

    manager = MagicMock()
    manager.__aenter__ = AsyncMock(return_value=fake)
    manager.__aexit__ = AsyncMock(return_value=False)

    with patch("adapters.http_notifier.httpx.AsyncClient", return_value=manager):
        yield fake


@pytest.fixture
def notifier():
    return HttpNotifier(base_url="https://api.example.com", secret="shh")


@pytest.mark.asyncio
async def test_it_posts_to_the_wake_endpoint(client, notifier):
    await notifier.notify("salon-1", "marie")

    client.post.assert_awaited_once()
    url = client.post.await_args.args[0]
    assert url == "https://api.example.com/orchestrator/wake"


@pytest.mark.asyncio
async def test_the_body_names_the_salon_and_the_participant(client, notifier):
    await notifier.notify("salon-1", "marie")

    body = client.post.await_args.kwargs["json"]
    assert body == {"salonId": "salon-1", "participantId": "marie"}


@pytest.mark.asyncio
async def test_the_secret_travels_as_a_bearer_token(client, notifier):
    await notifier.notify("salon-1", "marie")

    headers = client.post.await_args.kwargs["headers"]
    assert headers["Authorization"] == "Bearer shh"


@pytest.mark.asyncio
async def test_a_trailing_slash_on_the_base_url_is_not_doubled(client):
    notifier = HttpNotifier(base_url="https://api.example.com/", secret="shh")

    await notifier.notify("salon-1", "marie")

    url = client.post.await_args.args[0]
    assert url == "https://api.example.com/orchestrator/wake"


# ── Never raising ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_an_unreachable_api_does_not_raise(notifier):
    with patch(
        "adapters.http_notifier.httpx.AsyncClient",
        side_effect=RuntimeError("connection refused"),
    ):
        await notifier.notify("salon-1", "marie")  # must not raise


@pytest.mark.asyncio
async def test_an_error_response_does_not_raise(client, notifier):
    client.post.return_value = MagicMock(status_code=500)

    await notifier.notify("salon-1", "marie")  # must not raise


@pytest.mark.asyncio
async def test_no_base_url_configured_does_nothing():
    """The empty-string default — no notifier wired at all — must not even try."""
    notifier = HttpNotifier(base_url="", secret="shh")

    with patch("adapters.http_notifier.httpx.AsyncClient") as ctor:
        await notifier.notify("salon-1", "marie")

    ctor.assert_not_called()


@pytest.mark.asyncio
async def test_no_secret_configured_does_nothing():
    """A base URL with no secret would post an unauthenticated wake the API can only refuse
    — better to never send it."""
    notifier = HttpNotifier(base_url="https://api.example.com", secret="")

    with patch("adapters.http_notifier.httpx.AsyncClient") as ctor:
        await notifier.notify("salon-1", "marie")

    ctor.assert_not_called()
