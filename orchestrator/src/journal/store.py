"""Where a Salon's journal, positions and translations are kept (NFR8).

The port, and an implementation that keeps everything in the process. The durable one
belongs with the database and is not this story's business — what matters here is that
nothing above this line knows which of the two it is talking to.

Writing is why an instance is replaceable. Story 6.1 could say that affinity between a
Salon and the instance hosting it is a preference rather than a condition of survival
precisely because of what is written here, as it happens: another instance re-reads it and
carries on without loss and without repeating itself.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from src.journal.journal import JournalEntry


@dataclass(frozen=True)
class SalonState:
    """Everything needed to take a Salon over."""

    entries: tuple[JournalEntry, ...] = ()
    cursors: dict[str, int] = field(default_factory=dict)
    translations: dict[tuple[int, str], str] = field(default_factory=dict)


class JournalStore(Protocol):
    """What a Salon's log needs of its storage, and nothing else."""

    async def append_entry(self, salon_id: str, entry: JournalEntry) -> None:
        """Write one message. Never called twice for the same position."""

    async def save_cursor(self, salon_id: str, interpreter_id: str, position: int) -> None:
        """Write where one interpreter has got to."""

    async def save_translation(
        self, salon_id: str, sequence: int, language: str, text: str
    ) -> None:
        """Write one rendering of one message."""

    async def load(self, salon_id: str) -> SalonState:
        """Read a Salon back. Empty for one nothing has been written for."""


class InMemoryJournalStore:
    """A store that survives nothing.

    For tests and for a developer's machine, where the point of Story 6.1 was that the
    orchestrator starts with no database and no AWS account. It answers the port exactly,
    so what is written against it works unchanged against the durable one.
    """

    def __init__(self) -> None:
        self._entries: dict[str, list[JournalEntry]] = {}
        self._cursors: dict[str, dict[str, int]] = {}
        self._translations: dict[str, dict[tuple[int, str], str]] = {}

    async def append_entry(self, salon_id: str, entry: JournalEntry) -> None:
        self._entries.setdefault(salon_id, []).append(entry)

    async def save_cursor(self, salon_id: str, interpreter_id: str, position: int) -> None:
        self._cursors.setdefault(salon_id, {})[interpreter_id] = position

    async def save_translation(
        self, salon_id: str, sequence: int, language: str, text: str
    ) -> None:
        self._translations.setdefault(salon_id, {})[(sequence, language)] = text

    async def load(self, salon_id: str) -> SalonState:
        return SalonState(
            entries=tuple(self._entries.get(salon_id, ())),
            cursors=dict(self._cursors.get(salon_id, {})),
            translations=dict(self._translations.get(salon_id, {})),
        )
