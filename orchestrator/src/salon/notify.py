"""Waking a served participant's agent the moment something is ready for them.

Optional, and a deployment without one loses nothing but speed: a served seat is still
delivered to at the next poll, whatever that turns out to mean for this participant — the
poll is what makes every promise the two-call contract in `serving.py` makes, and this exists
only to shrink the gap between "somebody said something" and "another room hears it" from up
to one polling interval down to about as long as one HTTP call takes.

Never allowed to cost the conversation it is trying to speed up. A Salon that could not wake
a participant must still have recorded what was said — see the try/except around every call
site — because the alternative is losing a message over a feature that only ever promised to
make delivery *faster*.
"""
from __future__ import annotations

from typing import Protocol


class Notifier(Protocol):
    async def notify(self, salon_id: str, participant_id: str) -> None:
        """Tell whoever is listening for `participant_id` that something is ready.

        Carries no content — the fast path is an invitation to ask, not a second copy of
        what to say. `GET .../script` remains the only place a line is actually handed over,
        so there is exactly one way to advance a reading position and never two that could
        disagree about it.
        """


class NoNotifier:
    """The default: nobody is told, and a Salon without one behaves exactly as it always
    has — served only by the poll."""

    async def notify(self, salon_id: str, participant_id: str) -> None:
        return


class RecordingNotifier:
    """A `Notifier` that remembers what it was asked to say, for tests."""

    def __init__(self) -> None:
        self.notified: list[tuple[str, str]] = []

    async def notify(self, salon_id: str, participant_id: str) -> None:
        self.notified.append((salon_id, participant_id))


class FailingNotifier:
    """A `Notifier` that always raises, for testing that a Salon survives one that can't be
    reached."""

    async def notify(self, salon_id: str, participant_id: str) -> None:
        raise RuntimeError("the notifier could not be reached")
