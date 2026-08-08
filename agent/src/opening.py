"""Who opens the conversation, and when the wait stops applying.

The agent used to wait to be spoken to, which left a host sitting in silence with nothing to
react to. An invitation then scheduled an opening a quarter of a minute later, which merely
moved the awkwardness: a host still reading was interrupted, and one who was ready had to
wait out a counter. A salon now starts with the agent paused and opens when the host activates
it, so the opening is scheduled with no delay at all — the button press *is* the timing.

The delay is kept as a parameter rather than removed. It is what makes speech-before-the-
opening representable at all, and with it the two orderings this module exists to get right:
somebody who speaks first has already solved the problem the opening existed for, and both
ignoring them and greeting them afterwards read as broken. Speech therefore stands it down.

Standing down deliberately generates no reply. The salon answers speech on its own, and
that answer is the first turn — which the standing instructions already order as welcome,
announcement, then source. Forcing a second reply on top would have the agent talk over
itself, which is worse than the silence being fixed.

Extracted from the entrypoint closure it grew up in so that the two orderings that matter
can actually be tested: speech before the delay elapses, and speech after.
"""
import asyncio
import logging
from typing import Any, Awaitable, Callable, Optional

logger = logging.getLogger(__name__)


class OpeningGate:
    """Tracks two states that were once conflated into one flag.

    A countdown under way is not the same as an opening already spoken. Collapsing them is
    what let a single boolean claim the greeting was done the moment the timer started.
    """

    def __init__(self, speak: Callable[[], Any], *, label: str = "") -> None:
        # Called with no arguments so this holds no opinion about how the opening is worded
        # or which salon says it.
        self._speak = speak
        self._label = label
        self._spoken = False
        self._timer: Optional[asyncio.Task] = None

    @property
    def spoken(self) -> bool:
        """True once the opening has happened or been settled some other way."""
        return self._spoken

    @property
    def waiting(self) -> bool:
        return self._timer is not None and not self._timer.done()

    def schedule(self, delay: float) -> bool:
        """Arrange the opening for `delay` seconds from now. Returns whether it was taken.

        Ignored if an opening has already happened or is already pending: a host inviting two
        people should not be greeted twice, and an opening only makes sense as an opening.
        """
        if self._spoken or self._timer is not None:
            return False
        # The handle is stored before anything awaits, so a stand_down arriving in between
        # cannot find a gate that is waiting with no timer to cancel.
        self._timer = asyncio.ensure_future(self._open_after(delay))
        return True

    def settle(self) -> None:
        """Treat the opening as done without speaking it.

        For an agent joining a salon that is already under way — a restarted job, or one the
        host removed and brought back. The conversation has an opening already; what it must
        not get is a second one the next time the host pauses and resumes.

        Distinct from stand_down, which reports whether it was the call that settled things
        and only applies while a timer is pending. This applies at any point and says nothing.
        """
        self._spoken = True
        if self.waiting:
            self._timer.cancel()

    def stand_down(self) -> bool:
        """Somebody spoke first. Returns whether this call is what settled it."""
        if self._spoken or not self.waiting:
            return False
        self._timer.cancel()
        self._spoken = True
        logger.info(
            "Someone spoke before the opening delay elapsed; the reply to them opens the "
            "conversation instead%s",
            f" ({self._label})" if self._label else "",
        )
        return True

    async def _open_after(self, delay: float) -> None:
        try:
            await asyncio.sleep(delay)
        except asyncio.CancelledError:
            return
        # Cancellation normally stops us in the sleep above. It does not when a stand_down
        # lands in the same tick as the timer expiring, and a greeting delivered after
        # somebody has already started talking is the thing being fixed.
        if self._spoken:
            return
        self._spoken = True
        try:
            result = self._speak()
            if isinstance(result, Awaitable):
                await result
        except Exception as exc:  # noqa: BLE001
            # A failed opening must not disturb a salon that is otherwise working.
            logger.warning("Could not open the conversation after an invitation: %s", exc)

    def cancel(self) -> None:
        """Drop a pending opening without claiming it happened — for shutdown."""
        if self.waiting:
            self._timer.cancel()
