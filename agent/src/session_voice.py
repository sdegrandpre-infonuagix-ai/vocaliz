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
        await self._await_spoken(
            self._session.generate_reply(
                instructions=_verbatim_instructions(text, self._language or "the same language")
            )
        )

    async def render(self, line: Line) -> None:
        """Through the model, which translates and speaks in one movement."""
        if not line.text.strip():
            return
        await self._await_spoken(
            self._session.generate_reply(instructions=instructions_for(line))
        )

    async def _await_spoken(self, handle) -> None:
        """Wait for one turn to finish before the delivery loop asks for the next.

        Used to return without waiting — a handle to speech now under way, with the delivery
        loop free to move on. That was the wrong trade: a listener behind by more than one
        line got every one of them fired at the realtime session in the same breath, and the
        provider can only carry one generation at a time. The second and later calls sat
        waiting for a turn that never came, timed out, and were never spoken — silently, since
        nothing here was watching for it. Awaiting costs the batch the length of each
        sentence; that is what a person hearing it catch up would cost too, and it is
        recoverable in a way a message that quietly never arrives is not.

        Never raises on its own — see `SpeechHandle._mark_done`, which keeps a failure out of
        the awaited future by design. Logged here instead, so a line that timed out leaves a
        trace rather than looking indistinguishable from one that was said.
        """
        await handle
        error = handle.exception() if hasattr(handle, "exception") else None
        if error is not None:
            logger.warning("a turn did not finish speaking: %s", error)
