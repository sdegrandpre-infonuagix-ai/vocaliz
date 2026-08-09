"""The `RoomProvisioner` port, answered against LiveKit.

`src/salon/rooms.py` defines what a room is and what may be done with one; this builds the
real thing. It lives outside `src/` deliberately, and that placement is the whole point of
the port: the domain must not import a provider SDK — a test fails the build if it ever
does — while something, somewhere, has to.

**Why here rather than in the interpreter worker.** The worker was the first candidate,
being the component that already carries the LiveKit SDK. But creating a room is not
something a worker does: a worker is *dispatched into* a room that already exists. The
decision that a participant needs a room is the orchestrator's, made when somebody joins a
Salon, and an implementation living in another process would need an RPC layer that does
not exist to be reached. Having the SDK and owning the capability are different questions,
and the guard was never "no SDK in the orchestrator" — it is "no SDK in the domain".

**Two occupants, enforced by LiveKit rather than by our bookkeeping.** `max_participants`
is 2: the human and their interpreter. The topology's guarantee — that no two humans ever
share a room, so echo is impossible rather than cancelled — is worth more than a dataclass
that merely declines to store a third. Here the platform refuses the connection.
"""
from __future__ import annotations

import logging

from livekit import api as lk_api

from src.interprete import Participant
from src.salon.rooms import Room, RoomClosed, room_name

logger = logging.getLogger(__name__)

# One human, one interpreter. See the module docstring: this is the topology's guarantee
# expressed where it can actually be enforced.
OCCUPANTS_PER_ROOM = 2


class LiveKitRoomProvisioner:
    """Rooms that exist on LiveKit Cloud.

    Holds no client between calls. Each operation opens one and closes it, which is what
    the SDK's async context manager is for — a long-lived client would have to be
    reconnected after every idle period, and this is not a hot path: a room is provisioned
    when somebody joins, not per turn of speech.
    """

    def __init__(
        self,
        *,
        url: str,
        api_key: str,
        api_secret: str,
        empty_timeout_seconds: int = 30,
    ) -> None:
        # LiveKit's server API speaks HTTP where the client speaks WebSocket. Converting
        # here rather than asking every caller to hold two spellings of one address.
        self._url = url.replace("wss://", "https://").replace("ws://", "http://")
        self._api_key = api_key
        self._api_secret = api_secret
        self._empty_timeout = empty_timeout_seconds

    def _client(self) -> lk_api.LiveKitAPI:
        return lk_api.LiveKitAPI(self._url, self._api_key, self._api_secret)

    async def provision(self, salon_id: str, participant: Participant) -> Room:
        """A room for this participant in this Salon.

        The name is derived, never stored — an instance taking a Salon over can name the
        room again from the Salon and the participant, which is what makes a takeover
        possible without a fourth thing to persist.
        """
        name = room_name(salon_id, participant.id)
        async with self._client() as client:
            await client.room.create_room(
                lk_api.CreateRoomRequest(
                    name=name,
                    empty_timeout=self._empty_timeout,
                    max_participants=OCCUPANTS_PER_ROOM,
                )
            )
        logger.info("Provisioned room %s for salon %s", name, salon_id)
        return Room(salon_id=salon_id, participant_id=participant.id, name=name)

    async def close(self, room: Room) -> None:
        """Take one room down, and never another.

        Idempotent, as the port requires: a room LiveKit has already collected — an empty
        one past its timeout — is the outcome this asked for, not a failure. Marked closed
        locally whatever LiveKit says, so a caller cannot go on publishing into it.
        """
        try:
            async with self._client() as client:
                await client.room.delete_room(lk_api.DeleteRoomRequest(room=room.name))
        except Exception:  # noqa: BLE001
            # Logged rather than raised. Failing to delete a room must not stop a Salon
            # from closing: the room empties and LiveKit collects it on its own timeout,
            # where an exception here would leave the rest of the teardown undone.
            logger.warning("Could not delete room %s", room.name, exc_info=True)
        finally:
            room.closed = True

    async def publish(self, room: Room, payload: bytes) -> None:
        """Put something into one room.

        There is no call that puts it into two, and that absence is deliberate — the port
        says so, and it is what stops one participant's data reaching another's room.
        """
        if room.closed:
            raise RoomClosed(room.name)
        async with self._client() as client:
            await client.room.send_data(
                lk_api.SendDataRequest(room=room.name, data=payload, kind="RELIABLE")
            )
