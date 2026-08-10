"""The realtime session, seen as the two verbs the delivery loop needs.

`following.deliver` chooses between them, and the choice was meant to be the cost of the
product:

    say     the line is already in the listener's language — literal speech, no model call
    render  the line is in somebody else's — the model translates and speaks in one movement

**`say` does not exist for this provider, and both verbs go through the model now.** xAI's
realtime session has no standalone text-to-speech: `AgentSession.say()` requires either a
separate TTS model or a `RealtimeSession` that implements `say()`, and this one does not. The
first version of this file called it anyway, and every verbatim line — every introduction,
every announcement, any two participants sharing a language — raised
`RuntimeError: trying to generate speech from text without a TTS model...`, which
`following.deliver_script` catches and treats as "this line failed" — dropping not only that
line but everything queued after it in the same batch. A plain "test 4" between two people
speaking the same language went silent this way, with no translation involved at all.

Routing everything through `generate_reply` gives up the free path for same-language lines —
a real cost, paid because the alternative is not cheaper, it is broken. Revisit this if xAI
ever exposes a working `say()`; nothing else about the split would need to change.

Never a translation followed by a separate reading, regardless of path. That would double the
latency and lose the prosody of the original, which is most of what makes an interpreted
conversation bearable to sit through.
"""
from __future__ import annotations

import logging

from src.orchestrator_link import Line

logger = logging.getLogger("agent.voice")

# One retry, not none and not several. The reading position has already moved by the time
# this code sees the line — see the module docstring on the orchestrator's side of that
# contract — so a delivery that never lands is gone for good, not caught on the next poll.
# A second try costs one more provider timeout in the rare case the first attempt was itself
# a fluke; a loop that kept trying would hold a genuinely broken session hostage to a line it
# is never going to say.
MAX_ATTEMPTS = 2


def instructions_for(line: Line) -> str:
    """What to tell the model, for one line owed to one listener.

    Names the target language explicitly rather than leaving it to be inferred. The model
    hears the room and would otherwise answer in whatever language it last heard, which for a
    listener who has not spoken yet is nobody's language in particular.
    """
    origin = (
        f" It is written in {line.source_language}."
        if line.source_language
        else ""
    )
    return (
        f"Say the following to this listener in {line.language}, and nothing else."
        f"{origin} You are lending your voice to the person who said it: speak as they "
        "would, in the first person if that is how it is written. Add no greeting, no "
        "comment and no preamble, and never say that somebody asked you to pass it on.\n"
        f"---\n{line.text}\n---"
    )


def _verbatim_instructions(text: str, language: str) -> str:
    """What to tell the model for a line already in the listener's language.

    Still a `generate_reply` call — see the module docstring for why `say()` is not an
    option here — but told plainly that there is nothing to translate, so a model that
    might otherwise polish or rephrase says exactly what it was given.
    """
    return (
        f"Say the following to this listener exactly as written, in {language}. It is "
        "already in their language — do not translate it, paraphrase it, or add anything "
        "to it. Add no greeting, no comment and no preamble.\n"
        f"---\n{text}\n---"
    )


class SessionVoice:
    """A `following.Voice` backed by a live `AgentSession`.

    Holds the session and nothing else. Everything about which path a line takes is decided
    in `following.deliver`, so this stays the thinnest possible adapter — the place where a
    provider is named, and the only thing that would change if the provider did.
    """

    def __init__(self, session, *, language: str = "") -> None:
        self._session = session
        # Used only to word the verbatim instruction correctly. `deliver` calls `say` with
        # bare text, having already decided the line needs no translation — this is what
        # lets that instruction still name the language it is in.
        self._language = language

    async def say(self, text: str) -> None:
        """A line already in the listener's language — routed through the model anyway.

        Kept as its own method rather than folded into `render`, so the day this provider
        gains a real `say()` the fix is inside this one function.
        """
        if not text.strip():
            return
        await self._speak(
            _verbatim_instructions(text, self._language or "the same language")
        )

    async def render(self, line: Line) -> None:
        """Through the model, which translates and speaks in one movement."""
        if not line.text.strip():
            return
        await self._speak(instructions_for(line))

    async def _speak(self, instructions: str) -> None:
        """Ask the session to say this, and wait for the turn to finish before returning.

        Waiting was not the original design — `generate_reply` returned a handle to speech
        now under way, and the delivery loop moved straight on. That was the wrong trade: a
        listener behind by more than one line got every one fired at the realtime session in
        the same breath, and the provider can only carry one generation at a time. The
        second and later calls sat waiting for a turn that never came and timed out.

        Retried once, because the reading position has already moved by the time this code
        sees the line — see the orchestrator's side of that contract — so a delivery that
        never lands is gone for good, not caught on the next poll. Bounded to one retry
        deliberately: a session that fails a line twice running is not a fluke this loop
        should keep spending its own timeout budget on.

        Never raises. `SpeechHandle._mark_done` keeps a failure out of the awaited future by
        design — most handles are never awaited — so a failed attempt is only visible through
        `exception()`, which is what decides whether this retries or gives up.
        """
        for attempt in range(1, MAX_ATTEMPTS + 1):
            handle = self._session.generate_reply(instructions=instructions)
            await handle
            error = handle.exception() if hasattr(handle, "exception") else None
            if error is None:
                return
            logger.warning(
                "a turn did not finish speaking (attempt %d/%d): %s",
                attempt,
                MAX_ATTEMPTS,
                error,
            )
