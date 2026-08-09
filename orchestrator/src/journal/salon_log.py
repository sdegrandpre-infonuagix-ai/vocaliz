"""One Salon, held by the orchestrator: its journal, its readers and its translations.

This is the object an instance holds one of per Salon, and the reason Story 6.1 could say
that affinity between a Salon and its instance is a preference rather than a condition of
survival. Everything is written as it happens, so another instance re-reads it and carries
on.

What carrying on has to mean, exactly: no loss and no duplication. A message rendered
before the crash is not rendered again — hearing the same sentence twice is worse than
hearing it late, because a listener cannot tell a repeat from somebody saying the same
thing again — and a message not yet reached is still waiting.

Readers are identified by a plain string. The journal has no opinion about what an
interpreter is, and one reader per participant is a fact of Story 6.4 rather than of this
one.
"""
from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from src.journal.cursors import Cursors
from src.journal.journal import Journal, JournalEntry, _utcnow
from src.journal.store import JournalStore
from src.journal.translations import Translate, Translations


class SalonLog:
    """A Salon's journal, the position of every reader in it, and what has been translated."""

    def __init__(
        self,
        *,
        salon_id: str,
        store: JournalStore,
        translate: Translate,
        now: Callable[[], datetime] = _utcnow,
    ) -> None:
        self.salon_id = salon_id
        self._store = store
        self._journal = Journal(salon_id=salon_id, now=now)
        self._cursors = Cursors()
        # Positions set by `attach`, which is synchronous and so cannot write. Flushed by
        # `checkpoint`; `advance` writes as it goes and never leaves anything here.
        self._unwritten: set[str] = set()
        self._translations = Translations(translate=translate, on_new=self._remember)

    @classmethod
    async def resume(
        cls,
        *,
        salon_id: str,
        store: JournalStore,
        translate: Translate,
        now: Callable[[], datetime] = _utcnow,
    ) -> SalonLog:
        """Take a Salon over by re-reading it.

        Everything needed is in storage: the messages, where each reader had got to, and
        what has already been translated. Rendering resumes at each position — nothing
        repeated, nothing skipped — and no translation is paid for twice.
        """
        log = cls(salon_id=salon_id, store=store, translate=translate, now=now)
        state = await store.load(salon_id)

        log._journal.restore(state.entries)
        log._cursors = Cursors(state.cursors)
        log._translations = Translations(
            translate=translate, cache=state.translations, on_new=log._remember
        )
        return log

    # ── The journal ───────────────────────────────────────────────────────────

    @property
    def entries(self) -> tuple[JournalEntry, ...]:
        return self._journal.entries

    @property
    def head(self) -> int:
        return self._journal.head

    async def record(
        self,
        *,
        participant_id: str,
        text: str,
        language: str,
        duration_seconds: float | None = None,
    ) -> JournalEntry | None:
        """Add what an interpreter produced, in the language it was spoken in.

        Written before it reaches anybody: an instance dying between the arrival of a
        message and its first rendering must not take the message with it.
        """
        entry = self._journal.append(
            participant_id=participant_id,
            text=text,
            language=language,
            duration_seconds=duration_seconds,
        )
        if entry is None:
            return None

        await self._store.append_entry(self.salon_id, entry)
        return entry

    # ── Readers ───────────────────────────────────────────────────────────────

    @property
    def readers(self) -> tuple[str, ...]:
        return self._cursors.readers

    def attach(self, reader_id: str, *, from_start: bool = False) -> int:
        """Start following this Salon, and say from where.

        At the head by default — somebody arriving hears what is said from now on. From the
        beginning when Story 6.10 has the host grant them the history, which needs no
        mechanism of its own beyond this position.
        """
        position = self._cursors.place(reader_id, 0 if from_start else self.head)
        self._unwritten.add(reader_id)
        return position

    def detach(self, reader_id: str) -> None:
        """Stop waiting for this reader. Their position stays in storage — a participant
        who drops off a bad connection comes back to where they were."""
        self._cursors.remove(reader_id)
        self._unwritten.discard(reader_id)

    def cursor(self, reader_id: str) -> int:
        return self._cursors.position_of(reader_id, default=self.head)

    def pending(self, reader_id: str) -> tuple[JournalEntry, ...]:
        """What this reader has not been given yet. Reading takes nothing away."""
        return self._journal.after(self.cursor(reader_id))

    async def advance(self, reader_id: str, position: int) -> int:
        """Move a position forward and write it, so a takeover starts in the right place.

        Never backwards: a late acknowledgement arriving out of order would replay what has
        already been said.
        """
        moved = self._cursors.advance(reader_id, position, head=self.head)
        self._unwritten.discard(reader_id)
        await self._store.save_cursor(self.salon_id, reader_id, moved)
        return moved

    def lag_seconds(self, reader_id: str) -> float:
        """The distance from this reader's position to the head, in seconds of content —
        what Story 7.2 weighs against its condensation threshold."""
        return self._journal.lag_seconds(self.cursor(reader_id))

    async def checkpoint(self) -> None:
        """Write the positions `attach` could not.

        Without it a reader that joined and crashed before rendering anything would come
        back at the head of a journal it had been granted the history of.
        """
        for reader_id in sorted(self._unwritten):
            position = self._cursors.position_of(reader_id)
            await self._store.save_cursor(self.salon_id, reader_id, position)
        self._unwritten.clear()

    # ── Language ──────────────────────────────────────────────────────────────

    async def render(self, entry: JournalEntry, language: str) -> str:
        """One message, in one reader's language. See `translations.py` for the two rules."""
        return await self._translations.render(entry, language)

    async def _remember(self, sequence: int, language: str, text: str) -> None:
        await self._store.save_translation(self.salon_id, sequence, language, text)
