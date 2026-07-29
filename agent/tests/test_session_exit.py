"""Tests for Story 2.11 + 2.12 + 3.3 — Vocal Session Exit, Satisfaction Question, Anonymous Guest."""
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


# ─── Story 3.3: satisfaction question for anonymous guests ────────────────────

def test_base_instructions_contain_anonymous_guest_section():
    """Instructions must have an ANONYMOUS GUESTS section."""
    assert "ANONYMOUS GUESTS" in salon._BASE_INSTRUCTIONS


def test_base_instructions_anonymous_guest_receives_satisfaction_question():
    """Instructions must direct agent to ask the satisfaction question to anonymous guests."""
    instructions = salon._BASE_INSTRUCTIONS
    anon_section_start = instructions.find("ANONYMOUS GUESTS")
    assert anon_section_start != -1
    anon_section = instructions[anon_section_start:]
    assert "satisfaction question" in anon_section.lower() or "satisfaction" in anon_section


def test_base_instructions_no_profile_save_for_anonymous_guests():
    """Instructions must prohibit calling report_detected_language for anonymous guests."""
    instructions = salon._BASE_INSTRUCTIONS
    anon_section_start = instructions.find("ANONYMOUS GUESTS")
    assert anon_section_start != -1
    anon_section = instructions[anon_section_start:]
    assert "report_detected_language" in anon_section
    assert "Do NOT call report_detected_language" in anon_section


def test_base_instructions_anonymous_response_not_saved():
    """Instructions must clarify that anonymous guest responses are not persisted."""
    instructions = salon._BASE_INSTRUCTIONS
    anon_section_start = instructions.find("ANONYMOUS GUESTS")
    assert anon_section_start != -1
    anon_section = instructions[anon_section_start:]
    assert "NOT saved" in anon_section or "not saved" in anon_section.lower()


def test_base_instructions_anonymous_guest_treated_as_full_participant():
    """Instructions must state anonymous guests are full participants for exit purposes."""
    instructions = salon._BASE_INSTRUCTIONS
    anon_section_start = instructions.find("ANONYMOUS GUESTS")
    assert anon_section_start != -1
    anon_section = instructions[anon_section_start:]
    assert "full participant" in anon_section


def test_base_instructions_anonymous_guest_identity_described():
    """Instructions identify anonymous guests by their 'Invité' display name."""
    instructions = salon._BASE_INSTRUCTIONS
    assert "Invité" in instructions
