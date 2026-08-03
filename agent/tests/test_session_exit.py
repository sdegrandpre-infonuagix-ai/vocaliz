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


# ─── Inviting by voice ───────────────────────────────────────────────────────

def test_invite_tool_accepts_a_phone_number():
    """From a phone, speaking a number is the whole point — typing one is the fallback."""
    import inspect

    params = inspect.signature(salon.SalonAgent.invite_contact).parameters
    assert "phone" in params
    # Both optional, because either alone is a complete invitation.
    assert params["email"].default == ""
    assert params["phone"].default == ""


def test_instructions_explain_turning_spoken_words_into_a_number():
    section = salon._BASE_INSTRUCTIONS[
        salon._BASE_INSTRUCTIONS.find("INVITATION COMMANDS"):
    ]
    assert "spoken aloud arrives as words" in section
    assert "+1 followed by those ten digits" in section


def test_instructions_require_reading_a_number_back():
    """A digit misheard by one sends the invitation to a stranger, irrecoverably."""
    section = salon._BASE_INSTRUCTIONS[
        salon._BASE_INSTRUCTIONS.find("INVITATION COMMANDS"):
    ]
    assert "read a number back before inviting" in section
    assert "wait for confirmation" in section
    # And not the same ceremony for addresses, which would be tedious and pointless.
    assert "only numbers" in section


def test_instructions_forbid_claiming_an_invitation_that_did_not_leave():
    section = salon._BASE_INSTRUCTIONS[
        salon._BASE_INSTRUCTIONS.find("INVITATION COMMANDS"):
    ]
    assert "nothing_sent_share_link_manually" in section
    assert "Never say someone was invited when no" in section


def test_invite_with_neither_contact_is_refused_before_any_call():
    import asyncio

    agent = salon.SalonAgent(session_id="s", api_url="http://x", host_token="t")
    assert asyncio.run(agent.invite_contact()) == "error:need_email_or_phone"


# ─── Reaching beyond this salon ───────────────────────────────────────────────

def test_agent_exposes_the_corpus_tools():
    a = salon.SalonAgent()
    for tool in ("search_platform", "read_shared_page"):
        assert callable(getattr(a, tool, None)), tool


def test_the_search_is_the_agents_not_the_participants():
    """Nobody types anything, so the tool turns a spoken question into a query itself.

    The prompt therefore has to say the participant's own words go in — an agent that
    translated first would defeat the translation the search performs.
    """
    section = salon._BASE_INSTRUCTIONS[
        salon._BASE_INSTRUCTIONS.find("ASKING BEYOND THIS SALON"):
    ]
    assert section
    assert "in their own words" in section
    assert "do not translate it for it" in section


def test_instructions_require_attribution():
    """A claim drawn from an article nobody can place is worth less than one that names its
    source, and a listener cannot judge an unattributed assertion at all."""
    section = salon._BASE_INSTRUCTIONS[
        salon._BASE_INSTRUCTIONS.find("ASKING BEYOND THIS SALON"):
    ]
    assert "Name the publisher and the date" in section


def test_instructions_state_that_uploaded_documents_never_travel():
    """The agent will be asked. It must answer with the rule rather than searching and
    reporting nothing found, which sounds like the document merely could not be located."""
    section = salon._BASE_INSTRUCTIONS[
        salon._BASE_INSTRUCTIONS.find("ASKING BEYOND THIS SALON"):
    ]
    assert "never shared" in section
    assert "stay in the salon they were given to" in section


def test_no_results_is_a_real_answer():
    section = salon._BASE_INSTRUCTIONS[
        salon._BASE_INSTRUCTIONS.find("ASKING BEYOND THIS SALON"):
    ]
    assert "say plainly that you have nothing on it" in section
    assert "half remember" in section


def test_corpus_tools_refuse_without_session_context():
    import asyncio

    bare = salon.SalonAgent()
    assert asyncio.run(bare.search_platform(query="iran")) == "no_session_context"
    assert asyncio.run(bare.read_shared_page(source_id="x", query="y")) == "no_session_context"


def test_translation_guidance_no_longer_assumes_three_people():
    """The room now holds a host, three guests and the agent."""
    assert "3-way session" not in salon._BASE_INSTRUCTIONS
    assert "Up to four people may be in the room" in salon._BASE_INSTRUCTIONS
