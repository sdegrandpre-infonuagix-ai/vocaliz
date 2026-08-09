"""The realtime session, seen as the two verbs the delivery loop needs.

`following.deliver` chooses between them and that choice is the cost of the product:

    say     the line is already in the listener's language — literal speech, no model call
    render  the line is in somebody else's — the model translates and speaks in one movement

Never a translation followed by a separate reading. That would double the latency and lose
the prosody of the original, which is most of what makes an interpreted conversation bearable
to sit through.

The instruction below is the one already used for a host's typed message, narrowed to one
listener. Its shape matters more than its wording: **the model is lending its voice to
somebody, not describing what they said.** An agent that says "Hans says hello" instead of
"hello" turns a conversation into a report of a conversation.
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


class SessionVoice:
    """A `following.Voice` backed by a live `AgentSession`.

    Holds the session and nothing else. Everything about which path a line takes is decided
    in `following.deliver`, so this stays the thinnest possible adapter — the place where a
    provider is named, and the only thing that would change if the provider did.
    """

    def __init__(self, session) -> None:
        self._session = session

    async def say(self, text: str) -> None:
        """Literal speech, for a line already in the listener's language.

        `say` and not `generate_reply`: there is nothing to translate, and sending it through
        the model would pay for a translation into the language it is already in — on every
        announcement, of every conversation.
        """
        if not text.strip():
            return
        await self._session.say(text)

    async def render(self, line: Line) -> None:
        """Through the model, which translates and speaks in one movement.

        `generate_reply` is not awaited, matching how the rest of this agent drives the
        session: it returns a handle to speech that is now under way, and awaiting it here
        would hold the delivery loop for the length of the sentence — which is exactly how
        one slow turn becomes a queue behind it.
        """
        if not line.text.strip():
            return
        self._session.generate_reply(instructions=instructions_for(line))
