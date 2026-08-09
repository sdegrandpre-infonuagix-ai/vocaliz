"""Provisioning one room per participant.

The port, and the double the tests and a developer's machine run against. What matters
about a room here is who is in it — one human and their interpreter, never two humans — and
that closing one has no bearing on any other.
"""
import pytest

from src.interprete import Participant
from src.salon import InMemoryRoomProvisioner, Room, RoomClosed

MARIE = Participant(id="marie", language="fr", name="Marie")
HANS = Participant(id="hans", language="de", name="Hans")


@pytest.fixture
def rooms():
    return InMemoryRoomProvisioner()


async def test_a_room_holds_one_human_and_their_interpreter(rooms):
    room = await rooms.provision("salon-1", MARIE)

    assert room.occupants == ("interprete-marie", "marie")


async def test_a_room_belongs_to_one_salon_and_one_participant(rooms):
    room = await rooms.provision("salon-1", MARIE)

    assert room.salon_id == "salon-1"
    assert room.participant_id == "marie"


async def test_each_participant_gets_a_room_of_their_own(rooms):
    """The acceptance criterion in one line: no two humans in one room, so there is no
    audio to share and no echo to cancel."""
    marie = await rooms.provision("salon-1", MARIE)
    hans = await rooms.provision("salon-1", HANS)

    assert marie.name != hans.name
    assert set(marie.occupants) & set(hans.occupants) == set()


async def test_the_same_participant_in_two_salons_has_two_rooms(rooms):
    one = await rooms.provision("salon-1", MARIE)
    other = await rooms.provision("salon-2", MARIE)

    assert one.name != other.name


async def test_a_room_name_is_derived_and_not_random(rooms):
    """An instance taking a Salon over has to find the rooms again, and it has only the
    Salon and the participant to go on."""
    first = await rooms.provision("salon-1", MARIE)
    await rooms.close(first)

    assert (await rooms.provision("salon-1", MARIE)).name == first.name


async def test_a_room_is_open_when_provisioned(rooms):
    assert (await rooms.provision("salon-1", MARIE)).closed is False


async def test_closing_a_room_leaves_the_others_alone(rooms):
    """A participant hanging up must not take the conversation down with them."""
    marie = await rooms.provision("salon-1", MARIE)
    hans = await rooms.provision("salon-1", HANS)

    await rooms.close(marie)

    assert marie.closed is True
    assert hans.closed is False
    assert rooms.open_rooms == (hans.name,)


async def test_closing_a_room_twice_is_harmless(rooms):
    """A participant who leaves and whose Salon then ends closes the same room twice."""
    room = await rooms.provision("salon-1", MARIE)

    await rooms.close(room)
    await rooms.close(room)

    assert rooms.open_rooms == ()


async def test_a_closed_room_carries_nothing_further(rooms):
    room = await rooms.provision("salon-1", MARIE)
    await rooms.close(room)

    with pytest.raises(RoomClosed):
        await rooms.publish(room, b"audio")


async def test_what_is_published_reaches_only_that_room(rooms):
    """Nothing crosses. Echo is not cancelled here, it is unavailable."""
    marie = await rooms.provision("salon-1", MARIE)
    hans = await rooms.provision("salon-1", HANS)

    await rooms.publish(marie, b"bonjour")

    assert rooms.published(marie) == (b"bonjour",)
    assert rooms.published(hans) == ()


def test_a_room_knows_nothing_of_any_provider():
    """`Room` is a name and two occupants. The LiveKit room it stands for is built by the
    interpreter worker, which is the only thing that has the SDK."""
    room = Room(salon_id="salon-1", participant_id="marie", name="salon-1--marie")

    assert room.occupants == ("interprete-marie", "marie")
