"""Saying what the orchestrator says is owed.

The last stretch of the circuit. `orchestrator_link` fetches an ordered list of lines; this
turns each one into speech, in this process, where the audio already is.

**Two ways to say a line, and choosing between them is the cost of the product.**

    verbatim    the text is already in the listener's language
                → literal speech. No model call, no translation, no latency.

    otherwise   the text is in somebody else's language
                → the realtime model translates and speaks in one movement.

Handing a verbatim line to the model would pay for a translation into the language it is
already in. It is the same reason a Salon's price follows the number of languages in it
rather than its length, and it is decided here because here is where the two paths exist.

**The loop asks rather than waits.** The orchestrator serves and never pushes, so an agent
learns that somebody else spoke by asking. The interval is the trade: too slow and the
conversation lags, too fast and two idle agents fill a log with nothing. A quarter second
inside one VPC is cheap and is under what a listener notices between a sentence ending and
its translation beginning. Long-polling would remove even that, and is the next move if the
interval ever shows up in a measurement.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable, Protocol

from src.orchestrator_link import Line, OrchestratorLink

logger = logging.getLogger("agent.following")

# See the module docstring. A quarter second is beneath notice and above busy-waiting.
DEFAULT_INTERVAL_SECONDS = 0.25

# How long to keep quiet after a failed delivery before asking again. Longer than the
# ordinary interval on purpose: whatever went wrong is unlikely to be fixed in 250 ms, and an
# agent retrying at full speed against a service that is restarting is how one outage becomes
# two.
BACKOFF_SECONDS = 2.0

# Consecutive delivery batches that each lost a line to the same kind of failure before this
# loop gives up on its own realtime session rather than keep asking it. One rather than two:
# the fluke-tolerance this guards against is already spent inside `_speak` — see
# session_voice.py's own two-attempt retry — so a batch that reaches here has already failed
# to speak the same line twice running, which is the bar a fluke does not clear. Waiting for
# a second such batch before giving up used to cost the room roughly 34 seconds of silence
# for every session that dies this way — live logs from 2026-08-11 showed one taking that
# long to recover — against a redispatch already confirmed to produce a working session in
# about a second. There is nothing this extra wait buys that the first batch's own two
# attempts did not already spend.
GIVE_UP_AFTER_CONSECUTIVE_FAILURES = 1


class Voice(Protocol):
    """What this agent speaks through — its own interpreter, beside its own microphone.

    Two verbs because there are two costs. `say` is literal, `render` goes through the model.
    Declared structurally so the loop below can be tested without a realtime session, an
    audio device or a provider key.
    """

    def say(self, text: str) -> Awaitable[None]: ...

    def render(self, line: Line) -> Awaitable[None]: ...


async def deliver(line: Line, voice: Voice) -> None:
    """Say one line, by whichever of the two paths costs less.

    A line already in the listener's language is spoken as it stands. Everything else goes to
    the model, which translates and speaks it in one movement — never a translation followed
    by a separate reading, which would double the latency and lose the prosody of the
    original.
    """
    if line.verbatim:
        await voice.say(line.text)
    else:
        await voice.render(line)


async def deliver_script(
    link: OrchestratorLink,
    voice: Voice,
    *,
    on_delivered: Callable[[Line], None] | None = None,
) -> tuple[int, bool]:
    """Ask once, say everything that comes back. Returns (lines said, whether one failed).

    A line that cannot be spoken stops this delivery and no other. The reading position has
    already moved — the orchestrator advanced it when it handed the script over — so what is
    lost is what was left in this batch, and the next ask brings whatever has arrived since.
    Raising instead would take down the loop, and with it every later line as well.

    The second value is what lets `follow` tell a session that is merely having a bad line
    from one that cannot speak at all — a single batch failing here says nothing on its own,
    but several in a row is the pattern `GIVE_UP_AFTER_CONSECUTIVE_FAILURES` watches for.

    `on_delivered`, called once a line has actually been said, is how a caller shows this
    line as text — sourced from the line itself, which already carries who said it and in
    what language, rather than from watching what the model's voice produced. The interpreter
    lends its voice to a line; it does not become the thing that line is transcribed from.
    """
    said = 0
    for line in await link.script():
        try:
            await deliver(line, voice)
        except Exception:  # noqa: BLE001
            logger.warning("could not say a %s line, dropping the rest of this script",
                           line.kind, exc_info=True)
            return said, True
        said += 1
        if on_delivered is not None:
            on_delivered(line)
    return said, False


async def _wait(
    interval: float,
    sleep: Callable[[float], Awaitable[None]],
    wake: asyncio.Event | None,
) -> None:
    """The ordinary wait between two asks — cut short the moment `wake` says not to bother.

    `wake` is optional and its absence changes nothing: this is exactly `await
    sleep(interval)` for every caller that does not pass one, which is every test of this
    loop that predates it. Passed one, this races the interval against the event and takes
    whichever settles first — a fast path racing a poll it can only ever precede, never
    replace: the event carries nothing, so whoever set it still has to be asked what for.
    """
    if wake is None:
        await sleep(interval)
        return

    sleeping = asyncio.ensure_future(sleep(interval))
    waking = asyncio.ensure_future(wake.wait())
    try:
        await asyncio.wait({sleeping, waking}, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for task in (sleeping, waking):
            if not task.done():
                task.cancel()
    # Cleared either way. If `sleeping` won, this is a no-op — `wake` was never set. If
    # `waking` won, the next loop is the ask this event was for; leaving it set would fire
    # the short circuit again on every later interval for no reason.
    wake.clear()


async def follow(
    link: OrchestratorLink,
    voice: Voice,
    *,
    stop: asyncio.Event,
    interval: float = DEFAULT_INTERVAL_SECONDS,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    wake: asyncio.Event | None = None,
    on_unrecoverable: Callable[[], None] | None = None,
    on_delivered: Callable[[Line], None] | None = None,
) -> None:
    """Keep saying what this human is owed until told to stop.

    Checked before sleeping and again after, so a stop asked for while the loop is waiting is
    honoured at the next turn rather than a full interval later — which matters at teardown,
    where the room is going away underneath it.

    `wake` is the fast path alongside the poll (see `src/salon/notify.py` on the
    orchestrator's side): set from the room's data channel the moment the orchestrator says
    somebody else spoke, so this asks now instead of at the end of whatever is left of the
    ordinary interval. Left out, or never set, this behaves exactly as it always has —
    nothing here depends on it arriving.

    `on_unrecoverable` is called, once, after `GIVE_UP_AFTER_CONSECUTIVE_FAILURES` batches in
    a row each lose a line — the pattern a realtime session gives when its connection has
    died in a way retrying on it cannot fix (see session_voice.py's own retry, which this is
    the layer above). Left out, this loop keeps polling forever regardless, which was the
    whole behaviour before a webhook existed on the other end able to do anything about a
    session in that state. This function returns either way once it has called it: there is
    nothing left for it to poll for on a session its caller is about to leave.

    `on_delivered` is passed straight through to `deliver_script` — see there for what it is
    for.
    """
    if not link.configured:
        # Nothing to follow. An agent given no orchestrator runs the conversation it can,
        # rather than spinning against an address that does not exist.
        logger.info("no orchestrator configured: this agent will not follow a journal")
        return

    consecutive_failures = 0
    while not stop.is_set():
        try:
            _, failed = await deliver_script(link, voice, on_delivered=on_delivered)
        except Exception:  # noqa: BLE001
            # The link swallows its own failures, so reaching here means something else did.
            # Logged and slowed rather than raised: this task holds a live room.
            logger.warning("delivery loop stumbled", exc_info=True)
            await sleep(BACKOFF_SECONDS)
            continue

        if failed:
            consecutive_failures += 1
            if (
                on_unrecoverable is not None
                and consecutive_failures >= GIVE_UP_AFTER_CONSECUTIVE_FAILURES
            ):
                logger.error(
                    "giving up after %d consecutive failed deliveries; the realtime "
                    "session does not appear able to speak at all",
                    consecutive_failures,
                )
                on_unrecoverable()
                return
        else:
            consecutive_failures = 0

        if stop.is_set():
            return
        await _wait(interval, sleep, wake)
