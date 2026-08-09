"""Who is talking, when nobody can hear anybody.

The signal this replaces is the one the topology destroyed. Silence in your ear used to mean
nobody was speaking; now it means your interpreter has nothing to render yet. Those are
completely different facts, and from the inside they are indistinguishable.

So each pair carries **two** lights rather than one. Somebody speaking and their interpreter
rendering are different things, and the second is what explains the delay in the first:
seeing Marie green and her interpreter still red is seeing exactly why you are still
waiting. One light per pair would collapse the two and lose the explanation.

Nothing here detects anything. LiveKit already publishes speaking state natively and the
Silero VAD is already in `livekit-agents[silero]` — what is missing is only that a room's
state stops at the room, and the humans share none. This is the carrying, over the same data
channel as the turns.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Voice(Enum):
    """One voice, lit or not.

    Colour *and* shape, because UX-DR7 asks that colour never be the only carrier: a
    participant who cannot tell green from red still has to be able to read the board, and
    the difference has to survive being printed in black and white.
    """

    ACTIVE = ("green", "filled")
    QUIET = ("red", "hollow")

    @property
    def colour(self) -> str:
        return self.value[0]

    @property
    def shape(self) -> str:
        return self.value[1]

    @classmethod
    def of(cls, speaking: bool) -> Voice:
        return cls.ACTIVE if speaking else cls.QUIET


@dataclass
class Pair:
    """One human and the interpreter that is theirs, each with their own light."""

    participant_id: str
    human: Voice = Voice.QUIET
    interpreter: Voice = Voice.QUIET

    def as_dict(self) -> dict:
        return {
            "participant": self.participant_id,
            "human": {"colour": self.human.colour, "shape": self.human.shape},
            "interpreter": {
                "colour": self.interpreter.colour,
                "shape": self.interpreter.shape,
            },
        }


@dataclass
class SpeakingBoard:
    """Every pair of a Salon, and which voices are lit."""

    _pairs: dict[str, Pair] = field(default_factory=dict, repr=False)

    @property
    def pairs(self) -> tuple[Pair, ...]:
        return tuple(self._pairs[key] for key in sorted(self._pairs))

    def attach(self, participant_id: str) -> None:
        self._pairs.setdefault(participant_id, Pair(participant_id=participant_id))

    def detach(self, participant_id: str) -> None:
        self._pairs.pop(participant_id, None)

    def set(
        self,
        participant_id: str,
        *,
        human: bool | None = None,
        interpreter: bool | None = None,
    ) -> bool:
        """Record what a pair is doing. Returns whether anything actually moved.

        The return value is the whole economy of this feature. Silero reports continuously,
        and rebroadcasting an unchanged board to everybody many times a second would be the
        most expensive possible way to say nothing.
        """
        pair = self._pairs.setdefault(participant_id, Pair(participant_id=participant_id))

        before = (pair.human, pair.interpreter)
        if human is not None:
            pair.human = Voice.of(human)
        if interpreter is not None:
            pair.interpreter = Voice.of(interpreter)

        return before != (pair.human, pair.interpreter)

    def as_message(self) -> dict:
        """The board as it goes on the wire.

        Tagged, because captions travel the same channel and a client must be able to tell
        the two apart without guessing: a board is JSON with a `kind`, a caption is the text
        itself.
        """
        return {"kind": "speaking", "pairs": [pair.as_dict() for pair in self.pairs]}
