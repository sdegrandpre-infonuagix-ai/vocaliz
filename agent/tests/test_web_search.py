"""The web and X search tools, granted the same way to both modes of `SalonAgent`.

`xai.WebSearch()` and `xai.XSearch()` are what actually grant the capabilities — server-side
tools that run on xAI's own infrastructure, unrelated to the `function_tool`s the framework
calls back into this process for. They travel with the tool list rather than with a
particular Realtime model version, so the same wiring covers both today's pinned "1.0" and a
future "2.0" — nothing here names a version, which is the point.

A tool being technically available does not mean a realtime voice model reaches for it
unprompted, so the second half of this file is the instructions that tell it when to.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import agent as salon  # noqa: E402


def test_the_facilitation_agent_is_granted_web_and_x_search():
    agent = salon.SalonAgent()

    assert len(agent.tools) == 2


def test_the_interpreter_agent_is_granted_them_too():
    """The same capabilities under follow_journal — nothing about the topology change should
    take search away from whichever mode is active."""
    agent = salon.SalonAgent(follow_journal=True)

    assert len(agent.tools) == 2


def test_both_prompts_are_told_when_to_use_web_search():
    facilitator = salon.SalonAgent()
    interpreter = salon.SalonAgent(follow_journal=True)

    assert "web search" in facilitator.instructions.lower()
    assert "web search" in interpreter.instructions.lower()


def test_both_prompts_are_told_when_to_use_x_search():
    facilitator = salon.SalonAgent()
    interpreter = salon.SalonAgent(follow_journal=True)

    assert "x search" in facilitator.instructions.lower()
    assert "x search" in interpreter.instructions.lower()


def test_the_web_search_instruction_bounds_when_it_is_used():
    """A tool granted with no guidance gets reached for on things the model already knows
    perfectly well, which is a pause and a cost for nothing."""
    text = salon._WEB_SEARCH_INSTRUCTIONS.lower()

    assert "current" in text or "changed since" in text
    assert "do not search for things you already know" in text


def test_the_x_search_instruction_bounds_when_it_is_used():
    """X search is for what web search is not — real-time reaction, a specific account, a
    post going around — not a settled fact a plain web search would surface just as well."""
    text = salon._WEB_SEARCH_INSTRUCTIONS.lower()

    assert "x (formerly twitter)" in text
    assert "sentiment" in text or "real-time reaction" in text
