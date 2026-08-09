"""A participant who talks by himself, so fifty of them cost nothing (FR58).

`InterpreteFake` was already deterministic, but it is *reactive*: you queue what its human
says and it says it. What a load scenario needs is something that decides on its own when to
speak and what to say — at a cadence, a length and a language somebody chose.

Deterministic on purpose, and not as a convenience. A load result that changes between runs
is measuring the generator rather than the system, and the entire point of this machinery is
that raising the participant ceiling from 3 to 50 becomes a measurement instead of a bet.
Same seed, same words, same verdict.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from random import Random

from src.interprete import Participant

# Words of more than three letters, so the stammer rule in `journal/cleaning.py` does not
# collapse them on the way in. A generator whose output was mostly deleted at ingestion
# would be measuring a system that had thrown its input away.
_VOCABULARY = (
    "alors", "parce", "quand", "toute", "chose", "avant", "depuis", "encore", "pendant",
    "surtout", "ensuite", "presque", "toujours", "souvent", "certain", "plutot", "vraiment",
    "peniblement", "autrement", "justement", "lentement", "publiquement", "seulement",
    "dernier", "premier", "meilleur", "possible", "difficile", "important", "necessaire",
)


@dataclass
class SimulatedSpeaker:
    """One participant generating their own turns."""

    participant: Participant
    # One turn every this many seconds of scenario time.
    cadence_seconds: float = 20.0
    words_per_turn: int = 40
    # Defaults to the participant's own language below: somebody speaking a language they do
    # not speak is a scenario nobody meant to write.
    language: str = ""
    seed: int = 0
    # Counted and asserted on. The claim that a fifty-participant run costs nothing is worth
    # nothing unless something checks it.
    provider_calls: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        if not self.language:
            self.language = self.participant.language

    def turns_until(self, seconds: float) -> list[tuple[float, str]]:
        """Every turn this speaker produces up to and including `seconds`.

        Whole scenario at once rather than a generator advanced by a clock: a scenario that
        can be computed without waiting is one that can be run in a test suite.
        """
        turns: list[tuple[float, str]] = []
        index = 1
        while index * self.cadence_seconds <= seconds:
            turns.append((index * self.cadence_seconds, self._text(index)))
            index += 1
        return turns

    def _text(self, index: int) -> str:
        """The words of one turn.

        Seeded on the participant as well as the run, so fifty speakers in one scenario do
        not all say the same sentence — which would leave the translation cache doing the
        work the load test is meant to be measuring.
        """
        words = Random(f"{self.seed}:{self.participant.id}:{index}")
        return " ".join(words.choice(_VOCABULARY) for _ in range(self.words_per_turn))
