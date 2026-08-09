"""The journal of a Salon: every message, in the language it was spoken in.

There is one of these per Salon and it is the only structure of messages there is. Not a
queue — a message is rendered once per participant, at a rhythm each interpreter sets for
itself, so there is no moment at which it has been consumed and could be dropped. What
moves through the journal is the readers, not the messages.

Everything else follows from that. Entries are appended and never touched again, positions
live outside in `Cursors`, and reading is a pure function of a position.
"""
from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone

from src.journal.cleaning import pause_seconds, without_markers

# Characters of speech per second, used when nobody supplies a real duration.
#
# Roughly 150 words a minute at five characters a word — conversational speech, near enough
# across the languages this is likely to see. The absolute value matters less than it looks:
# lag is compared against thresholds that are themselves tuned against it, and every
# interpreter is measured the same way.
CHARACTERS_PER_SECOND = 12.5


def content_seconds(text: str) -> float:
    """How long a piece of text takes to say, when nobody measured it.

    An interpreter that knows how long its human actually spoke should say so. This is the
    stand-in, and its virtue is consistency rather than accuracy.
    """
    # The words at speaking pace, plus every silence in full. A marker is not spoken, but
    # the pause it stands for occupies real time when it is restituted (Story 6.11) — so it
    # counts against every reader who has not reached it yet.
    return len(without_markers(text)) / CHARACTERS_PER_SECOND + pause_seconds(text)


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


@dataclass(frozen=True)
class JournalEntry:
    """One message, as it was spoken, at the position it arrived in.

    Frozen on purpose: the speaker makes the original, and nothing downstream — no
    translation, no cleaning, no summary — may write over it.
    """

    sequence: int
    participant_id: str
    text: str
    language: str
    arrived_at: datetime
    duration_seconds: float
    # Where this message sits in the intervention it was cut out of (Story 6.5). One of one
    # for anything short enough not to have been cut, which is nearly everything.
    part: int = 1
    parts: int = 1

    @property
    def mid_run(self) -> bool:
        """True while more of the same intervention is still to come.

        What it guards: nothing third-party — no announcement — is spoken into the gap
        between two halves of somebody's sentence.
        """
        return self.part < self.parts


def arrival_key(entry: JournalEntry) -> tuple[datetime, int]:
    """How two messages are ordered against each other: when they arrived, then where they
    landed.

    The timestamp is what decides, and the position settles the ties — of which there are
    many. A clock has finite resolution, two rooms can hand over a message inside the same
    microsecond, and the pieces of one split intervention deliberately share a single
    instant. Sorting on the timestamp alone would leave those free to shuffle, and a
    conversation that reorders itself between two readings is not a record of anything.

    Note what this is not: it is not how the journal is read. Reading follows the positions,
    which are monotone whatever the clock does — NTP moves a drifting clock backwards, and
    what was already said must not become something said later. This is for comparing
    messages that did not come from the same journal.
    """
    return (entry.arrived_at, entry.sequence)


@dataclass
class Journal:
    """A Salon's messages, in arrival order."""

    salon_id: str
    now: Callable[[], datetime] = _utcnow
    _entries: list[JournalEntry] = field(default_factory=list, repr=False)

    @property
    def entries(self) -> tuple[JournalEntry, ...]:
        return tuple(self._entries)

    @property
    def head(self) -> int:
        """The last position assigned. Zero for a Salon in which nobody has spoken."""
        return self._entries[-1].sequence if self._entries else 0

    def append(
        self,
        *,
        participant_id: str,
        text: str,
        language: str,
        duration_seconds: float | None = None,
    ) -> JournalEntry | None:
        """Add a message, in the language it was spoken in, stamped on arrival.

        None for an empty one — silence taken for speech, or a cleaning pass (Story 6.11)
        that removed everything there was. Either way there is nothing to render to
        anybody, and a position it occupied would be a position that renders as silence.
        """
        text = (text or "").strip()
        if not text:
            return None

        entry = JournalEntry(
            sequence=self.head + 1,
            participant_id=participant_id,
            text=text,
            language=language,
            arrived_at=self.now(),
            duration_seconds=(
                content_seconds(text) if duration_seconds is None else duration_seconds
            ),
        )
        self._entries.append(entry)
        return entry

    def append_run(
        self,
        *,
        participant_id: str,
        texts: Sequence[str],
        language: str,
        duration_seconds: float | None = None,
    ) -> tuple[JournalEntry, ...]:
        """Add the pieces of one intervention, at consecutive positions.

        In one call, and with no await anywhere in it, which is the whole mechanism behind
        the acceptance criterion: the positions are handed out together, so there is no gap
        for another participant's message to land in.

        A supplied duration is the whole intervention's, shared out in proportion to what
        each piece holds. The lag of Story 7.2 is measured on these, and charging one piece
        with the length of the lot would misreport every reader behind it.
        """
        kept = [stripped for stripped in (text.strip() for text in texts) if stripped]
        if not kept:
            return ()

        total_characters = sum(len(text) for text in kept)
        # One instant for the whole intervention: it was said in one breath, and Story 6.6
        # settles order on arrival at the orchestrator, which happened once.
        arrived_at = self.now()
        entries: list[JournalEntry] = []

        for index, text in enumerate(kept, start=1):
            if duration_seconds is None:
                share = content_seconds(text)
            else:
                share = duration_seconds * len(text) / total_characters

            entry = JournalEntry(
                sequence=self.head + 1,
                participant_id=participant_id,
                text=text,
                language=language,
                arrived_at=arrived_at,
                duration_seconds=share,
                part=index,
                parts=len(kept),
            )
            self._entries.append(entry)
            entries.append(entry)

        return tuple(entries)

    def restore(self, entries: tuple[JournalEntry, ...]) -> None:
        """Put back what was read from storage, in place of whatever is here.

        Used by a takeover, before anybody reads. Numbering carries on from the last entry
        restored, so a resumed Salon does not reuse a position.
        """
        self._entries = sorted(entries, key=lambda entry: entry.sequence)

    def after(self, position: int) -> tuple[JournalEntry, ...]:
        """Everything a reader at `position` has not been given yet.

        Reading takes nothing away: three participants read the same message three times.
        """
        return tuple(entry for entry in self._entries if entry.sequence > position)

    def lag_seconds(self, position: int) -> float:
        """How far behind the head a reader at `position` is, in seconds of content.

        Seconds of content and not of clock: an interpreter that has said nothing for a
        minute because nobody spoke is not behind, it has nothing to say. The cleaning of
        Story 6.11 happens before this, so a room's lag falls when the "euh" go — for every
        room at once, because it was done at ingestion rather than per listener.
        """
        return sum(entry.duration_seconds for entry in self.after(position))

    def content_seconds_between(self, start: int, end: int) -> float:
        """The content of the span (start, end], in seconds."""
        return sum(
            entry.duration_seconds
            for entry in self._entries
            if start < entry.sequence <= end
        )
