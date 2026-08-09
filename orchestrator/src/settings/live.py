"""Holding the settings while the service runs, and noticing when they change.

`get()` is a coroutine rather than an attribute for one reason: several instances serve one
Salon, and a change made against the table by any route has to reach all of them. The only
thing they share is the table, so each re-reads it on an interval. That interval is the
whole design — reading on every access would make this the busiest query in the system, and
never re-reading would mean a change took a deploy, which is the thing FR54 exists to avoid.
"""
from __future__ import annotations

import time
from typing import Callable, Mapping, Protocol

from src.settings.values import InvalidSettings, SalonSettings, from_mapping

# Long enough that the table is not hot, short enough that somebody changing a threshold
# during a bad Salon sees it take effect while they are still watching.
DEFAULT_RELOAD_SECONDS = 30.0


class SettingsStore(Protocol):
    """Where the parameters are kept between restarts."""

    async def load(self) -> Mapping[str, float | int]: ...

    async def save(self, values: Mapping[str, float | int]) -> None: ...


class InMemorySettingsStore:
    """For tests and for a local run with no database.

    Counts its reads, which is how the reload interval is checked at all.
    """

    def __init__(self, values: Mapping[str, float | int] | None = None) -> None:
        self.saved: dict[str, float | int] = dict(values or {})
        self.reads = 0

    async def load(self) -> Mapping[str, float | int]:
        self.reads += 1
        return dict(self.saved)

    async def save(self, values: Mapping[str, float | int]) -> None:
        self.saved.update(values)


class LiveSettings:
    """The current parameters, re-read from the store on an interval."""

    def __init__(
        self,
        *,
        store: SettingsStore,
        reload_seconds: float = DEFAULT_RELOAD_SECONDS,
        now: Callable[[], float] = time.monotonic,
    ) -> None:
        self._store = store
        self._reload_seconds = reload_seconds
        self._now = now
        self._current: SalonSettings | None = None
        self._read_at = 0.0

    async def get(self) -> SalonSettings:
        """The parameters as they stand, reloading if the interval has elapsed."""
        if self._current is None or self._now() - self._read_at >= self._reload_seconds:
            await self.refresh()
        assert self._current is not None
        return self._current

    async def refresh(self) -> SalonSettings:
        """Re-read the store now, whatever the interval says.

        A stored combination that breaks a rule raises here, which on startup means the
        instance does not come up. That is the right way round: an instance running for a
        week with regulation that can never fire is worse than one that refused to start
        and said why.
        """
        self._current = from_mapping(dict(await self._store.load()))
        self._read_at = self._now()
        return self._current

    async def save(self, **changes: float | int) -> SalonSettings:
        """Validate a change against everything around it, write it, and apply it here.

        In that order. A change that is refused must not be written down, or the next
        instance to start would read it and fail on the way up — a bad edit correctly
        refused here would still have taken the fleet down at the next deploy.
        """
        updated = (await self.get()).replace(**changes)
        await self._store.save(changes)
        self._current = updated
        self._read_at = self._now()
        return updated


__all__ = [
    "DEFAULT_RELOAD_SECONDS",
    "InMemorySettingsStore",
    "InvalidSettings",
    "LiveSettings",
    "SettingsStore",
]
