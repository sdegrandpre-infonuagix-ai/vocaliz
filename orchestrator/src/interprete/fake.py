"""An interpreter with no provider behind it.

Named in Story 7.2, which asks that condensation be verifiable "de façon déterministe" —
and that is what this is for. It answers the port exactly as the speech-to-speech adapter
does, with a queue where the model would be, so the orchestrator's own behaviour can be
tested without a socket, an API key or a second of latency.

It is production code rather than a test fixture on purpose: it lives beside the adapters
because it is one, and because the day it drifts from the port is the day the orchestrator
tests stop meaning anything.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from src.interprete.port import Annonce, Interprete, Tour, UnsupportedLanguage, Utterance


@dataclass
class InterpreteFake(Interprete):
    """A deterministic interpreter: what goes into `queue` comes out of `ingest`, and
    everything it says is recorded in `spoken` rather than heard by anybody."""

    # What its human is going to say, in order.
    heard: list[tuple[str, str]] = field(default_factory=list)
    # Everything it has said out loud, in order.
    spoken: list[Utterance] = field(default_factory=list)
    # Languages it refuses, so Story 6.7's intersection has something to bite on.
    unsupported: set[str] = field(default_factory=set)
    # Set to raise from the next provider call, standing in for a model that stops
    # answering. The whole point is that it fails on demand rather than by luck.
    fail_with: Exception | None = None
    # Public, and spelled the same way as on `InterpreteS2S`: whether an interpreter is
    # still open is something the Salon asks of every adapter, so it cannot be private on
    # one of them.
    closed: bool = field(default=False, kw_only=True)

    # ── Driving it ────────────────────────────────────────────────────────────

    def queue(self, text: str, *, language: str) -> None:
        """Line up something for its human to say."""
        self.heard.append((text, language))

    def close_room(self) -> None:
        """Its human has gone. `ingest` returns None from here on."""
        self.closed = True

    # ── The port ──────────────────────────────────────────────────────────────

    async def ingest(self) -> Tour | None:
        if self.fail_with is not None:
            await self._fail(self.fail_with)
        if self.closed or not self.heard:
            return None

        text, language = self.heard.pop(0)
        return Tour(participant_id=self.participant.id, text=text, language=language)

    async def render(self, tour: Tour) -> None:
        await self._say(
            Utterance(
                text=tour.text,
                language=self.participant.language,
                source_language=tour.language,
                kind="tour",
            )
        )

    async def insert_annonce(self, annonce: Annonce) -> None:
        await self._say(
            Utterance(
                text=annonce.text,
                language=self.participant.language,
                source_language=annonce.language,
                kind="annonce",
            )
        )

    async def condense(self, tours: Sequence[Tour]) -> None:
        if not tours:
            return

        # Deterministic and obviously not a real summary — a test that asserted on prose
        # would be asserting on a model's mood. What matters is that one thing is said in
        # place of many, and that it says how many.
        await self._say(
            Utterance(
                text=f"[condensé de {len(tours)} tours]",
                language=self.participant.language,
                kind="condense",
                covers=tuple(tours),
            )
        )

    async def aclose(self) -> None:
        self.closed = True

    async def _say(self, utterance: Utterance) -> None:
        if utterance.language in self.unsupported:
            raise UnsupportedLanguage(self.participant.id, utterance.language)
        if self.fail_with is not None:
            await self._fail(self.fail_with)
        self.spoken.append(utterance)
