"""The order the interpreter's own utterances come out in (FR62).

The problem is reproducibility rather than fairness. Several things can become ready during
one long intervention, and if the order they emerge in depends on which coroutine happened
to resume first, the same scenario produces different audio twice and no test can pin any of
it down. So the order is a property of this queue and never of the event loop.

It sequences; it does not arbitrate. Everything waiting comes out, one after another —
nothing is dropped and nothing is held back for a round that never arrives. Deciding who
goes first is a different power from deciding who goes at all, and this only has the first.

Two kinds of speech stay outside it on purpose. A participant's introduction and their
history are said as they enter the room, before they are in the conversation at all, so they
never compete with any of this. And the sentence announcing a condensation belongs to the
summary it introduces: separating them would strand "while you were listening, three people
spoke" next to something else entirely.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from src.interprete import Annonce


class Urgency(Enum):
    """What kind of thing this is, and therefore when it is said.

    The three ranks the specification names are `BUSY`, `BALANCE` and `ADVERT`, in that
    order. `NOTICE` — arrivals, microphone changes, the ordinary facts of the conversation —
    is not in that list, and sits between the balance alerts and the advertising. That is the
    reading that keeps the three named ranks in exactly the given order while refusing to let
    anything being *sold* precede a fact about the conversation itself.
    """

    # "Vocaliz is busy" (FR49) and the request to top up (FR56). First, because it is what
    # tells somebody why the conversation is running away from them — anything said before
    # it is said to a person who does not yet know why they are lost.
    BUSY = 1
    # A low balance, and the warning that the Salon is about to end (FR55). Ahead of
    # advertising, since an advertisement that pushed this later could push it past the end.
    BALANCE = 2
    # Everything ordinary: somebody arrived, a microphone was cut, the history was shared.
    NOTICE = 3
    # Advertising (FR39). Always last: it is the only one of these that serves somebody
    # other than the person listening.
    ADVERT = 4

    @property
    def rank(self) -> int:
        return self.value


@dataclass(order=True)
class _Waiting:
    """One utterance waiting for a slot, with everything the order depends on.

    `arrived` is a counter rather than a clock. Two things ready at the same instant need a
    settled order, and a timestamp can tie while a counter cannot — nor does it depend on
    object identity or hash order, either of which varies between runs.
    """

    rank: int
    arrived: int
    annonce: Annonce = field(compare=False)


@dataclass
class MetaSpeechQueue:
    """What is waiting to be said to one participant, in the order it will be said."""

    _waiting: list[_Waiting] = field(default_factory=list)
    _arrivals: int = 0

    def add(self, annonce: Annonce, *, urgency: Urgency = Urgency.NOTICE) -> None:
        """Put something in. Nothing is ever refused, deduplicated or replaced.

        Two identical sentences are two things that happened, and collapsing them would be
        this queue deciding what is worth saying — which is exactly the power it must not
        have.
        """
        self._arrivals += 1
        self._waiting.append(
            _Waiting(rank=urgency.rank, arrived=self._arrivals, annonce=annonce)
        )

    def drain(self) -> tuple[Annonce, ...]:
        """Everything waiting, in order, and the queue left empty.

        Everything rather than the most urgent one: a slot between two messages is a chance
        to say what is owed, and leaving the rest for a later slot is how a low-priority
        utterance ends up never being said at all.
        """
        ordered = sorted(self._waiting)
        self._waiting.clear()
        return tuple(item.annonce for item in ordered)

    @property
    def waiting(self) -> int:
        return len(self._waiting)
