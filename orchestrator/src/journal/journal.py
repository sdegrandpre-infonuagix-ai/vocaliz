"""The journal of a Salon: every message, in the language it was spoken in.

There is one of these per Salon and it is the only structure of messages there is. Not a
queue — a message is rendered once per participant, at a rhythm each interpreter sets for
itself, so there is no moment at which it has been consumed and could be dropped. What
moves through the journal is the readers, not the messages.

Everything else follows from that. Entries are appended and never touched again, positions
live outside in `Cursors`, and reading is a pure function of a position.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone

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
    return len(text.strip()) / CHARACTERS_PER_SECOND


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
