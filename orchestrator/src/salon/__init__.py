"""A Salon in progress: one room and one interpreter per participant, over one journal.

`rooms` is what makes echo unavailable rather than cancelled — one human per room, always.
`conductor` is what ties that to the journal of Story 6.3 and the Interpreter port of 6.2.
"""
from src.salon.conductor import Salon
from src.salon.rooms import (
    InMemoryRoomProvisioner,
    Room,
    RoomClosed,
    RoomProvisioner,
    interpreter_identity,
    room_name,
)

__all__ = [
    "InMemoryRoomProvisioner",
    "Room",
    "RoomClosed",
    "RoomProvisioner",
    "Salon",
    "interpreter_identity",
    "room_name",
]
