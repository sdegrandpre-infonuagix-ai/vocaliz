"""The Base adapter: transcribe, render, synthesise.

The same four verbs as every other adapter, over three collaborators instead of one. A
realtime model hears a human and answers in voice in a single movement; here speech becomes
text, text is rendered into the listener's language, and text becomes speech again.

That difference is the tier. It is cheaper, it is a little slower, and it can fail in three
places rather than one — but the orchestrator cannot tell, which is the acceptance
criterion and the reason the port exists.

One rule is shared with the journal and worth stating again here: nothing already in the
listener's language goes near the renderer. A Salon held in one language pays for
transcription and synthesis and for no rendering at all.

No provider SDK, as everywhere under `src/`. The three collaborators are shapes; the worker
that hosts the adapter builds them out of real services.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, Sequence

from src.interprete.port import (
    Annonce,
    Interprete,
    ProviderUnavailable,
    Tour,
    UnsupportedLanguage,
    Utterance,
)


class SpeechToText(Protocol):
    """Speech in; text and the language it was spoken in, out."""

    async def transcribe(self) -> tuple[str, str] | None: ...

    async def aclose(self) -> None: ...


class LanguageModel(Protocol):
    """The text step in the middle, which speech-to-speech does not have at all."""

    async def render(self, text: str, *, source: str, target: str) -> str: ...

    async def condense(self, texts: Sequence[str], *, target: str) -> str:
        """The substance of an interval, in the listener's language (Story 7.2)."""


class TextToSpeech(Protocol):
    """Text out loud, in a synthetic voice.

    Given both the `Utterance` — what was asked for, in the shape every adapter produces —
    and the words to pronounce, which are what came back from the model. They differ
    whenever something had to be rendered, and a voice that wants to choose its delivery by
    kind or language needs the first as well as the second.
    """

    def speaks(self, language: str) -> bool: ...

    async def say(self, utterance: Utterance, words: str) -> None: ...

    async def aclose(self) -> None: ...


@dataclass
class InterpreteBase(Interprete):
    """The Interpreter port over a transcribe-render-synthesise chain."""

    stt: SpeechToText = field(kw_only=True)
    llm: LanguageModel = field(kw_only=True)
    tts: TextToSpeech = field(kw_only=True)
    closed: bool = field(default=False, kw_only=True)

    async def ingest(self) -> Tour | None:
        if self.closed:
            return None

        try:
            heard = await self.stt.transcribe()
        except Exception as error:  # noqa: BLE001 — any provider failure, under one name
            await self._fail(error)

        if heard is None:
            return None

        text, language = heard
        return Tour(participant_id=self.participant.id, text=text, language=language)

    async def render(self, tour: Tour) -> None:
        await self._speak(
            Utterance(
                text=tour.text,
                language=self.participant.language,
                source_language=tour.language,
                kind="tour",
            )
        )

    async def insert_annonce(self, annonce: Annonce) -> None:
        # Composed in this participant's language by the orchestrator, so there is nothing
        # to render — passing it through the model would be translating a translation.
        await self._speak(
            Utterance(
                text=annonce.text,
                language=annonce.language,
                source_language=annonce.language,
                kind="annonce",
            )
        )

    async def condense(self, tours: Sequence[Tour]) -> None:
        covered = tuple(tours)
        if not covered:
            return

        # The interval goes to the model whole and comes back as one thing to say: a
        # summary made turn by turn is not a summary. No single source language applies to
        # an interval several people spoke in, so none is claimed.
        await self._speak(
            Utterance(
                text="\n".join(tour.text for tour in covered),
                language=self.participant.language,
                kind="condense",
                covers=covered,
            ),
            words=lambda: self.llm.condense(
                [tour.text for tour in covered], target=self.participant.language
            ),
        )

    async def aclose(self) -> None:
        """Shut the chain down. The model is stateless; the other two hold connections."""
        if self.closed:
            return

        self.closed = True
        await self.stt.aclose()
        await self.tts.aclose()

    async def _speak(self, utterance: Utterance, *, words=None) -> None:
        """The single route to the voice, so neither check below can be skipped.

        `words` is how a condensation supplies its own text; everything else derives it
        from the utterance — unchanged when it is already in the right language, through
        the model when it is not.
        """
        if self.closed:
            raise ProviderUnavailable(self.participant.id, "the interpreter is closed")
        # Checked before the model, not after: no point paying to produce text that nothing
        # can then read out.
        if not self.tts.speaks(utterance.language):
            raise UnsupportedLanguage(self.participant.id, utterance.language)

        try:
            if words is not None:
                spoken = await words()
            elif utterance.verbatim:
                spoken = utterance.text
            else:
                spoken = await self.llm.render(
                    utterance.text,
                    source=utterance.source_language,
                    target=utterance.language,
                )

            await self.tts.say(utterance, spoken)
        except Exception as error:  # noqa: BLE001 — any provider failure, under one name
            await self._fail(error)
