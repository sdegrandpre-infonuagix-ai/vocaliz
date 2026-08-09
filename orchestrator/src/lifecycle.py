"""Which Salons this instance hosts, and whether it still accepts new ones.

Deliberately empty of meaning: a Salon is an opaque identifier here. Nothing of what is
said, nothing of where each interpreter has got to, nothing of what any of it costs —
Story 6.3 and Epic 8 own those. What lives here is the one thing an instance must know
about itself to be deployed at all, namely whether it is still taking work.

Affinity between a Salon and the instance hosting it is a performance preference, not a
condition of survival: the state is persisted elsewhere, so a Salon dropped by this
registry can be picked up by another instance that re-reads it.
"""
from __future__ import annotations

import asyncio


class DrainingError(RuntimeError):
    """Raised when a Salon is offered to an instance that is shutting down."""

    def __init__(self, salon_id: str) -> None:
        self.salon_id = salon_id
        super().__init__(
            f"Salon {salon_id} refused: this instance is draining and accepts no new Salons."
        )


class SalonRegistry:
    def __init__(self) -> None:
        self._hosted: set[str] = set()
        self._draining = False
        # Set while nothing is hosted, so a drain that starts on an idle instance returns
        # immediately instead of waiting for a release that will never come.
        self._empty = asyncio.Event()
        self._empty.set()

    @property
    def hosted(self) -> tuple[str, ...]:
        return tuple(sorted(self._hosted))

    @property
    def hosted_count(self) -> int:
        return len(self._hosted)

    @property
    def draining(self) -> bool:
        return self._draining

    def accept(self, salon_id: str) -> None:
        """Take responsibility for a Salon, unless this instance is on its way out."""
        if self._draining:
            raise DrainingError(salon_id)
        self._hosted.add(salon_id)
        self._empty.clear()

    def release(self, salon_id: str) -> None:
        """Let a Salon go. Unknown identifiers are ignored — a release arriving after
        another instance took the Salon over must not bring this one down."""
        self._hosted.discard(salon_id)
        if not self._hosted:
            self._empty.set()

    def begin_drain(self) -> None:
        """Stop accepting new Salons. What is already hosted keeps running."""
        self._draining = True

    async def wait_until_empty(self, timeout: float) -> bool:
        """Wait for the hosted Salons to end. True if they did, False on timeout.

        The timeout is what stops one Salon that never ends from holding the task open
        past the platform's own stop timeout, at which point it would be killed anyway —
        and killed is exactly the outcome the drain exists to avoid for everybody else.
        """
        try:
            await asyncio.wait_for(self._empty.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            return False
        return True
