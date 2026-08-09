"""The speech-to-speech adapter.

A human alone in a room with a realtime audio↔audio model. They speak, the model hears
them; the model speaks, they hear it. Nothing inside that room is text — the text this
adapter exchanges with the orchestrator is what *leaves* the room, so that the other
participants, who each have a room and an interpreter of their own, can be given it in
their own language.

That is also why translation is not a step here. A turn in another language is handed to
the model as it was spoken, together with the language to say it in, and the model does
both at once. Translating first and then asking for the result to be read out would add a
hop, a delay and a voice that has lost the tone of the original.

No provider SDK is imported. The session is supplied by whatever hosts this adapter — the
interpreter worker — and only has to answer the `RealtimeSession` shape.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from src.interprete.port import (
    Annonce,
    Interprete,
    ProviderUnavailable,
    RealtimeSession,
    Tour,
    UnsupportedLanguage,
    Utterance,
)


@dataclass
class InterpreteS2S(Interprete):
    session: RealtimeSession = field(kw_only=True)
    closed: bool = field(default=False, kw_only=True)

    async def ingest(self) -> Tour | None:
        if self.closed:
            return None

        try:
            heard = await self.session.listen()
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
        # Already composed in this participant's language by the orchestrator, so the model
        # is asked to say it and not to render it — translating it again would be
        # translating a translation.
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

        # The interval goes to the model whole, with what it covers. Summarising here and
        # handing over the result would put a text step back in the middle of the room, and
        # would summarise in a language the participant does not necessarily read.
        await self._speak(
            Utterance(
                text="\n".join(tour.text for tour in covered),
                language=self.participant.language,
                kind="condense",
                covers=covered,
            )
        )

    async def aclose(self) -> None:
        if self.closed:
            return

        self.closed = True
        await self.session.aclose()

    async def _speak(self, utterance: Utterance) -> None:
        if self.closed:
            raise ProviderUnavailable(self.participant.id, "the interpreter is closed")
        if not self.session.supports(utterance.language):
            raise UnsupportedLanguage(self.participant.id, utterance.language)

        try:
            await self.session.speak(utterance)
        except Exception as error:  # noqa: BLE001 — any provider failure, under one name
            await self._fail(error)
