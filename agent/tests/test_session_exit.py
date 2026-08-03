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
        "Est-ce que votre conversation dans Vocaliz a été une belle expérience ?"
        in salon._BASE_INSTRUCTIONS
    )


def test_base_instructions_contain_english_satisfaction_question():
    assert "Was your conversation in Vocaliz a wonderful experience?" in salon._BASE_INSTRUCTIONS


def test_base_instructions_contain_spanish_satisfaction_question():
    assert "¿Fue tu conversación en Vocaliz una bella experiencia?" in salon._BASE_INSTRUCTIONS


def test_base_instructions_satisfaction_question_before_end_session():
    """Satisfaction question step must appear before the end_session call in instructions."""
    instructions = salon._BASE_INSTRUCTIONS
    question_pos = instructions.find(
        "Est-ce que votre conversation dans Vocaliz a été une belle expérience ?"
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

def test_base_instructions_contain_guest_without_account_section():
    """Instructions must have an ANONYMOUS GUESTS section."""
    assert "GUESTS WITHOUT AN ACCOUNT" in salon._BASE_INSTRUCTIONS


def test_base_instructions_guest_without_account_receives_satisfaction_question():
    """Instructions must direct agent to ask the satisfaction question to anonymous guests."""
    instructions = salon._BASE_INSTRUCTIONS
    anon_section_start = instructions.find("GUESTS WITHOUT AN ACCOUNT")
    assert anon_section_start != -1
    anon_section = instructions[anon_section_start:]
    assert "satisfaction question" in anon_section.lower() or "satisfaction" in anon_section


def test_base_instructions_no_profile_save_for_guests_without_account():
    """Instructions must prohibit calling report_detected_language for anonymous guests."""
    instructions = salon._BASE_INSTRUCTIONS
    anon_section_start = instructions.find("GUESTS WITHOUT AN ACCOUNT")
    assert anon_section_start != -1
    anon_section = instructions[anon_section_start:]
    assert "report_detected_language" in anon_section
    assert "Do NOT call report_detected_language" in anon_section


def test_base_instructions_do_not_claim_guest_answers_are_discarded():
    """The prompt used to promise anonymous answers were never stored. It is now false.

    Guest satisfaction is recorded in salon_events like anyone else's, so the claim had to
    go. This guards against it being reinstated: a prompt that misdescribes what we keep
    is worse than one that says nothing.
    """
    anon = salon._BASE_INSTRUCTIONS[salon._BASE_INSTRUCTIONS.find("GUESTS WITHOUT AN ACCOUNT"):]
    assert anon
    assert "not saved" not in anon.lower()
    assert "not persisted" not in anon.lower()


def test_base_instructions_guest_without_account_treated_as_full_participant():
    """Instructions must state anonymous guests are full participants for exit purposes."""
    instructions = salon._BASE_INSTRUCTIONS
    anon_section_start = instructions.find("GUESTS WITHOUT AN ACCOUNT")
    assert anon_section_start != -1
    anon_section = instructions[anon_section_start:]
    assert "full participant" in anon_section


def test_base_instructions_guest_without_account_identity_described():
    """Guests are named 'Guest XXXX' now, not a single shared 'Invité'.

    The four characters are what lets the agent — and everyone else — tell two guests
    apart, so the prompt has to describe the shape it will actually see.
    """
    instructions = salon._BASE_INSTRUCTIONS
    assert "Guest 3F2A" in instructions
    assert "Invité" not in instructions


# ─── Sponsorship mention ─────────────────────────────────────────────────────

def test_base_instructions_mention_infonuagix_once_at_welcome():
    """The advertising aside belongs to the greeting, and only to the greeting."""
    instructions = salon._BASE_INSTRUCTIONS
    assert "Infonuagix.ai" in instructions
    section = instructions[instructions.find("SPONSORSHIP MENTION"):]
    assert section, "the mention must live in its own section, not buried in prose"
    # Bounded on purpose: one sentence, to newcomers only, with no second attempt.
    # Without these the model is free to bring it up again mid-conversation.
    assert "ONE short sentence" in section
    assert "never bring it up again" in section


def test_sponsorship_mention_survives_both_opening_paths():
    """A salon may open with a source or without one; the greeting happens either way."""
    with_source = salon._build_instructions(source_summary="A brief.", source_type="url")
    without_source = salon._build_instructions()
    for instructions in (with_source, without_source):
        assert "Infonuagix.ai" in instructions


# ─── Answering from the sources ──────────────────────────────────────────────

def test_agent_exposes_search_and_history_tools():
    a = salon.SalonAgent()
    for tool in ("search_source", "is_first_salon"):
        assert callable(getattr(a, tool, None)), tool


def test_instructions_forbid_inventing_details():
    """The summary is a brief, so the model must look things up rather than fill gaps."""
    section = salon._BASE_INSTRUCTIONS[
        salon._BASE_INSTRUCTIONS.find("ANSWERING FROM THE SOURCES"):
    ]
    assert section
    assert "search_source" in section
    # Both failure modes are named: inventing a fact, and denying one without looking.
    assert "Never invent" in section
    assert "without having searched" in section


def test_sponsorship_is_gated_on_being_a_newcomer():
    section = salon._BASE_INSTRUCTIONS[
        salon._BASE_INSTRUCTIONS.find("SPONSORSHIP MENTION"):
    ]
    assert "is_first_salon" in section
    assert "'returning'" in section
    assert "say nothing about it at all" in section


# ─── Transcription notice ────────────────────────────────────────────────────

def test_base_instructions_announce_transcription():
    """Speech is now stored. Everyone in the room has to be told, out loud."""
    section = salon._BASE_INSTRUCTIONS[
        salon._BASE_INSTRUCTIONS.find("TRANSCRIPTION NOTICE"):
    ]
    assert section, "the notice must have its own section, not be buried in prose"
    assert "transcribed" in section
    # Matched without the article: the prompt wraps between "their" and "own language".
    assert "own language" in section


def test_transcription_notice_is_not_gated_on_being_a_newcomer():
    """Unlike the sponsorship aside, this one is owed to returning participants too."""
    section = salon._BASE_INSTRUCTIONS[
        salon._BASE_INSTRUCTIONS.find("TRANSCRIPTION NOTICE"):
        salon._BASE_INSTRUCTIONS.find("SPONSORSHIP MENTION")
    ]
    assert "is_first_salon" not in section
    assert "returning participants too" in section


def test_transcription_notice_does_not_ask_for_permission():
    """A consent prompt the agent cannot honour would be worse than a plain statement."""
    section = salon._BASE_INSTRUCTIONS[
        salon._BASE_INSTRUCTIONS.find("TRANSCRIPTION NOTICE"):
        salon._BASE_INSTRUCTIONS.find("SPONSORSHIP MENTION")
    ]
    assert "do not ask for permission" in section


def test_transcription_notice_survives_both_opening_paths():
    for instructions in (
        salon._build_instructions(source_summary="A brief.", source_type="url"),
        salon._build_instructions(),
    ):
        assert "TRANSCRIPTION NOTICE" in instructions
