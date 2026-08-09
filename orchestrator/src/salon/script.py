"""What the orchestrator owes one listener, written down instead of spoken.

The consequence of the text-only boundary. `Salon.deliver()` used to call
`interprete.render()` directly, which was an in-memory call between two objects in one
process; with the interpreter moved into the agent that call would have to cross a network,
and a network hop per turn of speech is exactly what a realtime product cannot pay.

So the direction reverses. The orchestrator stops driving anybody and starts answering a
question — *what do I owe my human?* — with an ordered list of lines. The agent says them
with its own interpreter, which is sitting in the same process as the audio.

**A `Script` is a `Voice` that records.** That is the whole trick, and it is why none of the
conductor's logic had to be rewritten to invert it. The advert slots, the introductions, the
condensation threshold, the monologue ceiling, the held announcements — all of it runs
unchanged and lands here instead of in a socket. One code path produces both the in-process
delivery and the served script, so the two cannot drift.

Nothing here is audio, and nothing here knows how anything is pronounced.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Awaitable, Protocol, Sequence

from src.interprete import Annonce, Tour

# The three kinds of line, matching the three things an interpreter can be asked to say.
TOUR = "tour"
ANNONCE = "annonce"
CONDENSATION = "condensation"


class Voice(Protocol):
    """What the conductor speaks through — the speaking half of `Interprete`, and no more.

    `ingest` is deliberately absent. It is the one verb that touches audio, and a voice is
    what says things, not what hears them. An `Interprete` satisfies this structurally, so
    the in-process path needs no adapter at all.
    """

    def render(self, tour: Tour) -> Awaitable[None]: ...

    def insert_annonce(self, annonce: Annonce) -> Awaitable[None]: ...

    def condense(self, tours: Sequence[Tour]) -> Awaitable[None]: ...


@dataclass(frozen=True)
class Line:
    """One thing to say, and everything needed to say it.

    Deliberately not a flat string. A turn still carries its original language, because an
    adapter that translates and speaks in one movement must not be handed a string somebody
    else has already translated — that is the whole point of speech-to-speech, and flattening
    the line here would throw it away before the agent ever saw it.
    """

    kind: str
    # The listener's language: what this is to be said in, whatever it is in now.
    language: str
    tour: Tour | None = None
    annonce: Annonce | None = None
    # Non-empty for a condensation only: the interval being given in substance.
    covers: tuple[Tour, ...] = ()

    def as_json(self) -> dict:
        """The wire form. Flat and self-describing — the agent reconstructs the call from
        `kind` alone, and an unknown kind is a line it can skip rather than a parse error."""
        payload: dict = {"kind": self.kind, "language": self.language}
        if self.tour is not None:
            payload["tour"] = _tour_json(self.tour)
        if self.annonce is not None:
            payload["text"] = self.annonce.text
        if self.covers:
            payload["covers"] = [_tour_json(tour) for tour in self.covers]
        return payload


def _tour_json(tour: Tour) -> dict:
    return {
        "participantId": tour.participant_id,
        "text": tour.text,
        "language": tour.language,
        "sequence": tour.sequence,
    }


@dataclass
class Script:
    """A `Voice` that writes down what it was asked to say.

    Never raises. `InterpreteError` means a provider did not answer, and there is no provider
    here — which is the honest outcome: under the served model a failure to speak happens in
    the agent, minutes of network away from the decision to say it, and the conductor's
    `except InterpreteError` branches simply do not apply to writing a list down.
    """

    language: str
    lines: list[Line] = field(default_factory=list)

    async def render(self, tour: Tour) -> None:
        self.lines.append(Line(kind=TOUR, language=self.language, tour=tour))

    async def insert_annonce(self, annonce: Annonce) -> None:
        # An announcement is composed in the listener's language already, so there is nothing
        # left to translate — `language` and the annonce's own agree by construction.
        self.lines.append(Line(kind=ANNONCE, language=self.language, annonce=annonce))

    async def condense(self, tours: Sequence[Tour]) -> None:
        # An empty interval produces no line at all. An interpreter announcing the summary
        # of nothing is worse than silence, and the rule belongs here rather than in each
        # adapter that would otherwise have to remember it.
        if not tours:
            return
        self.lines.append(
            Line(kind=CONDENSATION, language=self.language, covers=tuple(tours))
        )

    def as_json(self) -> list[dict]:
        return [line.as_json() for line in self.lines]

    async def play(self, voice: Voice) -> None:
        """Say a written script through a real interpreter.

        What the agent does with what it is served, and what makes the two paths one thing:
        `deliver()` is `script_for()` followed by this. Failures are the caller's — an agent
        that stops half-way has a human who stopped listening, because in this topology the
        room and the agent die together.
        """
        for line in self.lines:
            if line.kind == TOUR and line.tour is not None:
                await voice.render(line.tour)
            elif line.kind == ANNONCE and line.annonce is not None:
                await voice.insert_annonce(line.annonce)
            elif line.kind == CONDENSATION:
                await voice.condense(line.covers)
