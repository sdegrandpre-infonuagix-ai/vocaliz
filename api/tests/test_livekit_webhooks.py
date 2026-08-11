"""Tests for POST /webhooks/livekit.

Signature verification is the SDK's own job (`livekit.api.WebhookReceiver`), not logic this
file re-proves — these tests patch `receive` and exercise the routing decision it feeds: which
events redispatch, which don't, and the cooldown that keeps a genuinely dead provider from
being redispatched into as fast as each fresh agent fails against it too.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from src.routers import livekit_webhooks


def _event(event: str, *, kind: int = livekit_webhooks._AGENT_KIND, room: str = "room-x"):
    return SimpleNamespace(
        event=event,
        room=SimpleNamespace(name=room),
        participant=SimpleNamespace(kind=kind),
    )


def test_an_unverifiable_request_is_answered_but_not_acted_on(client):
    with patch.object(livekit_webhooks._receiver, "receive", side_effect=Exception("bad sig")):
        resp = client.post("/webhooks/livekit", data=b"junk")

    assert resp.status_code == 200
    assert resp.json()["status"] == "rejected"


def test_an_agent_leaving_redispatches(client):
    livekit_webhooks._last_redispatch_at.clear()
    with (
        patch.object(livekit_webhooks._receiver, "receive", return_value=_event("participant_left")),
        patch(
            "src.routers.livekit_webhooks.agent_redispatch.redispatch_for_room",
            new_callable=AsyncMock,
        ) as mock_redispatch,
    ):
        resp = client.post("/webhooks/livekit", data=b"{}")

    assert resp.status_code == 200
    mock_redispatch.assert_called_once()
    assert mock_redispatch.call_args[0][1] == "room-x"


def test_a_human_leaving_does_not_redispatch(client):
    """kind 4 is AGENT; anything else is a human, and a human leaving is not this webhook's
    problem — `finalize_salon`/`salon_events` already handle it."""
    livekit_webhooks._last_redispatch_at.clear()
    with (
        patch.object(
            livekit_webhooks._receiver, "receive", return_value=_event("participant_left", kind=1)
        ),
        patch(
            "src.routers.livekit_webhooks.agent_redispatch.redispatch_for_room",
            new_callable=AsyncMock,
        ) as mock_redispatch,
    ):
        resp = client.post("/webhooks/livekit", data=b"{}")

    assert resp.status_code == 200
    mock_redispatch.assert_not_called()


def test_an_unrelated_event_does_not_redispatch(client):
    livekit_webhooks._last_redispatch_at.clear()
    with (
        patch.object(livekit_webhooks._receiver, "receive", return_value=_event("room_started")),
        patch(
            "src.routers.livekit_webhooks.agent_redispatch.redispatch_for_room",
            new_callable=AsyncMock,
        ) as mock_redispatch,
    ):
        resp = client.post("/webhooks/livekit", data=b"{}")

    assert resp.status_code == 200
    mock_redispatch.assert_not_called()


def test_a_second_departure_within_the_cooldown_is_skipped(client):
    """A room whose fresh agent fails immediately and leaves again must not be redispatched
    into at full speed — that is one failing connection multiplied by however fast this loop
    can turn, which is the worst possible response to a provider that is genuinely down."""
    livekit_webhooks._last_redispatch_at.clear()
    with (
        patch.object(livekit_webhooks._receiver, "receive", return_value=_event("participant_left")),
        patch(
            "src.routers.livekit_webhooks.agent_redispatch.redispatch_for_room",
            new_callable=AsyncMock,
        ) as mock_redispatch,
    ):
        client.post("/webhooks/livekit", data=b"{}")
        resp = client.post("/webhooks/livekit", data=b"{}")

    assert resp.status_code == 200
    mock_redispatch.assert_called_once()  # only the first of the two calls went through


def test_different_rooms_are_not_bound_by_each_others_cooldown(client):
    livekit_webhooks._last_redispatch_at.clear()
    with (
        patch.object(
            livekit_webhooks._receiver,
            "receive",
            side_effect=[_event("participant_left", room="room-a"), _event("participant_left", room="room-b")],
        ),
        patch(
            "src.routers.livekit_webhooks.agent_redispatch.redispatch_for_room",
            new_callable=AsyncMock,
        ) as mock_redispatch,
    ):
        client.post("/webhooks/livekit", data=b"{}")
        client.post("/webhooks/livekit", data=b"{}")

    assert mock_redispatch.call_count == 2


def test_a_redispatch_failure_still_answers_200(client):
    """The webhook provider must never see this as a reason to retry or disable itself —
    a redispatch that failed is logged, not turned into an HTTP error."""
    livekit_webhooks._last_redispatch_at.clear()
    with (
        patch.object(livekit_webhooks._receiver, "receive", return_value=_event("participant_left")),
        patch(
            "src.routers.livekit_webhooks.agent_redispatch.redispatch_for_room",
            new_callable=AsyncMock,
            side_effect=Exception("LiveKit is unreachable"),
        ),
    ):
        resp = client.post("/webhooks/livekit", data=b"{}")

    assert resp.status_code == 200
