"""A spoken "keep it private" reaches the same `private_to_agent` attribute the browser's
own toggle sets — and, once it is set, both the caption and the journal relay must honour it.

The second half was a real gap: `speaks_only_to_agent` already gated the caption in this
room, but nothing gated what got reported to the journal, so a participant's words were
relayed live to every other participant regardless of the toggle. Fixed in the same change
that gives the toggle a voice-triggered path in the first place.
"""
import asyncio
import inspect
import os
import sys
from unittest.mock import AsyncMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import agent as salon  # noqa: E402


# ─── The two tools ──────────────────────────────────────────────────────────────

def test_without_a_privacy_control_neither_tool_is_available():
    agent = salon.SalonAgent()
    assert asyncio.run(agent.keep_conversation_private()) == "not_available"
    assert asyncio.run(agent.back_to_the_salon()) == "not_available"


def test_keeping_it_private_sets_the_attribute_to_one():
    agent = salon.SalonAgent()
    toggle = AsyncMock()
    agent.set_privacy_control(toggle)

    assert asyncio.run(agent.keep_conversation_private()) == "private"
    toggle.assert_awaited_once_with("1")


def test_going_back_to_the_salon_sets_the_attribute_to_zero():
    agent = salon.SalonAgent()
    toggle = AsyncMock()
    agent.set_privacy_control(toggle)

    assert asyncio.run(agent.back_to_the_salon()) == "resumed"
    toggle.assert_awaited_once_with("0")


# ─── The journal relay honours the same toggle as the caption ──────────────────
#
# `_report_to_the_journal` is a closure registered deep inside `entrypoint`, the same as
# `_on_user_transcript` it has to agree with — there is no standalone function to import and
# call, so this is read out of the source the same way test_typed_messages.py already does
# for the sibling handler.

def _entrypoint_source() -> str:
    return inspect.getsource(salon.entrypoint)


def test_the_journal_handler_checks_the_same_toggle_as_the_caption_does():
    source = _entrypoint_source()
    start = source.index('@agent_session.on("user_input_transcribed")\n        def _report_to_the_journal')
    handler = source[start : source.index("\n\n", start)]
    assert "speaks_only_to_agent(" in handler
    assert "captions.attributed_speaker()" in handler
    # The guard has to return before the report, not after — checked by position, not just
    # presence, since a check that runs after link.report() already fired would be theatre.
    assert handler.index("speaks_only_to_agent(") < handler.index("link.report(")


def test_a_missing_caption_publisher_does_not_crash_the_journal_handler():
    """captions is declared None until the caption block runs; a handler that dereferenced
    it unconditionally would take the whole job down on the one path where captions never
    got set up at all."""
    source = _entrypoint_source()
    start = source.index('@agent_session.on("user_input_transcribed")\n        def _report_to_the_journal')
    handler = source[start : source.index("\n\n", start)]
    assert "captions is not None" in handler


# ─── The welcome mentions both phrases ──────────────────────────────────────────

def test_the_welcome_message_teaches_both_commands():
    assert "keep it private" in salon._WELCOME_MESSAGE
    assert "back to the Salon" in salon._WELCOME_MESSAGE
