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


async def deliver_script(link: OrchestratorLink, voice: Voice) -> int:
    """Ask once, say everything that comes back. Returns how many lines were said.

    A line that cannot be spoken stops this delivery and no other. The reading position has
    already moved — the orchestrator advanced it when it handed the script over — so what is
    lost is what was left in this batch, and the next ask brings whatever has arrived since.
    Raising instead would take down the loop, and with it every later line as well.
    """
    said = 0
    for line in await link.script():
        try:
            await deliver(line, voice)
        except Exception:  # noqa: BLE001
            logger.warning("could not say a %s line, dropping the rest of this script",
                           line.kind, exc_info=True)
            return said
        said += 1
    return said


async def follow(
    link: OrchestratorLink,
    voice: Voice,
    *,
    stop: asyncio.Event,
    interval: float = DEFAULT_INTERVAL_SECONDS,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> None:
    """Keep saying what this human is owed until told to stop.

    Checked before sleeping and again after, so a stop asked for while the loop is waiting is
    honoured at the next turn rather than a full interval later — which matters at teardown,
    where the room is going away underneath it.
    """
    if not link.configured:
        # Nothing to follow. An agent given no orchestrator runs the conversation it can,
        # rather than spinning against an address that does not exist.
        logger.info("no orchestrator configured: this agent will not follow a journal")
        return

    while not stop.is_set():
        try:
            await deliver_script(link, voice)
        except Exception:  # noqa: BLE001
            # The link swallows its own failures, so reaching here means something else did.
            # Logged and slowed rather than raised: this task holds a live room.
            logger.warning("delivery loop stumbled", exc_info=True)
            await sleep(BACKOFF_SECONDS)
            continue

        if stop.is_set():
            return
        await sleep(interval)
