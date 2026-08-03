"""Who opens the conversation, and when the wait stops applying.

The agent used to wait to be spoken to, which left a host who had just sent an invitation
sitting in silence with nothing to react to. So an invitation now schedules an opening a
quarter of a minute later.

That delay is a *maximum*, not a promise of silence. Somebody who speaks during the wait has
already solved the problem the wait existed for, and ignoring them for the remaining twelve
seconds reads as broken — as does greeting them afterwards as though nothing had been said.
Speech therefore stands the opening down.

Standing down deliberately generates no reply. The session answers speech on its own, and
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
        # or which session says it.
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
            # A failed opening must not disturb a session that is otherwise working.
            logger.warning("Could not open the conversation after an invitation: %s", exc)

    def cancel(self) -> None:
        """Drop a pending opening without claiming it happened — for shutdown."""
        if self.waiting:
            self._timer.cancel()
