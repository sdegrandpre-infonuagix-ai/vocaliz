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

from dataclasses import dataclass, field

from src.interprete import Annonce, Interprete, InterpreteError, Participant, Tour
from src.journal import MAX_MESSAGE_CHARACTERS, JournalEntry, SalonLog
from src.salon.notices import microphone_cut, microphone_restored
from src.salon.notices import microphone_cut, microphone_restored
from src.salon.rooms import Room, RoomProvisioner


class NotTheHost(PermissionError):
    """Somebody who is not the host tried to do something only the host may do.

    Story 6.6 removed every notion of being granted the floor. Cutting a microphone is the
    one asymmetry left in a Salon, and it stays an asymmetry only because this exists — a
    participant who could silence another participant is a different product, and a cut
    whoever it was applied to could lift is not a cut.
    """

    def __init__(self, actor_id: str, salon_id: str) -> None:
        self.actor_id = actor_id
        super().__init__(f"{actor_id} is not the host of salon {salon_id}")


@dataclass
class Seat:
    """One participant's place: their room and the interpreter that is theirs."""

    participant: Participant
    room: Room
    interpreter: Interprete
    # Set by the host (Story 6.8). Nothing this participant says reaches the journal while
    # it holds; everything the others say still reaches them.
    muted: bool = False
    # True between two pieces of one intervention (Story 6.5). Nothing third-party is
    # spoken while it is.
    mid_run: bool = False
    # Announcements that arrived mid-run, in the order they arrived.
    held: list[Annonce] = field(default_factory=list)


class Salon:
    """One conversation, as an orchestrator instance holds it."""

    def __init__(
        self,
        *,
        log: SalonLog,
        rooms: RoomProvisioner,
        max_message_characters: int = MAX_MESSAGE_CHARACTERS,
        host_id: str | None = None,
    ) -> None:
        self.log = log
        self._rooms = rooms
        self._max_message_characters = max_message_characters
        # Who may cut a microphone. None means nobody can, which is the right default for a
        # Salon whose host has not been declared: the alternative is everybody.
        self._host_id = host_id
        self._seats: dict[str, Seat] = {}

    @property
    def salon_id(self) -> str:
        return self.log.salon_id

    @property
    def participants(self) -> tuple[str, ...]:
        return tuple(sorted(self._seats))

    @property
    def muted(self) -> tuple[str, ...]:
        """Whose microphone the host has closed."""
        return tuple(sorted(key for key, seat in self._seats.items() if seat.muted))

    def is_muted(self, participant_id: str) -> bool:
        seat = self._seats.get(participant_id)
        return seat is not None and seat.muted

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

    # ── The host's microphone control ─────────────────────────────────────────

    async def mute(self, participant_id: str, *, by: str) -> None:
        """Stop one participant being heard, and tell them so.

        It stops nothing else. They stay in the Salon, they keep their room and their
        position, and they go on hearing everybody — which is the whole difference between
        this and removing them.

        The notice is a courtesy and the cut is not: an interpreter that cannot deliver the
        message must not leave the microphone open, so the flag is set first.
        """
        seat = self._authorised(participant_id, by)
        if seat is None or seat.muted:
            return

        seat.muted = True
        await self.announce(
            participant_id,
            Annonce(
                text=microphone_cut(seat.participant.language),
                language=seat.participant.language,
            ),
        )

    async def unmute(self, participant_id: str, *, by: str) -> None:
        """Let them be heard again, and say so before they have to test it.

        Nothing is owed to them for the silence. What they say next takes the next position
        in the journal, behind whoever spoke while they were quiet — a cut is not a queue.
        """
        seat = self._authorised(participant_id, by)
        if seat is None or not seat.muted:
            return

        seat.muted = False
        await self.announce(
            participant_id,
            Annonce(
                text=microphone_restored(seat.participant.language),
                language=seat.participant.language,
            ),
        )

    def _authorised(self, participant_id: str, actor_id: str) -> Seat | None:
        """The seat to act on, once the actor is established as the host.

        A Salon with no host lets nobody do this. That is the state a Salon is in when its
        host has left, and it is not a reason to hand the control to whoever is still there.
        """
        if self._host_id is None or actor_id != self._host_id:
            raise NotTheHost(actor_id, self.salon_id)

        return self._seats.get(participant_id)

    # ── Out of a room, into the journal ───────────────────────────────────────

    async def ingest(
        self,
        participant_id: str,
        text: str,
        *,
        language: str,
        duration_seconds: float | None = None,
    ) -> tuple[JournalEntry, ...]:
        """Put what one participant said into the journal, once, cut into messages.

        Once, whoever ends up hearing it — which is also why Story 6.11 cleans here rather
        than at rendering: paid for a single time, and every listener benefits.

        A tuple because a long intervention is several messages (Story 6.5). Usually one,
        and empty when there was nothing to record.
        """
        if self.is_muted(participant_id):
            return ()

        return await self.log.record_intervention(
            participant_id=participant_id,
            text=text,
            language=language,
            duration_seconds=duration_seconds,
            max_characters=self._max_message_characters,
        )

    async def collect(self) -> tuple[JournalEntry, ...]:
        """Take what each interpreter has heard from its human into the journal."""
        recorded: list[JournalEntry] = []

        for seat in self._ordered_seats():
            # A cut microphone is not asked what it heard. Discarding it downstream would
            # work and would go on paying for the transcription of somebody who has been
            # told they are not being heard.
            if seat.muted:
                continue

            heard = await seat.interpreter.ingest()
            if heard is None:
                continue

            recorded.extend(
                await self.ingest(heard.participant_id, heard.text, language=heard.language)
            )

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

        await self._render(seat, self.log.pending(participant_id))

    async def deliver_upto(self, participant_id: str, sequence: int) -> None:
        """Render as far as one position and stop there.

        For a caller that wants to leave an interpreter part-way through an intervention —
        which is the only state in which Story 6.5's rule about announcements has anything
        to say.
        """
        seat = self._seats.get(participant_id)
        if seat is None:
            return

        pending = self.log.pending(participant_id)
        await self._render(seat, tuple(e for e in pending if e.sequence <= sequence))

    async def _render(self, seat: Seat, entries: tuple[JournalEntry, ...]) -> None:
        participant_id = seat.participant.id

        for entry in entries:
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

                seat.mid_run = entry.mid_run

            await self.log.advance(participant_id, entry.sequence)

            if not seat.mid_run:
                await self._say_held(seat)

    async def deliver_all(self) -> None:
        """Let every interpreter catch up, each at its own pace and none blocking another."""
        for seat in self._ordered_seats():
            await self.deliver(seat.participant.id)

    # ── Announcements ─────────────────────────────────────────────────────────

    async def announce(self, participant_id: str, annonce: Annonce) -> None:
        """Say something to one participant that nobody in the Salon said.

        Held back while their interpreter is between two pieces of one intervention. An
        announcement dropped into the middle of somebody's sentence is worse than the same
        announcement a second later, and the seam is where a listener is least able to tell
        the two speakers apart.
        """
        seat = self._seats.get(participant_id)
        if seat is None:
            return

        seat.held.append(annonce)
        if not seat.mid_run:
            await self._say_held(seat)

    async def _say_held(self, seat: Seat) -> None:
        """Say what was waiting, in the order it arrived."""
        while seat.held:
            annonce = seat.held.pop(0)
            try:
                await seat.interpreter.insert_annonce(annonce)
            except InterpreteError:
                # Their adapter has told them out loud already (NFR3). Putting it back would
                # replay it on every later delivery, and an announcement is not worth that.
                return

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
