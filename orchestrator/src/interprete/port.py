"""The Interpreter port.

One interpreter per participant, and this is everything the orchestrator is allowed to
know about it. No provider is named here and none ever will be: an adapter is what knows
about a model, a socket and an API key, and the orchestrator is what knows about a Salon.

Four verbs, from Story 6.2:

- `ingest`   — what this interpreter's human just said, for the journal
- `render`   — say a turn of the journal to this interpreter's human, in their language
- `insert_annonce` — say something to this human that nobody said
- `condense` — say the substance of an interval rather than all of it (Story 7.2)

The direction of the dependency is the point. `InterpreteS2S` and, in Story 6.7,
`InterpreteBase` implement this; the orchestrator imports this and nothing below it.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Awaitable, Callable, NoReturn, Protocol, Sequence

logger = logging.getLogger("orchestrator")

# A voice that does not go through the interpreter's own provider — see `_notify` below.
FallbackVoice = Callable[[str, str], Awaitable[None]]


@dataclass(frozen=True)
class Participant:
    """A human in a Salon, and the language they speak and are spoken to in."""

    id: str
    language: str
    name: str | None = None


@dataclass(frozen=True)
class Tour:
    """One thing one participant said, in the language they said it in.

    The original, never overwritten — the speaker makes it. `sequence` is the position in
    the journal, assigned on arrival at the orchestrator (Story 6.3) and therefore unknown
    to the interpreter that produced it.
    """

    participant_id: str
    text: str
    language: str
    sequence: int | None = None


@dataclass(frozen=True)
class Annonce:
    """Something said to one participant that nobody in the Salon said.

    Already in that participant's language — the orchestrator composes it for them, so
    there is nothing left to translate. It never enters the journal.
    """

    text: str
    language: str


@dataclass(frozen=True)
class Utterance:
    """What an interpreter asks its voice to say, and in which language.

    The text is handed over as it stands, together with the language to say it in. An
    adapter that can translate and speak in one movement — which is the whole point of
    speech-to-speech — must not be given a string somebody else has already translated.
    """

    text: str
    language: str
    # The language the text is in now. Empty when there is no single one, as for a
    # condensation covering an interval spoken in several.
    source_language: str = ""
    kind: str = "tour"
    covers: tuple[Tour, ...] = ()

    @property
    def spoken_text(self) -> str:
        """What a voice is actually given to say.

        The metadata markers of Story 6.11 are stripped out here, at the last possible
        moment. They are instructions about *how* to say the rest — a silence to leave —
        and pronouncing "[pause=4000]" at somebody is the one outcome nothing may produce.
        """
        from src.journal.cleaning import without_markers

        return without_markers(self.text)

    @property
    def pause_seconds(self) -> float:
        """How long to stay quiet while saying it.

        An indication of intent rather than a constraint to the hundredth: an interpreter
        applies it idiomatically in its own language, where the same beat may be shorter or
        longer than the one the speaker left.
        """
        from src.journal.cleaning import pause_seconds

        return pause_seconds(self.text)

    @property
    def verbatim(self) -> bool:
        """True when nothing has to be translated and the voice is only being asked to
        say it. A turn already in the listener's language costs no model call, which is why
        the price of a Salon follows the number of languages in it and not its length."""
        return bool(self.source_language) and self.source_language == self.language


class RealtimeSession(Protocol):
    """An audio↔audio session with one human, as `InterpreteS2S` needs it.

    Declared structurally and on purpose: the worker that hosts the adapter builds the real
    one out of its own SDK, and nothing of that SDK has to be importable here for the
    adapter to be written or tested.
    """

    def supports(self, language: str) -> bool: ...

    async def listen(self) -> tuple[str, str] | None: ...

    async def speak(self, utterance: Utterance) -> None: ...

    async def aclose(self) -> None: ...


# ── Typed failures ────────────────────────────────────────────────────────────


class InterpreteError(Exception):
    """Anything an interpreter can fail at, under one name.

    Carries who it happened to and never what was said: this reaches a log, and Story 6.12
    asks for identifiers and lengths rather than content.
    """

    def __init__(self, participant_id: str, message: str) -> None:
        self.participant_id = participant_id
        super().__init__(f"{message} (participant={participant_id})")


class ProviderUnavailable(InterpreteError):
    """The model behind this interpreter did not answer (NFR3)."""


class UnsupportedLanguage(InterpreteError):
    """This adapter does not speak that language.

    A decision rather than a breakdown, and Story 6.7 is where it is acted on: the languages
    the product offers are the intersection of what its adapters speak, never their union.
    """

    def __init__(self, participant_id: str, language: str) -> None:
        self.language = language
        super().__init__(participant_id, f"language {language!r} is not spoken here")


# What a participant hears when their interpreter cannot answer. Written out per language
# rather than translated on demand, because the thing that would translate it is precisely
# what has just stopped working. English when the language is not one of these — an
# apology in the wrong language still says something is wrong, silence says nothing.
_NOTICES = {
    "fr": "Un instant, je n'arrive plus à suivre la conversation. J'essaie de revenir.",
    "en": "One moment — I have lost the conversation. I am trying to get it back.",
    "es": "Un momento, he perdido la conversación. Estoy intentando recuperarla.",
    "de": "Einen Moment, ich habe das Gespräch verloren. Ich versuche es wiederherzustellen.",
    "pt": "Um momento, perdi a conversa. Estou a tentar recuperá-la.",
    "it": "Un momento, ho perso la conversazione. Sto cercando di riprenderla.",
}


def notice_for(language: str) -> str:
    return _NOTICES.get(language.split("-")[0].lower(), _NOTICES["en"])


# ── The port ──────────────────────────────────────────────────────────────────


@dataclass
class Interprete(ABC):
    """One participant's interpreter.

    A dataclass so that every adapter declares the same two things — whose interpreter it
    is, and what voice to use when its own provider is down — without repeating a
    constructor four times.
    """

    participant: Participant
    fallback_voice: FallbackVoice | None = field(default=None, kw_only=True)

    @abstractmethod
    async def ingest(self) -> Tour | None:
        """Wait for the next thing this human says, cleaned, in the language they said it
        in. `None` once their room is closed — leaving is the ordinary end of a Salon, not
        a failure."""

    @abstractmethod
    async def render(self, tour: Tour) -> None:
        """Say a turn of the journal to this human, in their own language."""

    @abstractmethod
    async def insert_annonce(self, annonce: Annonce) -> None:
        """Say something to this human that nobody in the Salon said."""

    @abstractmethod
    async def condense(self, tours: Sequence[Tour]) -> None:
        """Say the substance of an interval instead of all of it. Nothing for an empty
        interval: an interpreter announcing a summary of nothing is worse than silence."""

    async def aclose(self) -> None:
        """Release whatever this interpreter holds. Idempotent — shutdown runs on a drain
        and again when the participant leaves."""

    # ── For adapters ─────────────────────────────────────────────────────────

    async def _fail(self, error: Exception) -> NoReturn:
        """Tell the participant out loud, then hand the orchestrator a typed error.

        Both halves of NFR3. Somebody in headphones has no screen to check and no second
        voice to ask: an interpreter that goes quiet is indistinguishable from a room where
        everyone has stopped talking.
        """
        await self._notify(notice_for(self.participant.language))
        raise ProviderUnavailable(
            self.participant.id, "the interpreter's provider did not answer"
        ) from error

    async def _notify(self, text: str) -> None:
        """Speak out of band. Never through the provider that has just failed, and never
        raising: a fallback voice that is broken too is not a reason to lose the error that
        got us here."""
        if self.fallback_voice is None:
            return
        try:
            await self.fallback_voice(text, self.participant.language)
        except Exception:  # noqa: BLE001 — the original failure is the one that matters
            logger.warning(
                "could not tell participant=%s that their interpreter is down",
                self.participant.id,
            )
