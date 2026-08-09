"""Rendering a message into another language, at most once, always from the original.

Two rules do all the work here.

A translation is one hop from what was actually said. Never a translation of a
translation: a chain compounds its own errors, and the third listener ends up being told
something the speaker never said.

And the pair (message, language) is produced once, however many people ask for it. Three
participants listening in French share one translation, so the cost of a Salon follows the
number of languages in it rather than the number of people or the number of turns.

The corollary is the one worth stating: a Salon held in a single language never touches
this at all.
"""
from __future__ import annotations

from typing import Awaitable, Callable, Protocol

from src.journal.journal import JournalEntry

# Rendering text from one language into another. A port like the others — no provider is
# named. Note that the speech-to-speech adapter never comes through here: it hands the
# original to its own model and gets voice back in one movement. This is for what has to
# exist as text, which is captions (Story 6.14) and the Base adapter (Story 6.7).
Translate = Callable[..., Awaitable[str]]


class OnNewTranslation(Protocol):
    async def __call__(self, sequence: int, language: str, text: str) -> None: ...


def _base(language: str) -> str:
    """The language without its region. fr-CA and fr are the same language to translate
    between, and paying to turn French into French would also risk it coming back quietly
    rephrased."""
    return language.split("-")[0].lower()


class Translations:
    """The translations of one Salon, keyed on the pair."""

    def __init__(
        self,
        *,
        translate: Translate,
        cache: dict[tuple[int, str], str] | None = None,
        on_new: OnNewTranslation | None = None,
    ) -> None:
        self._translate = translate
        self._cache: dict[tuple[int, str], str] = dict(cache or {})
        self._on_new = on_new

    async def render(self, entry: JournalEntry, target: str) -> str:
        """One message, in one language.

        The original as it stands whenever there is nothing to do — and nothing is stored
        in that case, because storing a copy of the text under another name would be a
        claim about where it came from that is not true.
        """
        # "" is a choice in its own right: as spoken, translate nothing. Distinct from
        # never having chosen, which is what NULL means in `caption_language`.
        if not target:
            return entry.text

        # A message with no declared language is left to the translator, which detects the
        # source itself. It must not be guessed at here.
        if entry.language and _base(entry.language) == _base(target):
            return entry.text

        key = (entry.sequence, target)
        if key in self._cache:
            return self._cache[key]

        # From `entry.text`, always — the original, never another rendering of it.
        text = await self._translate(entry.text, source=entry.language, target=target)
        self._cache[key] = text

        # Announced on production and not on every read: a popular language would otherwise
        # be written to storage once per listener.
        if self._on_new is not None:
            await self._on_new(entry.sequence, target, text)

        return text

    def cached(self, sequence: int) -> dict[str, str]:
        """Every language one message has already been rendered into."""
        return {
            language: text
            for (cached_sequence, language), text in self._cache.items()
            if cached_sequence == sequence
        }

