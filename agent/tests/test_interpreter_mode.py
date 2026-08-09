"""The interpreter's silence, and the one thing it says anyway.

Tranche 4 of Story 11.1. Under the per-participant topology this agent's room holds exactly
one human, and what to say to them is decided entirely by the orchestrator. Two things had to
change together, and this file is what holds them to that:

**The prompt and the reply-suppression must agree.** A facilitation prompt paired with a
silenced reply would leave the model composing interventions it is never allowed to speak; an
interpreter prompt paired with an un-silenced reply would let the model's own opinion answer
its human directly, on top of whatever the orchestrator asked for. `follow_journal` is the one
switch that must move both at once.

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


@pytest.mark.asyncio
async def test_follow_journal_silences_the_automatic_reply():
    """The mechanism that makes the prompt true rather than aspirational. Without this, the
    framework calls its own reply generation right after this returns — the same automatic
    response the interpreter prompt says never to make."""
    agent = salon.SalonAgent(follow_journal=True)

    try:
        await agent.on_user_turn_completed(None, None)
    except salon.StopResponse:
        return
    assert False, "on_user_turn_completed did not raise StopResponse under follow_journal"


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
