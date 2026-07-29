"""Tests for Story 2.10 — Simultaneous Translation and Echo Prevention."""
import os
import sys
import json
import pytest
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import agent as salon  # noqa: E402


# ─── Helper: build a mock room ───────────────────────────────────────────────

def make_mock_room():
    room = MagicMock()
    room.local_participant.publish_data = AsyncMock(return_value=None)
    return room


# ─── Instructions ────────────────────────────────────────────────────────────

def test_base_instructions_mention_simultaneous_translation():
    assert "SIMULTANEOUS TRANSLATION" in salon._BASE_INSTRUCTIONS


def test_base_instructions_mention_mute_tool():
    assert "mute_translation_recipient" in salon._BASE_INSTRUCTIONS


def test_base_instructions_mention_unmute_tool():
    assert "unmute_translation_recipient" in salon._BASE_INSTRUCTIONS


def test_base_instructions_no_interrupt_original_speaker():
    assert "NEVER interrupt" in salon._BASE_INSTRUCTIONS


# ─── SalonAgent room wiring ───────────────────────────────────────────────────

def test_agent_stores_room_reference():
    mock_room = make_mock_room()
    agent = salon.SalonAgent(room=mock_room)
    assert agent._room is mock_room


def test_agent_room_defaults_to_none():
    agent = salon.SalonAgent()
    assert agent._room is None


# ─── mute_translation_recipient ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_mute_sends_mute_start_data_message():
    mock_room = make_mock_room()
    agent = salon.SalonAgent(room=mock_room)
    result = await agent.mute_translation_recipient()
    assert result == "muted"
    mock_room.local_participant.publish_data.assert_called_once()
    call_args = mock_room.local_participant.publish_data.call_args
    payload = call_args[0][0]  # first positional arg
    msg = json.loads(payload.decode())
    assert msg["action"] == "translation_mute_start"


@pytest.mark.asyncio
async def test_mute_returns_muted_without_room():
    agent = salon.SalonAgent()
    result = await agent.mute_translation_recipient()
    assert result == "muted"


# ─── unmute_translation_recipient ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_unmute_sends_mute_end_data_message():
    mock_room = make_mock_room()
    agent = salon.SalonAgent(room=mock_room)
    result = await agent.unmute_translation_recipient()
    assert result == "unmuted"
    call_args = mock_room.local_participant.publish_data.call_args
    payload = call_args[0][0]
    msg = json.loads(payload.decode())
    assert msg["action"] == "translation_mute_end"


@pytest.mark.asyncio
async def test_unmute_returns_unmuted_without_room():
    agent = salon.SalonAgent()
    result = await agent.unmute_translation_recipient()
    assert result == "unmuted"


# ─── Publish error is swallowed ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_mute_swallows_publish_exception():
    mock_room = make_mock_room()
    mock_room.local_participant.publish_data = AsyncMock(side_effect=Exception("network error"))
    agent = salon.SalonAgent(room=mock_room)
    # Must not raise
    result = await agent.mute_translation_recipient()
    assert result == "muted"
