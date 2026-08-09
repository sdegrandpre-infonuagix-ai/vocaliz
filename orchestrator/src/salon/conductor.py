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

from dataclasses import dataclass, field, field

from src.interprete import Annonce, Interprete, InterpreteError, Participant, Tour
from src.journal import MAX_MESSAGE_CHARACTERS, JournalEntry, SalonLog, without_markers
from src.salon.history import HistoryAccess, grants_history
from src.salon.notices import (
    already_here,
    history_shared_with,
    introduces,
    microphone_cut,
    microphone_restored,
    on_the_telephone,
)
from src.salon.captions import DEFAULT_CAPTION_SCALE, reads_captions
from src.salon.rooms import Room, RoomProvisioner
from src.salon.video import VideoPath, VideoTrack


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
    # Story 6.13. Off until asked for, and `wanted` remembers the asking across a drive:
    # somebody whose camera was on before they started driving did not choose to stop.
    video: VideoTrack | None = None
    wants_video: bool = False
    driving: bool = False
    # Story 6.14. `None` is "never chosen"; `""` is "as spoken, translate nothing", which is
    # a choice in its own right and the difference matters.
    caption_language: str | None = None
    caption_scale: float = DEFAULT_CAPTION_SCALE
    # True between two pieces of one intervention (Story 6.5). Nothing third-party is
    # spoken while it is.
    mid_run: bool = False
    # Announcements that arrived mid-run, in the order they arrived.
    held: list[Annonce] = field(default_factory=list)
    # Who this listener has been introduced to (Story 6.9). Per seat rather than per Salon:
    # what matters is that each person hears each introduction once, and somebody arriving
    # late has heard none of them.
    introduced: set[str] = field(default_factory=set)


