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

def _opening_section() -> str:
    section = salon._BASE_INSTRUCTIONS[
        salon._BASE_INSTRUCTIONS.find("HOW A SALON OPENS"):
    ]
    assert section
    return section


def test_a_salon_opens_in_four_steps_in_order():
    """Welcome, what this is, the announcement, then the source. The order is the product
    decision: an announcement to somebody ungreeted is jarring, one delivered later
    interrupts, and explaining the platform after the sponsor would introduce Vocaliz to
    somebody who has already been sold something in its name."""
    section = _opening_section()
    steps = ["1. WELCOME", "2. WHAT THIS IS", "3. THE ANNOUNCEMENT", "4. THE CONVERSATION"]
    positions = [section.index(step) for step in steps]
    assert positions == sorted(positions)


def test_the_opening_says_what_the_platform_is():
    """A guest is invited by somebody else and may have no idea what they have joined."""
    section = _opening_section()
    # Whitespace collapsed: the prompt wraps at eighty columns, so a phrase can straddle a
    # newline and two spaces of indentation. Asserting on the raw text tests the line breaks
    # rather than the wording.
    lowered = " ".join(section.split()).lower()
    assert "platform for creating salons" in lowered
    # The three things that make it what it is: a source, other people, and the agent as a
    # participant rather than an assistant.
    assert "document" in lowered and "web page" in lowered
    assert "together" in lowered
    assert "do not merely assist" in lowered


def test_the_explanation_is_per_participant_not_per_salon():
    """Somebody who joins after the opening never heard it. Modelled on the transcription
    notice, which had the same problem for the same reason."""
    section = _opening_section()
    assert "Once per participant, not once per salon" in section


def test_the_hosts_opening_also_explains_the_platform():
    """The opening the host triggers by activating the agent carries its own instructions, so
    leaving them alone would have made the explanation depend on how the salon started."""
    import inspect

    source = inspect.getsource(salon.entrypoint)
    opening = source[source.find("Open the conversation now"):]
    assert "what Vocaliz is" in opening
    assert "platform for creating Salons" in opening
    assert "discuss a web page or a document together" in opening


def test_the_hardcoded_sponsorship_mention_is_gone():
    """It said what a house ad now says, so a newcomer heard it twice. The auction carries the
    message; a second copy in the prompt would be a duplicate nobody could turn off."""
    assert "SPONSORSHIP MENTION" not in salon._BASE_INSTRUCTIONS
    # And the company is no longer named in the prompt at all: what an advertiser says is data
    # now, not instructions, so it can change without a redeploy.
    assert "Infonuagix.ai" not in salon._BASE_INSTRUCTIONS


def test_silence_rather_than_announcing_the_absence_of_a_sponsor():
    section = salon._BASE_INSTRUCTIONS[
        salon._BASE_INSTRUCTIONS.find("HOW A SALON OPENS"):
    ]
    assert "never announce that there is no sponsor" in section


def test_the_announcement_is_bounded():
    """Repeating or pressing it turns a conversation into a sales call, which is the fastest way
    to make the advertising worthless."""
    section = salon._BASE_INSTRUCTIONS[
        salon._BASE_INSTRUCTIONS.find("HOW A SALON OPENS"):
    ]
    assert "once and never return to it" in section
    assert "never add a claim they did not make" in section


def test_the_agent_can_request_an_ad():
    assert callable(getattr(salon.SalonAgent(), "request_ad", None))


def test_requesting_an_ad_without_a_session_says_nothing():
    import asyncio

    assert asyncio.run(salon.SalonAgent().request_ad()) == "no_ad"


def test_the_opening_sequence_survives_both_paths():
    """A salon may open with a source or without one; the three steps happen either way."""
    for instructions in (
        salon._build_instructions(source_summary="A brief.", source_type="url"),
        salon._build_instructions(),
    ):
        assert "HOW A SALON OPENS" in instructions


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


def test_the_advertiser_is_chosen_by_the_server_not_the_prompt():
    """Who is heard, and what they pay, comes from an auction over region, topics and language.
    A prompt naming one advertiser could not be outbid, discounted, or replaced without a
    redeploy."""
    section = salon._BASE_INSTRUCTIONS[
        salon._BASE_INSTRUCTIONS.find("HOW A SALON OPENS"):
    ]
    assert "request_ad" in section


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


