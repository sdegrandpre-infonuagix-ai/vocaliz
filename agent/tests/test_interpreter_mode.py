"""The interpreter's silence, and the one thing it says anyway.

Tranche 4 of Story 11.1. Under the per-participant topology this agent's room holds exactly
one human, and what to say to them is decided entirely by the orchestrator.

**The reply is suppressed by `_journal_linked`, not by `follow_journal`, and that is not the
same flag by an oversight — it is the fix for a real production silence.** `follow_journal`
is decided the moment a job starts; whether the journal actually got linked depends on a
background task that waits for the human to connect and then joins the orchestrator, either
of which can fail. The first version of this file gated the reply on `follow_journal` alone:
a link that failed for any reason left the agent mute for the rest of the conversation — no
automatic reply (suppressed) and nothing from the journal either (never linked). Gating on
confirmation instead means a failed link falls back to the old facilitation behaviour, which
is the wrong topology but a working one.

**Silence is not the same as disappearing.** A model told to say nothing unless instructed is
still the first voice a participant hears in their room — the one-shot introduction is what
keeps that from reading as a broken connection.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import agent as salon  # noqa: E402


# ─── Which prompt ───────────────────────────────────────────────────────────────


def test_the_old_topology_still_gets_the_facilitation_prompt_by_default():
    """`follow_journal` defaults to False, matching every dispatch that predates Story
    11.1 — dial_in, call_the_desk, and any job whose Salon has no orchestrator holding it."""
    agent = salon.SalonAgent()

    assert "facilitator" in agent.instructions
    assert "personal voice interpreter" not in agent.instructions


def test_follow_journal_selects_the_interpreter_prompt_instead():
    agent = salon.SalonAgent(follow_journal=True)

    assert "personal voice interpreter" in agent.instructions
    assert "facilitator" not in agent.instructions


def test_the_interpreter_prompt_says_to_stay_silent_otherwise():
    agent = salon.SalonAgent(follow_journal=True)

    assert "silent" in agent.instructions.lower()


def test_a_forced_language_still_applies_under_follow_journal():
    """`_language_override` is orthogonal to which base prompt was chosen — pinning the
    spoken language has to survive the switch to interpreter mode exactly as it did before."""
    agent = salon.SalonAgent(follow_journal=True, forced_language="es-MX")

    assert "es-MX" in agent.instructions


# ─── Whether it replies on its own ───────────────────────────────────────────────


def test_follow_journal_alone_does_not_yet_silence_anything():
    """The flag that starts every job under this topology, and by itself proves nothing:
    the journal has not been confirmed linked yet, so the model must still be free to reply
    normally — the fail-open state, not a bug."""
    agent = salon.SalonAgent(follow_journal=True)

    assert agent._journal_linked is False


@pytest.mark.asyncio
async def test_a_confirmed_link_silences_the_automatic_reply():
    """The mechanism that makes the prompt true rather than aspirational, once the journal
    is actually there to speak for. Without this, the framework calls its own reply
    generation right after this returns — the same automatic response the interpreter
    prompt says never to make."""
    agent = salon.SalonAgent(follow_journal=True)
    agent._journal_linked = True  # what the background join sets on success

    try:
        await agent.on_user_turn_completed(None, None)
    except salon.StopResponse:
        return
    assert False, "on_user_turn_completed did not raise StopResponse once linked"


@pytest.mark.asyncio
async def test_an_unconfirmed_link_replies_normally_instead_of_going_mute():
    """The regression this whole flag exists to prevent: `follow_journal=True` with a link
    that never confirmed — a failed join, a participant who never connected — must fall back
    to the model's own replies rather than leaving the agent silent for the whole
    conversation."""
    agent = salon.SalonAgent(follow_journal=True)  # _journal_linked never set

    await agent.on_user_turn_completed(None, None)  # must not raise


@pytest.mark.asyncio
async def test_the_old_topology_still_replies_automatically():
    """Nothing about dial_in, call_the_desk, or a Salon with no orchestrator should change:
    the default construction must not raise, or every existing facilitation flow goes mute."""
    agent = salon.SalonAgent()

    await agent.on_user_turn_completed(None, None)  # must not raise


# ─── The one thing it says on its own ────────────────────────────────────────────


def test_the_one_shot_intro_names_the_language_and_the_product():
    text = salon._journal_intro_instructions("fr")

    assert "fr" in text
    assert "Vocaliz" in text
    assert "interpreter" in text.lower()


def test_the_one_shot_intro_does_not_invite_a_reply():
    """Introducing itself and then waiting for an answer would be exactly the kind of
    initiative the interpreter prompt tells it never to take."""
    text = salon._journal_intro_instructions("fr").lower()

    assert "ask" not in text or "ask nothing" in text
