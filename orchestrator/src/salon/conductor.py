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

import json

from dataclasses import dataclass, field

from src.interprete import Annonce, Interprete, InterpreteError, Participant, Tour
from src.journal import JournalEntry, SalonLog, content_seconds, without_markers
from src.settings import SalonSettings
from src.salon.history import HistoryAccess, grants_history
from src.salon.notices import (
    already_here,
    condensed_while_listening,
    history_shared_with,
    introduces,
    microphone_cut,
    microphone_restored,
    vocaliz_is_busy,
    on_the_telephone,
)
from src.salon.advertising import Regie
from src.salon.captions import DEFAULT_CAPTION_SCALE, reads_captions
from src.salon.rooms import Room, RoomProvisioner
from src.salon.meta_speech import MetaSpeechQueue, Urgency
from src.salon.speaking import SpeakingBoard
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
    # Story 6.16. What they were reading before the screen went black, kept so it can be
    # given back. `None` means there is nothing to give back — either they are not driving,
    # or they have chosen something since, which supersedes it.
    captions_before: tuple[str | None, float] | None = None
    # True between two pieces of one intervention (Story 6.5). Nothing third-party is
    # spoken while it is.
    mid_run: bool = False
    # Announcements that arrived mid-run (Story 6.5), in the order they will be said —
    # which past Story 7.6 is a deliberate order rather than the order they turned up in.
    held: MetaSpeechQueue = field(default_factory=MetaSpeechQueue)
    # Who this listener has been introduced to (Story 6.9). Per seat rather than per Salon:
    # what matters is that each person hears each introduction once, and somebody arriving
    # late has heard none of them.
    introduced: set[str] = field(default_factory=set)
    # Story 7.3. Set when this room's own lag passes the saturation threshold: nothing
    # this participant says reaches the journal until it comes back down. A state of
    # one room and never of the Salon — the others are neither warned nor blocked.
    blocked: bool = False
    # Story 7.4. How much of the run currently being rendered to this listener has gone
    # by, in seconds of content. Reset at every seam, so it measures one continuous
    # intervention rather than how much somebody has said all evening.
    monologue_seconds: float = 0.0
    # Story 9.3. Whether a broadcast is owed to this listener. Set when the moment comes and
    # spent at the next placement, which may be several messages later — the frequency is
    # the tier's business (FR33) and the placement is this Salon's.
    owes_advert: bool = False
    # Who this listener last actually heard. Their own messages never reach them, so their
    # own identifier can never appear here — which is what keeps two of somebody's messages
    # either side of their own from looking like a change of speaker.
    last_heard: str = ""


