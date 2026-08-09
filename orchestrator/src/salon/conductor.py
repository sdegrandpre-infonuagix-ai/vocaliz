"""A Salon running: one room and one interpreter per participant, over one journal.

Where the three pieces of the epic meet. Story 6.3 gave the journal and the reading
positions, 6.2 gave the interpreters, and this provisions a room for each participant and
moves messages from the journal into every interpreter except the one that produced them.

Two directions, kept apart on purpose. `ingest` is what comes out of a room and into the
journal; `deliver` is what goes from the journal back into one room. Neither waits on the
other — an interpreter that has fallen behind on its rendering must not hold up anybody
else's words reaching the journal, and that independence is the whole reason the positions
are per-reader.

What crosses between participants is text in the journal. No audio ever does.
"""
from __future__ import annotations

from dataclasses import dataclass

from src.interprete import Interprete, InterpreteError, Participant, Tour
from src.journal import JournalEntry, SalonLog
from src.salon.rooms import Room, RoomProvisioner


@dataclass
class Seat:
    """One participant's place: their room and the interpreter that is theirs."""

    participant: Participant
    room: Room
    interpreter: Interprete


class Salon:
    """One conversation, as an orchestrator instance holds it."""

    def __init__(self, *, log: SalonLog, rooms: RoomProvisioner) -> None:
        self.log = log
        self._rooms = rooms
        self._seats: dict[str, Seat] = {}

    @property
    def salon_id(self) -> str:
        return self.log.salon_id

    @property
    def participants(self) -> tuple[str, ...]:
        return tuple(sorted(self._seats))

    def interpreter_of(self, participant_id: str) -> Interprete | None:
        seat = self._seats.get(participant_id)
        return seat.interpreter if seat else None

    async def room_of(self, participant_id: str) -> Room | None:
        seat = self._seats.get(participant_id)
        return seat.room if seat else None

    def pending_for(self, participant_id: str) -> tuple[JournalEntry, ...]:
        return self.log.pending(participant_id)

    # ── Coming and going ──────────────────────────────────────────────────────

    async def join(
        self,
        participant: Participant,
        interpreter: Interprete,
        *,
        from_start: bool = False,
    ) -> Room:
        """Give a participant a room, an interpreter and a position in the journal.

        Joining twice is the same participant reconnecting, not a second one. The seat that
        exists is returned rather than a second room opened — a room nobody accounts for is
        a room nobody closes, and rooms are billed by the minute.
        """
        existing = self._seats.get(participant.id)
        if existing is not None:
            return existing.room

        room = await self._rooms.provision(self.salon_id, participant)
        self._seats[participant.id] = Seat(
            participant=participant, room=room, interpreter=interpreter
        )

        # At the head unless the host granted the history (Story 6.10). Written straight
        # away: a participant who joins and is then lost with the instance must come back
        # to the position they were given, not to the head of a journal they were meant to
        # have all of.
        self.log.attach(participant.id, from_start=from_start)
        await self.log.checkpoint()
        return room

    async def leave(self, participant_id: str) -> None:
        """Close one participant's room and interpreter, and nothing else.

        Idempotent, and silent about somebody who was never here: a connection that dies is
        often reported twice, and neither report may take the Salon down. What they said
        stays in the journal — leaving is not a reason to lose half the conversation.
        """
        seat = self._seats.pop(participant_id, None)
        if seat is None:
            return

        self.log.detach(participant_id)
        await seat.interpreter.aclose()
        await self._rooms.close(seat.room)

    async def aclose(self) -> None:
        """End the Salon. Every room closes; the journal stays where it is (NFR8)."""
        for participant_id in list(self._seats):
            await self.leave(participant_id)

    # ── Out of a room, into the journal ───────────────────────────────────────

    async def ingest(
        self,
        participant_id: str,
        text: str,
        *,
        language: str,
        duration_seconds: float | None = None,
    ) -> JournalEntry | None:
        """Put what one participant said into the journal, once.

        Once, whoever ends up hearing it — which is also why Story 6.11 cleans here rather
        than at rendering: paid for a single time, and every listener benefits.
        """
        return await self.log.record(
            participant_id=participant_id,
            text=text,
            language=language,
            duration_seconds=duration_seconds,
        )

    async def collect(self) -> tuple[JournalEntry, ...]:
        """Take what each interpreter has heard from its human into the journal."""
        recorded: list[JournalEntry] = []

        for seat in self._ordered_seats():
            heard = await seat.interpreter.ingest()
            if heard is None:
                continue

            entry = await self.ingest(
                heard.participant_id, heard.text, language=heard.language
            )
            if entry is not None:
                recorded.append(entry)

        return tuple(recorded)

    # ── Out of the journal, into a room ───────────────────────────────────────

    async def deliver(self, participant_id: str) -> None:
        """Let one interpreter say what it has not said yet, and move its position.

        The position advances as each message is rendered rather than at the end, so an
        interruption leaves it exactly where the rendering stopped. Hearing a sentence
        twice is worse than hearing it late: a listener cannot tell a repeat from somebody
        saying the same thing again.
        """
        seat = self._seats.get(participant_id)
        if seat is None:
            return

        for entry in self.log.pending(participant_id):
            # Nobody is told what they themselves said. It is the one thing they certainly
            # already know, and a journal every reader reads is exactly what would say it
            # back to them.
            if entry.participant_id != participant_id:
                try:
                    await seat.interpreter.render(_as_tour(entry))
                except InterpreteError:
                    # Their own adapter has told them out loud (NFR3). The position stays
                    # where it is, so what they missed is still theirs to catch up on, and
                    # no other room is affected.
                    return

            await self.log.advance(participant_id, entry.sequence)

    async def deliver_all(self) -> None:
        """Let every interpreter catch up, each at its own pace and none blocking another."""
        for seat in self._ordered_seats():
            await self.deliver(seat.participant.id)

    def _ordered_seats(self) -> tuple[Seat, ...]:
        """Seats in a fixed order, so a Salon behaves the same way twice."""
        return tuple(self._seats[key] for key in sorted(self._seats))


def _as_tour(entry: JournalEntry) -> Tour:
    """A journal entry in the shape the Interpreter port takes."""
    return Tour(
        participant_id=entry.participant_id,
        text=entry.text,
        language=entry.language,
        sequence=entry.sequence,
    )
