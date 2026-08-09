"""Where an interpreter gets an advertisement from (FR39 / FR33).

The exchange is inherited and lives on the API side: it reserves a broadcast, prices it, and
keeps reserved apart from actually heard. This is the port an interpreter reaches it through,
and the whole of what the conversation process is allowed to know about advertising.

Two calls, matching the two the API already exposes. `draw` reserves — it is a **pull**, made
at the moment a placement turns up rather than when the broadcast becomes due, so the choice
is made against a current record of what this listener has already heard. `delivered` confirms
that the words were actually said, and nothing is ever billed without it.

`draw` takes a participant and a language, and nothing else. Which cell somebody is in is the
exchange's business: the process holding the conversation never receives a location, which is
a stronger guarantee than remembering not to write one down.

Nothing here needs a verbatim flag. An advertisement is inserted, never journalled, so no
condensation, shortening or disfluency cleaning can reach it — the wording an advertiser
required word for word (Story 9.2) is said as given because there is no path by which
anything else could happen to it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from src.interprete import Annonce


@dataclass(frozen=True)
class Diffusion:
    """One advertisement, reserved for one participant, not yet spoken.

    The identifier is what the confirmation refers to. Without it the exchange could not tell
    which of two reservations was the one actually heard, and the whole reserved-versus-heard
    distinction would collapse into a count.
    """

    id: str
    annonce: Annonce


class Regie(Protocol):
    """The advertising exchange, as a Salon is allowed to see it."""

    async def draw(self, participant_id: str, *, language: str) -> Diffusion | None:
        """Reserve one advertisement for one listener, or `None` if there are none.

        `None` is an ordinary outcome and not an error: an empty inventory means silence,
        which is the correct thing to hear.
        """
        ...

    async def delivered(self, diffusion: Diffusion) -> None:
        """Confirm that it was spoken. Never called for one that was not."""
        ...


@dataclass
class RegieFake:
    """An exchange that never leaves the process, for tests and for local running.

    Hands out the same pitch every time. Which advertisement is chosen is Story 9.2's
    question and is settled on the API side; what a Salon has to get right is *where* it goes,
    so varying the text here would only make the placement harder to read.
    """

    pitch: str = "Une annonce."
    language: str = "fr"
    # Set to have the inventory come back empty — silence, not an error.
    empty: bool = False
    # Set to raise from `draw`, standing in for an exchange that cannot be reached.
    fail_with: Exception | None = None

    draws: list[tuple[str, str]] = field(default_factory=list)
    reserved: list[Diffusion] = field(default_factory=list)
    delivered_ones: list[Diffusion] = field(default_factory=list)

    async def draw(self, participant_id: str, *, language: str) -> Diffusion | None:
        self.draws.append((participant_id, language))
        if self.fail_with is not None:
            raise self.fail_with
        if self.empty:
            return None
        diffusion = Diffusion(
            id=f"diffusion-{len(self.reserved) + 1}",
            # Already in the listener's language: the exchange derives the translation from
            # the creative, exactly as a turn of speech is derived from what was said.
            annonce=Annonce(text=self.pitch, language=language),
        )
        self.reserved.append(diffusion)
        return diffusion

    async def delivered(self, diffusion: Diffusion) -> None:
        self.delivered_ones.append(diffusion)
