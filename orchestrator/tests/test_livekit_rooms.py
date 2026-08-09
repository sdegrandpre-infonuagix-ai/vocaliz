"""The LiveKit-backed provisioner, checked without a LiveKit project.

The SDK is mocked throughout. What is worth asserting here is not that LiveKit works — it
does — but that this adapter asks it for the right things: two occupants and never three,
one room touched per call and never two, and a delete that does not raise when the room has
already gone.

The in-memory provisioner these mirror is in `test_salon.py`; the port suite is what makes
the two interchangeable. This file covers what only the real one can get wrong.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from adapters.livekit_rooms import OCCUPANTS_PER_ROOM, LiveKitRoomProvisioner
from src.interprete import Participant
from src.salon.rooms import Room, RoomClosed


@pytest.fixture
def client():
    """A stand-in LiveKit client, and the async context manager the SDK hands back."""
    fake = MagicMock()
    fake.room = MagicMock()
    fake.room.create_room = AsyncMock()
    fake.room.delete_room = AsyncMock()
    fake.room.send_data = AsyncMock()

    manager = MagicMock()
    manager.__aenter__ = AsyncMock(return_value=fake)
    manager.__aexit__ = AsyncMock(return_value=False)

    with patch("adapters.livekit_rooms.lk_api.LiveKitAPI", return_value=manager):
        yield fake


@pytest.fixture
def provisioner():
    return LiveKitRoomProvisioner(
        url="wss://example.livekit.cloud", api_key="k", api_secret="s"
    )


def _someone(identifier="alice"):
    return Participant(id=identifier, language="fr")


# ── Provisioning ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_a_room_is_capped_at_two_occupants(client, provisioner):
    """The topology's guarantee, enforced where it can actually be enforced. A dataclass
    that declines to store a third occupant is bookkeeping; this makes LiveKit refuse the
    connection."""
    await provisioner.provision("salon-1", _someone())

    request = client.room.create_room.await_args.args[0]
    assert request.max_participants == OCCUPANTS_PER_ROOM == 2


@pytest.mark.asyncio
async def test_the_room_name_is_derived_from_the_salon_and_the_participant(
    client, provisioner
):
    """Never random and never stored: an instance taking a Salon over has the Salon and its
    participants, and must be able to name the room again from those alone."""
    room = await provisioner.provision("salon-1", _someone("alice"))

    assert room.name == "salon-1--alice"
    assert client.room.create_room.await_args.args[0].name == "salon-1--alice"


@pytest.mark.asyncio
async def test_two_participants_get_two_different_rooms(client, provisioner):
    first = await provisioner.provision("salon-1", _someone("alice"))
    second = await provisioner.provision("salon-1", _someone("bob"))

    assert first.name != second.name


@pytest.mark.asyncio
async def test_a_websocket_url_is_converted_for_the_server_api(client):
    """The client speaks WebSocket and the server API speaks HTTP. Asking every caller to
    hold two spellings of one address is how one of them ends up wrong."""
    made = LiveKitRoomProvisioner(url="wss://x.livekit.cloud", api_key="k", api_secret="s")

    assert made._url == "https://x.livekit.cloud"


# ── Closing ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_closing_deletes_that_room_and_no_other(client, provisioner):
    room = await provisioner.provision("salon-1", _someone())

    await provisioner.close(room)

    assert client.room.delete_room.await_args.args[0].room == room.name


@pytest.mark.asyncio
async def test_closing_a_room_that_is_already_gone_is_not_an_error(client, provisioner):
    """Idempotent, as the port requires. A room LiveKit has already collected — an empty
    one past its timeout — is the outcome this asked for, not a failure."""
    room = await provisioner.provision("salon-1", _someone())
    client.room.delete_room.side_effect = RuntimeError("no such room")

    await provisioner.close(room)

    assert room.closed is True


@pytest.mark.asyncio
async def test_a_room_is_marked_closed_even_when_livekit_refuses(client, provisioner):
    """Locally closed whatever the platform says, so a caller cannot go on publishing into
    something that is on its way out."""
    room = await provisioner.provision("salon-1", _someone())
    client.room.delete_room.side_effect = RuntimeError("boom")

    await provisioner.close(room)

    with pytest.raises(RoomClosed):
        await provisioner.publish(room, b"anything")


# ── Publishing ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_publishing_reaches_one_room(client, provisioner):
    """There is no call that puts something into two, and that absence is what stops one
    participant's data reaching another's room."""
    room = await provisioner.provision("salon-1", _someone())

    await provisioner.publish(room, b"hello")

    request = client.room.send_data.await_args.args[0]
    assert request.room == room.name
    assert request.data == b"hello"


@pytest.mark.asyncio
async def test_publishing_into_a_closed_room_raises(client, provisioner):
    room = Room(salon_id="s", participant_id="p", name="s--p", closed=True)

    with pytest.raises(RoomClosed):
        await provisioner.publish(room, b"hello")


@pytest.mark.asyncio
async def test_nothing_is_published_when_the_room_is_closed(client, provisioner):
    """The refusal happens before the call, not after it — otherwise the payload would
    already have reached a room the caller was told it could not use."""
    room = Room(salon_id="s", participant_id="p", name="s--p", closed=True)

    with pytest.raises(RoomClosed):
        await provisioner.publish(room, b"hello")

    client.room.send_data.assert_not_awaited()
