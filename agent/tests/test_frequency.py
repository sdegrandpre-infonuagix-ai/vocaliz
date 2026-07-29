"""Tests for Story 2.7 — Vocal Intervention Frequency Adjustment."""
import importlib
import sys
import os
import pytest

# conftest.py registers livekit stubs before we import agent
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import agent as salon  # noqa: E402


# ─── Instructions ────────────────────────────────────────────────────────────

def test_base_instructions_mention_once_per_minute():
    assert "once per minute" in salon._BASE_INSTRUCTIONS


def test_base_instructions_mention_frequency_tool():
    assert "set_intervention_frequency" in salon._BASE_INSTRUCTIONS


def test_base_instructions_mention_parle_moins_souvent():
    assert "parle moins souvent" in salon._BASE_INSTRUCTIONS


def test_base_instructions_mention_interviens_plus():
    assert "interviens plus" in salon._BASE_INSTRUCTIONS


def test_base_instructions_mention_less_direction():
    assert "direction='less'" in salon._BASE_INSTRUCTIONS


def test_base_instructions_mention_more_direction():
    assert "direction='more'" in salon._BASE_INSTRUCTIONS


# ─── SalonAgent default state ─────────────────────────────────────────────────

def test_agent_default_frequency_is_normal():
    agent = salon.SalonAgent()
    assert agent._frequency_preference == "normal"


# ─── set_intervention_frequency tool ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_frequency_less_updates_preference():
    agent = salon.SalonAgent()
    result = await agent.set_intervention_frequency("less")
    assert agent._frequency_preference == "less"
    assert isinstance(result, str)
    assert len(result) > 0


@pytest.mark.asyncio
async def test_frequency_more_updates_preference():
    agent = salon.SalonAgent()
    result = await agent.set_intervention_frequency("more")
    assert agent._frequency_preference == "more"
    assert isinstance(result, str)


@pytest.mark.asyncio
async def test_frequency_normal_resets_preference():
    agent = salon.SalonAgent()
    await agent.set_intervention_frequency("less")
    result = await agent.set_intervention_frequency("normal")
    assert agent._frequency_preference == "normal"
    assert isinstance(result, str)


@pytest.mark.asyncio
async def test_frequency_invalid_direction_defaults_to_normal():
    agent = salon.SalonAgent()
    await agent.set_intervention_frequency("less")
    await agent.set_intervention_frequency("unknown_value")
    assert agent._frequency_preference == "normal"


@pytest.mark.asyncio
async def test_frequency_confirmations_are_in_french():
    agent = salon.SalonAgent()

    less_msg = await agent.set_intervention_frequency("less")
    more_msg = await agent.set_intervention_frequency("more")
    normal_msg = await agent.set_intervention_frequency("normal")

    # Each confirmation must be a non-empty French string
    for msg in (less_msg, more_msg, normal_msg):
        assert len(msg) > 10


@pytest.mark.asyncio
async def test_each_direction_has_distinct_confirmation():
    agent = salon.SalonAgent()
    less_msg = await agent.set_intervention_frequency("less")
    more_msg = await agent.set_intervention_frequency("more")
    normal_msg = await agent.set_intervention_frequency("normal")
    assert less_msg != more_msg
    assert more_msg != normal_msg
    assert less_msg != normal_msg