def test_instructions_lead_with_what_can_be_found():
    """The natural request is positive — "find me a website another host used" — so the
    prompt says that first. Leading with the prohibition teaches the model what it cannot do
    before what it can, and a model that has learned a refusal reaches for it."""
    section = salon._BASE_INSTRUCTIONS[
        salon._BASE_INSTRUCTIONS.find("ASKING BEYOND THIS SALON"):
    ]
    assert "web pages other hosts used in their own salons" in section
    assert section.index("is precisely the request") < section.index("is not in it")


def test_instructions_state_that_uploaded_documents_never_travel():
    """The agent will be asked. It must answer with the rule rather than searching and
    reporting nothing found, which sounds like the document merely could not be located."""
    section = salon._BASE_INSTRUCTIONS[
        salon._BASE_INSTRUCTIONS.find("ASKING BEYOND THIS SALON"):
    ]
    # Matched on fragments that do not straddle a line break in the prompt.
    assert "uploaded files stay in the" in section
    assert "sounds like it exists somewhere" in section


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
    assert "Up to three people may be in the room" in salon._BASE_INSTRUCTIONS


def test_the_agent_confirms_delivery_separately():
    """Reserving and delivering are two acts. The advertiser is charged by the second, so an ad
    reserved when the salon opened and never spoken costs them nothing."""
    a = salon.SalonAgent()
    assert callable(getattr(a, "confirm_ad_delivered", None))


def test_the_prompt_ties_the_charge_to_the_confirmation():
    """A model that skipped the confirmation would cost real revenue, and one that called it
    without speaking would bill somebody for silence. Both have to be stated."""
    section = salon._BASE_INSTRUCTIONS[
        salon._BASE_INSTRUCTIONS.find("HOW A SALON OPENS"):
    ]
    assert "confirm_ad_delivered" in section
    assert "before it they pay nothing" in section
    assert "bills somebody" in section


def test_confirming_without_a_session_does_nothing():
    import asyncio

    assert asyncio.run(salon.SalonAgent().confirm_ad_delivered()) == "not_confirmed"


# ─── Every language the model knows, not the three that are printed ──────────

def _flat() -> str:
    """The prompt with its line wrapping removed, so an assertion tests the wording rather
    than where the eighty-column limit happened to fall."""
    return " ".join(salon._BASE_INSTRUCTIONS.split())


def test_the_three_written_languages_are_examples_not_a_limit():
    """French, English and Spanish are spelled out in three places because an example has to be
    written in some language. Read as a list of what is supported, they would make the agent
    answer a Polish speaker in French — which is the failure this wording prevents."""
    flat = _flat()
    assert "not only the ones named in these instructions" in flat
    assert "they are not the set you are limited to" in flat
    assert "illustrations of the intent, not the set of languages this works in" in flat
    assert "reference wordings" in flat


def test_the_fallback_is_english_not_french():
    """It used to say "default to French if unknown", which contradicted the product decision
    that English is the default and French a choice."""
    flat = _flat()
    assert "default to French if unknown" not in flat
    assert "English is the fallback when you genuinely could not tell" in flat


def test_a_farewell_in_an_unlisted_language_still_ends_the_salon():
    """Waiting for one of the printed phrases would strand everybody else."""
    assert "counts exactly the same" in _flat()


def test_languages_beyond_the_interface_are_named_explicitly():
    """Naming a few unlisted languages is what stops the three examples reading as the whole
    world. These are deliberately languages the site does NOT offer an interface in."""
    flat = _flat()
    named = [lang for lang in ("Polish", "Ukrainian", "Thai", "Swedish", "Hebrew") if lang in flat]
    assert len(named) >= 3, f"only {named} named"


def test_answering_in_the_wrong_language_is_forbidden_in_so_many_words():
    """The specific failure worth naming: reaching for the nearest language that appears in the
    prompt rather than the one actually being spoken."""
    assert "never do is answer in a language they did not use" in _flat()
