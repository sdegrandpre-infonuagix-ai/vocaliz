"""One room per participant.

This is the piece that makes echo impossible rather than cancelled. A room holds one human
and that human's interpreter, and never a second human — so there is no audio to leak from
one person into another's microphone, no acoustic path to suppress, and nothing for FR17 to
ask for.

The consequence worth being explicit about: no participant ever hears another participant's
voice. Everything anybody hears is spoken by their own interpreter. That is what Stories
6.13 and 6.15 are for — the video and the speaking indicator give back the two signals this
topology takes away.

No provider SDK here, as everywhere under `src/`. A `Room` is a name and its two occupants;
building the LiveKit room it stands for is the interpreter worker's job, because the worker
is the thing that has the SDK.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from src.interprete import Participant

# The interpreter's identity in its human's room, derived from the participant so that an
# instance taking a Salon over can name it again without having stored it.
INTERPRETER_PREFIX = "interprete-"


def interpreter_identity(participant_id: str) -> str:
    return f"{INTERPRETER_PREFIX}{participant_id}"


def room_name(salon_id: str, participant_id: str) -> str:
    """The name of one participant's room in one Salon.

    Derived rather than random, and that is a requirement rather than a convenience: an
    instance that picks a Salon up has the Salon and its participants, and nothing else. A
    name it had to have stored would be a fourth thing to persist and a fourth thing to
    lose.
    """
    return f"{salon_id}--{participant_id}"


class RoomClosed(RuntimeError):
    """Something was published to a room that is no longer there."""

    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(f"room {name} is closed")


@dataclass
class Room:
    """One participant's room: them, their interpreter, and nobody else ever."""

    salon_id: str
    participant_id: str
    name: str
    closed: bool = False

    @property
    def occupants(self) -> tuple[str, ...]:
        """Exactly two, always. A third occupant would be a second voice in somebody's ear
        and the end of the guarantee this whole topology exists for."""
        return (interpreter_identity(self.participant_id), self.participant_id)


class RoomProvisioner(Protocol):
    """Making and unmaking rooms. Implemented against LiveKit by the interpreter worker."""

    async def provision(self, salon_id: str, participant: Participant) -> Room:
        """A room for this participant in this Salon, containing them and their interpreter."""

    async def close(self, room: Room) -> None:
        """Take a room down. Idempotent, and with no bearing on any other room."""

    async def publish(self, room: Room, payload: bytes) -> None:
        """Put something into one room. There is no call that puts it into two."""


class InMemoryRoomProvisioner:
    """Rooms that exist only as bookkeeping.

    For tests and for a developer with no LiveKit project, which Story 6.1 requires. It
    answers the port exactly, and it makes the isolation checkable: what is published to one
    room is readable from that room and from nowhere else.
    """

    def __init__(self) -> None:
        self._rooms: dict[str, Room] = {}
        self._published: dict[str, list[bytes]] = {}

    async def provision(self, salon_id: str, participant: Participant) -> Room:
        name = room_name(salon_id, participant.id)
        room = Room(salon_id=salon_id, participant_id=participant.id, name=name)
        self._rooms[name] = room
        self._published.setdefault(name, [])
        return room

    async def close(self, room: Room) -> None:
        room.closed = True
        self._rooms.pop(room.name, None)

    async def publish(self, room: Room, payload: bytes) -> None:
        if room.closed:
            raise RoomClosed(room.name)
        self._published.setdefault(room.name, []).append(payload)

    # ── For tests, which need to see that nothing crossed ────────────────────

    @property
    def open_rooms(self) -> tuple[str, ...]:
        return tuple(sorted(self._rooms))

    def published(self, room: Room) -> tuple[bytes, ...]:
        return tuple(self._published.get(room.name, ()))