class Salon:
    """One conversation, as an orchestrator instance holds it."""

    def __init__(
        self,
        *,
        log: SalonLog,
        rooms: RoomProvisioner,
        max_message_characters: int | None = None,
        host_id: str | None = None,
        condensation_threshold_seconds: float | None = None,
        saturation_threshold_seconds: float | None = None,
        unblock_threshold_seconds: float | None = None,
        monologue_ceiling_seconds: float | None = None,
        video: VideoPath | None = None,
        regie: Regie | None = None,
        settings: SalonSettings | None = None,
    ) -> None:
        # Story 7.1. The persisted parameters supply the operational numbers; either can
        # still be passed directly, which is what the tests do and what keeps a Salon
        # constructible without a settings table behind it. An explicit argument wins,
        # because a caller who named a value meant it.
        settings = settings or SalonSettings()
        self.log = log
        self._rooms = rooms
        self._max_message_characters = (
            max_message_characters
            if max_message_characters is not None
            else settings.max_message_characters
        )
        # Who may cut a microphone. None means nobody can, which is the right default for a
        # Salon whose host has not been declared: the alternative is everybody.
        self._host_id = host_id
        self._condensation_threshold = (
            condensation_threshold_seconds
            if condensation_threshold_seconds is not None
            else settings.condensation_threshold_seconds
        )
        # Story 7.3. Two numbers, never one: reopening at the blocking point is a room
        # that flaps between the two states several times a second. `SalonSettings` refuses
        # a configuration where either sits at or above saturation.
        self._saturation_threshold = (
            saturation_threshold_seconds
            if saturation_threshold_seconds is not None
            else settings.saturation_threshold_seconds
        )
        self._unblock_threshold = (
            unblock_threshold_seconds
            if unblock_threshold_seconds is not None
            else settings.unblock_threshold_seconds
        )
        # Story 7.4. Past this, third-party content may be inserted inside somebody's
        # intervention. No ordering rule ties it to the saturation threshold it happens to
        # start beside: neither silently disables the other, so a rule between them would
        # only refuse configurations that work.
        self._monologue_ceiling = (
            monologue_ceiling_seconds
            if monologue_ceiling_seconds is not None
            else settings.monologue_ceiling_seconds
        )
        # Optional: a deployment without it loses the pictures and nothing else.
        self._video = video
        # Story 9.3. Optional in the same way: a deployment without an exchange hears no
        # advertising and is otherwise identical.
        self._regie = regie
        # Story 6.15. LiveKit publishes speaking state per room; the humans share none, so
        # this is what carries it between them.
        self._speaking = SpeakingBoard()
        self._seats: dict[str, Seat] = {}
        # The language each participant was first heard in. Written once and never revised,
        # like `salon_events.first_spoken_language`: somebody switching language mid-Salon
        # is not a second person and is not introduced again.
        self._first_language: dict[str, str] = {}
        # Everybody who has ever had a seat. The journal outlives the seat, so a late
        # arrival given the history hears what somebody said after they left — and has to
        # be told who said it.
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
        self._speaking.attach(participant.id)

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
        self._speaking.detach(participant_id)
        self.log.detach(participant_id)
        await seat.interpreter.aclose()
        await self._rooms.close(seat.room)

    async def change_mode(self, participant_id: str, interpreter: Interprete) -> None:
        """Swap one participant's adapter, leaving everything around it exactly as it was.

        Everything: the room, so nobody is put through a reconnection; the reading position,
        so nothing is replayed; who they have been introduced to, since that belongs to the
        listener rather than to the adapter; and whatever is held mid-run for them. Only the
        object that speaks changes.

        The reading position is the one worth being careful about. A swap that reset it would
        replay the entire conversation from the beginning, which is a considerably worse
        outcome than the wrong voice for a minute.

        The old adapter is closed. It holds a session to a provider, and leaving it open
        keeps paying for a room nobody is listening to.
        """
        seat = self._seats.get(participant_id)
        if seat is None:
            return

        outgoing = seat.interpreter
        seat.interpreter = interpreter
        await outgoing.aclose()

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

    # ── Saturation (Story 7.3 / FR55) ─────────────────────────────────────────

    @property
    def condensation_threshold_seconds(self) -> float:
        return self._condensation_threshold

    @property
    def saturation_threshold_seconds(self) -> float:
        return self._saturation_threshold

    @property
    def unblock_threshold_seconds(self) -> float:
        return self._unblock_threshold

    @property
    def monologue_ceiling_seconds(self) -> float:
        return self._monologue_ceiling

    def is_saturated(self, participant_id: str) -> bool:
        """Whether this one room has stopped taking words. Never asked of the Salon."""
        seat = self._seats.get(participant_id)
        return seat is not None and seat.blocked

    async def _review_saturation(self, seat: Seat) -> None:
        """Weigh one room's own lag against the two thresholds.

        Called where the lag can have moved: after anything is added to the journal, which
        pushes the head away from every cursor, and after a delivery, which pulls one cursor
        back towards it. Two thresholds and not one — reopening at the blocking point puts
        the room straight back over it, which is a room that flaps rather than a room that
        recovers.

        The signal is spoken on the crossing only. Repeating it for every message afterwards
        would bury the conversation the participant is already struggling to follow.
        """
        lag = self._unheard_seconds(seat)

        if not seat.blocked:
            if lag > self._saturation_threshold:
                seat.blocked = True
                await self._say_busy(seat)
            return

        if lag < self._unblock_threshold:
            # Not announced. Being able to speak again is discovered by speaking, and a
            # notice for it would interrupt the conversation to report that nothing is wrong.
            seat.blocked = False

    def _unheard_seconds(self, seat: Seat) -> float:
        """How much of the conversation this participant has not yet heard.

        Their own words are not part of it. `_render` never says somebody's own message
        back to them, so a long speaker is behind by exactly the amount they just said and
        by nothing they are actually waiting on — measuring the raw lag would have them
        saturate their own room by talking, and block themselves for it.
        """
        participant_id = seat.participant.id
        return sum(
            content_seconds(entry.text)
            for entry in self.log.pending(participant_id)
            if entry.participant_id != participant_id
        )

    async def _say_busy(self, seat: Seat) -> None:
        """Tell one participant their room cannot keep up.

        Never the Salon: one interpreter's lag says nothing about anybody else's, and
        warning a room that is keeping up would tell it something untrue about itself.
        """
        try:
            await seat.interpreter.insert_annonce(
                Annonce(
                    text=vocaliz_is_busy(told_in=seat.participant.language),
                    language=seat.participant.language,
                )
            )
        except InterpreteError:
            # Their adapter has already told them out loud (NFR3). The block still holds —
            # it is about the lag, not about whether the sentence was delivered.
            return

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

        seat = self._seats.get(participant_id)
        if seat is not None and seat.blocked:
            # Told now rather than left talking. Dropping what somebody says in silence
            # leaves them speaking into nothing and finding out much later, if at all.
            await self._say_busy(seat)
            return ()

        self._first_language.setdefault(participant_id, language)

        # The decision was taken above, before any of this landed. An intervention long
        # enough to saturate the room is still recorded whole: `record_intervention` cuts
        # and appends it in one go, so a block that falls due because of it can never take
        # the tail off somebody's sentence.
        recorded = await self.log.record_intervention(
            participant_id=participant_id,
            text=text,
            language=language,
            duration_seconds=duration_seconds,
            max_characters=self._max_message_characters,
        )

        # The head has moved away from every cursor, so every room's lag just grew.
        for other in self._ordered_seats():
            await self._review_saturation(other)

        return recorded

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
            # The cursor has jumped to the end of what was summarised, so this room may
            # well have come back under the reopening threshold.
            await self._review_saturation(seat)
            return

        await self._render(seat, self.log.pending(participant_id))
        await self._review_saturation(seat)

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
        await self._review_saturation(seat)

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

        # Nobody is summarised about their own words. `_render` already refuses to say them
        # back, and a long speaker puts themselves behind by exactly the amount they just
        # said — without this they would be told that one person spoke while they were
        # listening, and given the gist of themselves.
        from_others = tuple(e for e in pending if e.participant_id != participant_id)
        if not from_others:
            await self.log.advance(participant_id, pending[-1].sequence)
            return True

        # Everybody covered counts as introduced: they were named in the summary, and
        # introducing them again with their next sentence would be introducing them twice.
        for entry in from_others:
            seat.introduced.add(entry.participant_id)

        # Said before the summary, not after: afterwards it would explain something the
        # listener has already had to make sense of unaided. Counting people rather than
        # messages is what tells them how much of the room they are getting the gist of.
        await self._announce_condensation(seat, from_others)

        try:
            # Markers are dropped with the rest (Story 6.11): one does not summarise
            # silences, and a summary that reproduced them would spend its time on them.
            await seat.interpreter.condense(
                [_as_tour(entry, spoken_only=True) for entry in from_others]
            )
        except InterpreteError:
            # Their adapter has told them out loud (NFR3). The position does not move, so
            # the backlog is still theirs to catch up on.
            return True

        await self.log.advance(participant_id, pending[-1].sequence)
        # Story 9.3. A summary is not a message from a person, so nothing spans it: the next
        # message is not a change of speaker whatever came before, and an advertisement
        # immediately after being told the gist of four people is not what this listener
        # needs to hear next.
        seat.last_heard = ""
        await self._say_held(seat)
        return True

    async def _announce_condensation(
        self, seat: Seat, covered: tuple[JournalEntry, ...]
    ) -> None:
        """Tell a listener that what follows is the gist, and of how many people.

        Without it a summary is indistinguishable from the conversation having been quiet:
        they hear less than everybody else and have no way of knowing it happened. Failing
        to say it must not cost the summary it introduces, so an adapter that cannot speak
        it is not allowed to stop the catching up — the same rule introductions follow.
        """
        speakers = {entry.participant_id for entry in covered}
        text = condensed_while_listening(len(speakers), told_in=seat.participant.language)
        try:
            await seat.interpreter.insert_annonce(
                Annonce(text=text, language=seat.participant.language)
            )
        except InterpreteError:
            return

    async def _render(self, seat: Seat, entries: tuple[JournalEntry, ...]) -> None:
        participant_id = seat.participant.id

        for entry in entries:
            # Nobody is told what they themselves said. It is the one thing they certainly
            # already know, and a journal every reader reads is exactly what would say it
            # back to them.
            if entry.participant_id != participant_id:
                # Story 9.3. Before the introduction, not after: the introduction belongs to
                # the message it precedes, and an advertisement between "Sofia says" and what
                # Sofia said would be inside that pair rather than between two messages.
                if self._advert_slot(seat, speaker=entry.participant_id):
                    await self._broadcast(seat)
                    # The conversation did not stop while it was read. If that has put this
                    # listener past the threshold, the backlog is said in substance and the
                    # cursor jumps past it — so there is nothing left of this batch to render.
                    if await self._condense_if_far_behind(seat):
                        return

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
                # Story 9.3. Who they last actually heard, which is what makes the next
                # message either a change of speaker or a continuation.
                seat.last_heard = entry.participant_id
                # Story 7.4. One continuous intervention, so it accumulates across the
                # pieces of a run and is cleared at the seam below.
                seat.monologue_seconds += content_seconds(entry.text)

                await self._send_caption(seat, entry)

            await self.log.advance(participant_id, entry.sequence)

            # At a seam, always. Inside a run only once the speaker has gone past the
            # ceiling — until then, cutting a thought in half costs the listener more than
            # a delayed announcement does. Past it, the delay has stopped being a courtesy
            # to the speaker and become a silence imposed on everybody by one of them.
            if self._may_interrupt(seat):
                await self._say_held(seat)

            if not seat.mid_run:
                seat.monologue_seconds = 0.0

    async def deliver_all(self) -> None:
        """Let every interpreter catch up, each at its own pace and none blocking another."""
        for seat in self._ordered_seats():
            await self.deliver(seat.participant.id)

    # ── Announcements ─────────────────────────────────────────────────────────

    async def announce(
        self,
        participant_id: str,
        annonce: Annonce,
        *,
        urgency: Urgency = Urgency.NOTICE,
    ) -> None:
        """Say something to one participant that nobody in the Salon said.

        Held back while their interpreter is between two pieces of one intervention. An
        announcement dropped into the middle of somebody's sentence is worse than the same
        announcement a second later, and the seam is where a listener is least able to tell
        the two speakers apart.

        Unless the intervention has passed the monologue ceiling (Story 7.4). Held with no
        limit, that courtesy becomes the means by which one person makes everybody else
        unreachable — nothing can be said to anybody for as long as they keep talking.
        """
        seat = self._seats.get(participant_id)
        if seat is None:
            return

        seat.held.add(annonce, urgency=urgency)
        if self._may_interrupt(seat):
            await self._say_held(seat)

    # ── Advertising ───────────────────────────────────────────────────────────

    @property
    def regie(self) -> Regie | None:
        return self._regie

    def advertising_due(self, participant_id: str) -> None:
        """The moment to broadcast has come for one listener (FR33).

        It records a debt and nothing more. Nothing is drawn and nothing is said here: the
        advertisement goes at the next placement, which may be several messages away, and
        drawing now would choose against a record of what this listener has heard that is
        already going stale. How often this is called is the tier's business; where the
        result lands is this Salon's.

        Not a coroutine, because nothing about it can fail or wait.
        """
        seat = self._seats.get(participant_id)
        if seat is not None:
            seat.owes_advert = True

    def _advert_slot(self, seat: Seat, *, speaker: str) -> bool:
        """Whether an advertisement may go in immediately before this speaker's message.

        Between two messages from two *different* people. A seam is not enough on its own —
        somebody may carry straight on with a second message, and wedging an advertisement
        between two of their sentences is barely better than cutting one in half. A change of
        speaker is a place a listener already expects to be interrupted at.

        The exception is the monologue ceiling (Story 7.4). Past it there may be no change of
        speaker for a very long time, and honouring the placement rule would mean one person
        talking at length makes the room unreachable — which is the same failure the ceiling
        exists to stop, arriving by another route.
        """
        if not seat.owes_advert:
            return False
        if seat.monologue_seconds > self._monologue_ceiling:
            return True
        if not self._may_interrupt(seat):
            return False
        # An empty `last_heard` is a listener who has heard nothing yet: there is only one
        # message, so there is no *between* to put anything in.
        return bool(seat.last_heard) and seat.last_heard != speaker

    async def _broadcast(self, seat: Seat) -> None:
        """Draw one advertisement and say it. The slot is spent either way.

        Spent whatever came of it — an empty inventory, an unreachable exchange, an adapter
        that could not speak. A debt that survived its own attempt would be retried at every
        boundary for the rest of the Salon, which is how one missed slot becomes a listener
        hearing advertising continuously.
        """
        seat.owes_advert = False
        if self._regie is None:
            return

        try:
            diffusion = await self._regie.draw(
                seat.participant.id, language=seat.participant.language
            )
        except Exception:  # noqa: BLE001
            # Deliberately everything. A Salon must not go down because an advertising
            # exchange did: the conversation is the product, and this is how one tier of it
            # is paid for.
            return

        if diffusion is None:
            return

        try:
            await seat.interpreter.insert_annonce(diffusion.annonce)
        except InterpreteError:
            # Never spoken, so never confirmed and never billed. That is the whole purpose
            # of `ad_broadcasts.delivered_at` being separate from the reservation.
            return

        try:
            await self._regie.delivered(diffusion)
        except Exception:  # noqa: BLE001
            # The listener heard it; the exchange did not hear that they did. Failing
            # towards not billing is the right direction to fail in.
            return

    def _may_interrupt(self, seat: Seat) -> bool:
        """Whether something third-party may be said to this listener right now.

        At a seam, always. Inside a run only once the speaker has gone past the ceiling:
        below it a cut thought costs the listener more than a delayed announcement, and
        above it the delay has stopped being a courtesy to the speaker and become a silence
        imposed on everybody by one of them.
        """
        return not seat.mid_run or seat.monologue_seconds > self._monologue_ceiling

    async def _say_held(self, seat: Seat) -> None:
        """Say everything that was waiting, in the order the queue puts it in (Story 7.6).

        Everything rather than the most urgent one: a slot between two messages is the
        chance to say what is owed, and keeping the rest back for a later slot is how the
        least urgent thing ends up never being said at all.
        """
        for annonce in seat.held.drain():
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
        # Somebody who reaches for this during a red light meant it. Putting the older choice
        # back when the drive ends would overwrite a decision with the one it replaced.
        seat.captions_before = None

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

    # ── Who is speaking (Story 6.15) ──────────────────────────────────────────

    @property
    def speaking_board(self) -> SpeakingBoard:
        return self._speaking

    async def speaking(
        self,
        participant_id: str,
        *,
        human: bool | None = None,
        interpreter: bool | None = None,
    ) -> None:
        """Record what one pair is doing, and show everybody if it changed.

        Everybody, including the pair itself: seeing your own interpreter still red is how
        you know your last sentence has not reached anybody yet.

        Nothing is sent when nothing moved, and nothing is sent to a screen that is black —
        a board nobody can look at costs the same to deliver as one somebody can.
        """
        if participant_id not in self._seats:
            return
        if not self._speaking.set(participant_id, human=human, interpreter=interpreter):
            return

        payload = json.dumps(self._speaking.as_message()).encode()
        for seat in self._ordered_seats():
            if seat.driving:
                continue
            await self._rooms.publish(seat.room, payload)

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
        """FR75. The screen goes black, so everything that exists only to be looked at stops.

        Video is suspended both ways and the wish for it survives. Captions are emptied, and
        that one has a price on it: a translation is paid for per turn, so leaving the
        language set would buy text for a screen nobody is looking at. The speaking board
        stops at the broadcast (`speaking`), since there is no state to suspend.
        """
        seat = self._seats.get(participant_id)
        if seat is None:
            return

        # Only on the way in. Starting twice must not save the emptied state over the real
        # one — the second call would otherwise erase what the first put aside.
        if not seat.driving:
            seat.captions_before = (seat.caption_language, seat.caption_scale)
        seat.driving = True
        seat.caption_language = None
        await self._stop_video(seat)

    async def stop_driving(self, participant_id: str) -> None:
        """Restore what was on before, and nothing that was not.

        They did not choose to stop reading, or to turn the camera off; they chose to start
        driving. Both come back — unless they have chosen otherwise since, which
        `set_captions` records by dropping what was put aside.
        """
        seat = self._seats.get(participant_id)
        if seat is None:
            return

        seat.driving = False
        if seat.captions_before is not None:
            seat.caption_language, seat.caption_scale = seat.captions_before
            seat.captions_before = None
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
