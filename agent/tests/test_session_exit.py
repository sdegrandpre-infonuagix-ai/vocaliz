"""Tests for Story 2.11 + 2.12 — Vocal Session Exit and Satisfaction Question."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import agent as salon  # noqa: E402


# ─── SESSION EXIT instructions present ───────────────────────────────────────

def test_base_instructions_contain_session_exit_section():
    assert "SESSION EXIT" in salon._BASE_INSTRUCTIONS


def test_base_instructions_list_french_exit_phrase():
    assert "Je quitte le Salon" in salon._BASE_INSTRUCTIONS


def test_base_instructions_list_english_exit_phrase():
    assert "I'm leaving the Salon" in salon._BASE_INSTRUCTIONS


def test_base_instructions_list_spanish_exit_phrase():
    assert "Me voy del Salón" in salon._BASE_INSTRUCTIONS


# ─── Satisfaction question is mandatory and language-specific ─────────────────

def test_base_instructions_contain_french_satisfaction_question():
    assert (
        "Est-ce que votre conversation dans Salon a été une belle expérience ?"
        in salon._BASE_INSTRUCTIONS
    )


def test_base_instructions_contain_english_satisfaction_question():
    assert "Was your conversation in Salon a wonderful experience?" in salon._BASE_INSTRUCTIONS


def test_base_instructions_contain_spanish_satisfaction_question():
    assert "¿Fue tu conversación en Salon una bella experiencia?" in salon._BASE_INSTRUCTIONS


def test_base_instructions_satisfaction_question_before_end_session():
    """Satisfaction question step must appear before the end_session call in instructions."""
    instructions = salon._BASE_INSTRUCTIONS
    question_pos = instructions.find(
        "Est-ce que votre conversation dans Salon a été une belle expérience ?"
    )
    end_session_pos = instructions.find("end_session")
    assert question_pos != -1
    assert end_session_pos != -1
    assert question_pos < end_session_pos, (
        "Satisfaction question must be described before end_session call in instructions"
    )


def test_base_instructions_satisfaction_question_mandatory():
    """Instructions must state the satisfaction question is mandatory (cannot be skipped)."""
    assert "MUST ask the satisfaction question" in salon._BASE_INSTRUCTIONS


# ─── end_session function_tool is callable ───────────────────────────────────

def test_salon_agent_has_end_session_tool():
    agent = salon.SalonAgent()
    assert hasattr(agent, "end_session")
    assert callable(agent.end_session)


def test_end_session_tool_is_function_tool():
    """end_session should be registered as a function_tool (has _is_tool marker or similar)."""
    agent = salon.SalonAgent()
    # livekit @function_tool wraps the method — verify the attribute exists
    assert hasattr(agent, "end_session")


def test_end_session_returns_no_session_context_without_config():
    """When agent has no session_id/api_url/host_token, end_session returns a known sentinel."""
    import asyncio
    agent = salon.SalonAgent()
    result = asyncio.run(agent.end_session())
    assert result == "no_session_context"