class Salon:
    """One conversation, as an orchestrator instance holds it."""

    def __init__(
        self,
        *,
        log: SalonLog,
        rooms: RoomProvisioner,
        max_message_characters: int = MAX_MESSAGE_CHARACTERS,
        host_id: str | None = None,
        condensation_threshold_seconds: float = 120.0,
        video: VideoPath | None = None,
    ) -> None:
        self.log = log
        self._rooms = rooms
        self._max_message_characters = max_message_characters
        # Who may cut a microphone. None means nobody can, which is the right default for a
        # Salon whose host has not been declared: the alternative is everybody.
        self._host_id = host_id
        self._condensation_threshold = condensation_threshold_seconds
        # Optional: a deployment without it loses the pictures and nothing else.
        self._video = video
        self._seats: dict[str, Seat] = {}
        # The language each participant was first heard in. Written once and never revised,
        # like `salon_events.first_spoken_language`: somebody switching language mid-Salon
        # is not a second person and is not introduced again.
        self._first_language: dict[str, str] = {}
        # Everybody who has ever had a seat. The journal outlives the seat, so a late
        # arrival given the history hears what somebody said after they left — and has to
        # be told who said it.
        self._ever_joined: dict[str, Participant] = {}
        self._ever_joined: dict[str, Participant] = {}

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
        history: HistoryAccess = HistoryAccess.UNSPECIFIED,
    ) -> Room:
        """Give a participant a room, an interpreter and a position in the journal.

        Joining twice is the same participant reconnecting, not a second one. The seat that
        exists is returned rather than a second room opened — a room nobody accounts for is
        a room nobody closes, and rooms are billed by the minute.
        """
        # The host's decision, taken in the same breath as the invitation. Saying nothing
        # falls to `DEFAULT_HISTORY_FOR_ARRIVALS`, which grants it: somebody invited into a
        # conversation is being invited into what it has been about. `from_start` stays the
        # low-level knob underneath, and forcing it on still works.
        from_start = from_start or grants_history(history)

        existing = self._seats.get(participant.id)
        if existing is not None:
            return existing.room

        room = await self._rooms.provision(self.salon_id, participant)
        seat = Seat(participant=participant, room=room, interpreter=interpreter)
        self._seats[participant.id] = seat
        self._ever_joined[participant.id] = participant

        # At the head unless the host granted the history (Story 6.10). Written straight
        # away: a participant who joins and is then lost with the instance must come back
        # to the position they were given, not to the head of a journal they were meant to
        # have all of.
        self.log.attach(participant.id, from_start=from_start)
        await self.log.checkpoint()

        await self._say_who_is_here(self._seats[participant.id])
        await self._say_who_is_on_the_telephone(participant)
        if from_start:
            await self._say_the_history_was_shared(participant)
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

        await self._stop_video(seat)
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

        self._first_language.setdefault(participant_id, language)

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

        if await self._condense_if_far_behind(seat):
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

    async def _condense_if_far_behind(self, seat: Seat) -> bool:
        """Say the backlog in substance rather than replaying it, when there is too much.

        Whether to condense is decided by volume and by nothing else. Granting somebody the
        history and summarising it are two separate decisions (Story 6.10): a Salon two
        minutes old is replayed in full however it was granted, and a listener who has
        fallen twenty minutes behind is summarised however they got there.

        Returns whether it condensed. Nothing arriving afterwards is a special case — the
        next delivery weighs the same threshold against whatever has accumulated since.
        """
        participant_id = seat.participant.id
        pending = self.log.pending(participant_id)
        if not pending:
            return False
        if self.log.lag_seconds(participant_id) <= self._condensation_threshold:
            return False

        # Everybody covered counts as introduced: they were named in the summary, and
        # introducing them again with their next sentence would be introducing them twice.
        for entry in pending:
            seat.introduced.add(entry.participant_id)

        try:
            # Markers are dropped with the rest (Story 6.11): one does not summarise
            # silences, and a summary that reproduced them would spend its time on them.
            await seat.interpreter.condense(
                [_as_tour(entry, spoken_only=True) for entry in pending]
            )
        except InterpreteError:
            # Their adapter has told them out loud (NFR3). The position does not move, so
            # the backlog is still theirs to catch up on.
            return True

        await self.log.advance(participant_id, pending[-1].sequence)
        await self._say_held(seat)
        return True

    async def _render(self, seat: Seat, entries: tuple[JournalEntry, ...]) -> None:
        participant_id = seat.participant.id

        for entry in entries:
            # Nobody is told what they themselves said. It is the one thing they certainly
            # already know, and a journal every reader reads is exactly what would say it
            # back to them.
            if entry.participant_id != participant_id:
                # Who is speaking, before what they said (Story 6.9). Failing to say it must
                # not cost the message it introduces, so this does not raise.
                await self._introduce(seat, entry.participant_id)

                try:
                    await seat.interpreter.render(_as_tour(entry))
                except InterpreteError:
                    # Their own adapter has told them out loud (NFR3). The position stays
                    # where it is, so what they missed is still theirs to catch up on, and
                    # no other room is affected.
                    return

                seat.mid_run = entry.mid_run

                await self._send_caption(seat, entry)

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

    # ── Who is speaking ───────────────────────────────────────────────────────

    def _known_speakers(self, *, except_for: str = "") -> list[tuple[Participant, str]]:
        """Everybody who has actually been heard, and the language they were heard in.

        Only them. Somebody who has not spoken has no detected language, and there is
        nothing true to say about them yet — they are introduced when they speak.
        """
        # From everybody who has ever joined, not from who is still here. What somebody
        # said stays in the journal after they leave, so a late arrival given the history
        # hears them — and has to be told whose words those are.
        return [
            (self._ever_joined[key].name, language)
            for key, language in self._first_language.items()
            if key in self._ever_joined and key != except_for
        ]

    async def _say_who_is_here(self, seat: Seat) -> None:
        """Tell somebody arriving who has already spoken, and in what language.

        Nothing at all when nobody has: an announcement that names nobody is worse than no
        announcement. They are marked as introduced either way, so the next thing each of
        those people says is not prefaced a second time.
        """
        listener = seat.participant
        people = self._known_speakers(except_for=listener.id)

        # `already_here` decides whether there is anything worth saying; duplicating that
        # test here would be a second place for the two answers to drift apart.
        text = already_here(people, told_in=listener.language)
        seat.introduced.update(self._first_language)

        if text is not None:
            await self.announce(listener.id, Annonce(text=text, language=listener.language))

    async def _introduce(self, seat: Seat, speaker_id: str) -> None:
        """Say who is about to speak, once per listener.

        Silent when the speaker's language is somehow unknown — which cannot happen for a
        message that came through `ingest`, and inventing one would be worse than saying
        nothing.
        """
        if speaker_id in seat.introduced:
            return

        speaker = self._ever_joined.get(speaker_id)
        language = self._first_language.get(speaker_id)
        if speaker is None or language is None:
            return

        # Marked before it is said, not after: an interpreter that fails on the
        # introduction must not be asked for it again on every later message.
        seat.introduced.add(speaker_id)

        await self.announce(
            seat.participant.id,
            Annonce(
                text=introduces(
                    speaker.name, language, told_in=seat.participant.language
                ),
                language=seat.participant.language,
            ),
        )

    async def _say_the_history_was_shared(self, arrival: Participant) -> None:
        """Tell everybody already here that the arrival will hear what they said.

        Nothing when the journal is empty: granting access to nothing discloses nothing, and
        saying so would worry people about a disclosure that did not happen.

        There is no way to take this back, so the only honest moment to say it is now.
        """
        if not self.log.entries:
            return

        for seat in self._ordered_seats():
            if seat.participant.id == arrival.id:
                continue

            language = seat.participant.language
            await self.announce(
                seat.participant.id,
                Annonce(
                    text=history_shared_with(arrival.name, told_in=language),
                    language=language,
                ),
            )

    # ── Captions (Story 6.14) ─────────────────────────────────────────────────

    def caption_language(self, participant_id: str) -> str | None:
        seat = self._seats.get(participant_id)
        return seat.caption_language if seat else None

    def caption_scale(self, participant_id: str) -> float:
        seat = self._seats.get(participant_id)
        return seat.caption_scale if seat else DEFAULT_CAPTION_SCALE

    def reads_captions(self, participant_id: str) -> bool:
        return reads_captions(self.caption_language(participant_id))

    async def set_captions(
        self,
        participant_id: str,
        *,
        language: str | None,
        scale: float = DEFAULT_CAPTION_SCALE,
    ) -> None:
        """Choose what to read, and how large.

        `None` turns them off — back to never having chosen. `""` is the other kind of off:
        show me the original. Both are settings of the account rather than of the device.
        """
        seat = self._seats.get(participant_id)
        if seat is None:
            return

        seat.caption_language = language
        seat.caption_scale = scale

    async def _send_caption(self, seat: Seat, entry: JournalEntry) -> None:
        """Put one turn into this reader's own room, as text.

        The data channel of their room and nowhere else — the same isolation that makes echo
        impossible. It is never handed to the voice: a caption is something to read, and
        sending it to the interpreter would say everything twice.
        """
        if not reads_captions(seat.caption_language):
            return

        text = await self.log.render(entry, seat.caption_language or "")
        # A pause marker says how to *say* something. There is nothing to read in a silence.
        await self._rooms.publish(seat.room, without_markers(text).encode())

    # ── Video (Story 6.13) ────────────────────────────────────────────────────

    @property
    def publishing_video(self) -> tuple[str, ...]:
        return tuple(sorted(key for key, seat in self._seats.items() if seat.video))

    def video_on(self, participant_id: str) -> bool:
        seat = self._seats.get(participant_id)
        return seat is not None and seat.video is not None

    def receives_video(self, participant_id: str) -> bool:
        """Whether there is any point sending pictures to this participant.

        A telephone has no screen, and in driving mode there is nothing to look at — that
        being the whole purpose of the mode.
        """
        seat = self._seats.get(participant_id)
        if seat is None or seat.participant.by_telephone:
            return False
        return not seat.driving

    async def enable_video(self, participant_id: str) -> None:
        """Turn a camera on, at somebody's request and never otherwise.

        Refused for a telephone participant, who has none, and while driving, where the
        screen is black and a camera aimed at a windscreen helps nobody.
        """
        seat = self._seats.get(participant_id)
        if seat is None or seat.participant.by_telephone:
            return

        seat.wants_video = True
        if seat.driving or seat.video is not None or self._video is None:
            return

        seat.video = await self._video.publish(self.salon_id, seat.participant)

    async def disable_video(self, participant_id: str) -> None:
        """Turn it off. Deliberate, so it is not restored when a drive ends."""
        seat = self._seats.get(participant_id)
        if seat is None:
            return

        seat.wants_video = False
        await self._stop_video(seat)

    async def shed_video(self, participant_id: str) -> None:
        """Drop the pictures to save the conversation.

        Always in this order, and never the other way round: a conversation without
        pictures is still a conversation, and pictures without a conversation are nothing.
        The wish is kept, so it comes back when the connection does.
        """
        seat = self._seats.get(participant_id)
        if seat is not None:
            await self._stop_video(seat)

    async def start_driving(self, participant_id: str) -> None:
        """FR75. Video is suspended both ways; the wish for it survives."""
        seat = self._seats.get(participant_id)
        if seat is None:
            return

        seat.driving = True
        await self._stop_video(seat)

    async def stop_driving(self, participant_id: str) -> None:
        """Restore what was on before, and nothing that was not."""
        seat = self._seats.get(participant_id)
        if seat is None:
            return

        seat.driving = False
        if seat.wants_video:
            await self.enable_video(participant_id)

    async def _stop_video(self, seat: Seat) -> None:
        if seat.video is None or self._video is None:
            seat.video = None
            return

        track, seat.video = seat.video, None
        await self._video.stop(track)

    async def _say_who_is_on_the_telephone(self, arrival: Participant) -> None:
        """Tell the others, so an empty tile is not mistaken for somebody hiding."""
        if not arrival.by_telephone:
            return

        for seat in self._ordered_seats():
            if seat.participant.id == arrival.id:
                continue

            language = seat.participant.language
            await self.announce(
                seat.participant.id,
                Annonce(text=on_the_telephone(arrival.name, told_in=language), language=language),
            )

    def _ordered_seats(self) -> tuple[Seat, ...]:
        """Seats in a fixed order, so a Salon behaves the same way twice."""
        return tuple(self._seats[key] for key in sorted(self._seats))


def _as_tour(entry: JournalEntry, *, spoken_only: bool = False) -> Tour:
    """A journal entry in the shape the Interpreter port takes.

    `spoken_only` strips the metadata markers, which is what a condensation gets.
    """
    return Tour(
        participant_id=entry.participant_id,
        text=without_markers(entry.text) if spoken_only else entry.text,
        language=entry.language,
        sequence=entry.sequence,
    )
