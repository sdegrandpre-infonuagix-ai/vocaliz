"""A Salon in progress: one room and one interpreter per participant, over one journal.

`rooms` is what makes echo unavailable rather than cancelled — one human per room, always.
`conductor` is what ties that to the journal of Story 6.3 and the Interpreter port of 6.2.
"""
from src.salon.conductor import NotTheHost, Salon
from src.salon.history import (
    DEFAULT_HISTORY_FOR_ARRIVALS,
    HistoryAccess,
    grants_history,
    history_from_invitation,
)
from src.salon.notices import history_shared_with, microphone_cut, microphone_restored
from src.salon.rooms import (
    InMemoryRoomProvisioner,
    Room,
    RoomClosed,
    RoomProvisioner,
    interpreter_identity,
    room_name,
)

__all__ = [
    "DEFAULT_HISTORY_FOR_ARRIVALS",
    "HistoryAccess",
    "InMemoryRoomProvisioner",
    "NotTheHost",
    "Room",
    "RoomClosed",
    "RoomProvisioner",
    "Salon",
    "interpreter_identity",
    "grants_history",
    "history_from_invitation",
    "history_shared_with",
    "microphone_cut",
    "microphone_restored",
    "room_name",
]
