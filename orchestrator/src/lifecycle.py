"""Which Salons this instance hosts, and whether it still accepts new ones.

Nearly empty of meaning, and that emptiness is deliberate. What is said, where each reader
has got to, what any of it costs — Story 6.3 and Epic 8 own those. What lives here is the
one thing an instance must know about itself to be deployed at all, namely whether it is
still taking work, plus the running conversations themselves so a request can find one.

Holding the `Salon` objects does not make this their home. Affinity between a Salon and the
instance hosting it is a performance preference, not a condition of survival: the journal is
persisted, so a Salon dropped here can be picked up by another instance that re-reads it.
Everything in this dictionary is reconstructible, which is what makes it safe to lose.
"""
from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover — the import exists for the type checker alone
    from src.salon import Salon


class DrainingError(RuntimeError):
    """Raised when a Salon is offered to an instance that is shutting down."""

    def __init__(self, salon_id: str) -> None:
        self.salon_id = salon_id
        super().__init__(
            f"Salon {salon_id} refused: this instance is draining and accepts no new Salons."
        )


class SalonRegistry:
    def __init__(self) -> None:
        # Identifiers only until a running conversation is put against one. `accept` is
        # still the whole of what the drain needs, and a Salon may be accepted before it is
        # built — which is what the API does when it creates the room and the Salon in one
        # breath, before anybody has joined.
        self._hosted: dict[str, "Salon | None"] = {}
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

    def accept(self, salon_id: str, salon: "Salon | None" = None) -> None:
        """Take responsibility for a Salon, unless this instance is on its way out.

        Accepting the same Salon twice is a reconnection or a retried request, never a
        second conversation: an existing one is kept and the running state with it. Passing
        a `Salon` over one already here would silently drop everything said so far, which is
        why it does not.
        """
        if self._draining:
            raise DrainingError(salon_id)
        if salon is None or self._hosted.get(salon_id) is None:
            self._hosted.setdefault(salon_id, None)
            if salon is not None:
                self._hosted[salon_id] = salon
        self._empty.clear()

    def get(self, salon_id: str) -> "Salon | None":
        """The running conversation, or `None` — either unknown here, or accepted and not
        yet built. A caller cannot tell those apart and does not need to: both mean there is
        nothing to serve yet."""
        return self._hosted.get(salon_id)

    def release(self, salon_id: str) -> None:
        """Let a Salon go. Unknown identifiers are ignored — a release arriving after
        another instance took the Salon over must not bring this one down."""
        self._hosted.pop(salon_id, None)
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
