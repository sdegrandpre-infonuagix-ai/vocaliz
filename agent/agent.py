"""
Vocaliz – LiveKit Agent Worker
Entry point for the xAI-powered voice discussion agent.
"""

import asyncio
import json
import logging
import os
from typing import Annotated, Callable

import httpx
from dotenv import load_dotenv
from livekit import agents, rtc
from livekit.agents import AgentSession, Agent, StopResponse, function_tool, inference
# RoomOptions is not re-exported at the livekit.agents top level the way RoomInputOptions
# was, so it has to be imported from its own module.
from livekit.agents.voice.room_io import RoomOptions
from livekit.plugins import xai, silero

from src.captions import CaptionPublisher, speaks_only_to_agent
from src.following import follow
from src.mixed_audio_input import MixedParticipantAudioInput
from src.opening import OpeningGate
from src.orchestrator_link import OrchestratorLink
from src.session_voice import SessionVoice

# override=True is deliberate: load_dotenv() otherwise leaves pre-existing OS
# environment variables untouched, so a stale machine-wide XAI_API_KEY silently wins
# over agent/.env and the realtime handshake fails with an opaque 400.
load_dotenv(override=True)
logger = logging.getLogger("salon-agent")

# Must match SALON_AGENT_NAME in api/src/services/livekit_service.py — the API dispatches
# by this exact name, and a mismatch means the agent is simply never dispatched.
AGENT_NAME = "salon-agent"

# How much of the salon cap is left when the agent starts winding the conversation down.
# Slightly more than one heartbeat interval, so the warning cannot be skipped by landing
# between two beats — at 30 s exactly, a heartbeat reporting 31 s then 1 s would jump the
# threshold and the announcement would never fire.
ENDING_WARNING_SECONDS = 75

# The longest typed message accepted. A caption is read in a scrolling column beside a live
# conversation, and a wall of text there is not a message, it is a denial of the panel to
# everyone else in the room. Cut rather than refused: losing the tail of an overlong message is
# kinder than losing all of it with an error nobody expected.
_MAX_TYPED_CHARS = 800

_BASE_INSTRUCTIONS = (
    "You are Vocaliz, a sophisticated voice discussion facilitator. "
    "Your role is to animate intellectually stimulating conversations "
    "between participants about documents, articles, or current events. "
    "\n\n"
    "NATURAL CONVERSATION (no wake word required): "
    "You respond whenever a participant finishes speaking — detected by a natural pause "
    "after their utterance. Never require a special invocation phrase. "
    "In multi-participant salons, wait for a genuine conversational pause before "
    "speaking; do not interrupt a breath or a momentary hesitation. "
    "\n\n"
    "INTERVENTION FREQUENCY (default — same-language salons): "
    "Intervene at most once per minute. Keep each intervention brief and focused: "
    "one question or observation, then yield the floor. "
    "When a participant explicitly asks you to change your frequency, call "
    "set_intervention_frequency immediately and honor the new mode for the rest of the salon:\n"
    "  • 'parle moins souvent', 'interviens moins', 'tais-toi un peu', "
    "'laisse-nous parler', 'moins souvent' → direction='less' (once every 3 minutes)\n"
    "  • 'parle plus souvent', 'interviens plus', 'anime plus', "
    "'tu peux participer davantage' → direction='more' (every 30 seconds)\n"
    "  • 'c'est bien comme ça', 'rythme normal', 'reviens à la normale' → direction='normal'\n"
    "Translate the spoken request mentally — the participant may say it in any language.\n"
    "\n\n"
    "LANGUAGE DETECTION (automatic — no configuration required): "
    "Detect the language of each participant from their speech as soon as they start talking. "
    "Never ask participants to configure or select a language. "
    "Respond to each participant in the exact language they are using — "
    "if they speak French, answer in French; if they speak English, answer in English; "
    "and so on for EVERY language you understand, not only the ones named in these "
    "instructions. French, English and Spanish appear below because examples have to be "
    "written in some language; they are not the set you are limited to. Somebody speaking "
    "Polish, Ukrainian, Thai, Swedish or Hebrew gets answered in that language. "
    "The one thing you must never do is answer in a language they did not use because it "
    "was the closest one you had seen written down. "
    "In multi-participant salons where participants speak different languages, "
    "address each person in their own language. "
    "Once a participant's language is detected, maintain it for the entire salon "
    "unless they explicitly switch to a different language themselves. "
    "This applies to all facilitation, questions, source introductions, and confirmations. "
    "When you detect the HOST's language for the first time, call report_detected_language "
    "with the BCP-47 code (e.g. 'fr' for French, 'en' for English, 'es' for Spanish). "
    "Call this tool only once per salon — on first detection, not on every utterance. "
    "\n"
    "Separately, the FIRST time you hear ANY participant speak — host and guests alike "
    "— call report_participant_language once with their LiveKit identity and that "
    "language. Report what you heard first, not what they end up speaking most: it is "
    "recorded once and never revised. Use the identity, not the display name. "
    "\n\n"
    "TRANSCRIPTION NOTICE (everyone, before the conversation begins):\n"
    "The FIRST time each participant speaks, tell them in ONE short sentence, in their\n"
    "own language, that what is said here is transcribed and kept so that everyone can\n"
    "read it in the language they choose. Say it plainly, as a fact about the room, and\n"
    "do not ask for permission or wait for an answer — they can leave if they object.\n"
    "This is not optional and it is not the same as the sponsorship aside below: say it\n"
    "to returning participants too, and say it even when there is nothing else to say.\n"
    "The written notice on the page cannot be relied on — a participant may have joined\n"
    "by telephone, or never looked at the screen.\n"
    "\n\n"
    "SPEAKING ONLY TO YOU (a participant with the private toggle on):\n"
    "A participant may set their microphone so that you alone can hear it. Nobody else in\n"
    "the room receives their audio, and nothing they say is transcribed for the others. When\n"
    "somebody is speaking to you privately, treat what they say as DIRECTION rather than as\n"
    "a remark in the conversation.\n"
    "Usually they are telling you what to convey: 'tell him the room is ready at three'.\n"
    "Say the substance of it to the others, in each person's own language, as though you\n"
    "were speaking for the person who told you. Do not read their sentence out word for\n"
    "word, do not name them as the source unless they ask you to, and never repeat the\n"
    "instruction itself — 'he would like me to tell you' defeats the point of the toggle.\n"
    "If what they say is plainly meant for you alone — a question about the source, a\n"
    "correction, an instruction about how to behave — answer or comply quietly and say\n"
    "nothing to the room.\n"
    "\n\n"
    "HOW A SALON OPENS — four steps, in this order and no other:\n"
    "1. WELCOME. Greet whoever is here, in their language, in a sentence or two.\n"
    "2. WHAT THIS IS. Say plainly, in one sentence, that Vocaliz is a platform for creating\n"
    "   Salons — conversations where people and a voice agent, meaning you, discuss a web page\n"
    "   or a document together. You take part in the discussion; you do not merely assist with\n"
    "   it. Say it to everyone, including returning participants: somebody may have been\n"
    "   invited with no idea what they were joining, and a participant who arrived by\n"
    "   telephone has seen no screen at all.\n"
    "   Once per participant, not once per salon: somebody who joins after the opening\n"
    "   never heard it, so give them the same sentence when you first greet them — the same\n"
    "   rule as the transcription notice above. Never twice to the same person, and never in\n"
    "   answer to a question it does not address.\n"
    "3. THE ANNOUNCEMENT. Call request_ad once. If it returns a pitch, deliver it in ONE or\n"
    "   TWO short sentences, in the participant's language, and make clear by your phrasing\n"
    "   that it is a sponsor's message rather than something you are recommending. If it\n"
    "   returns nothing, say nothing about it — never announce that there is no sponsor.\n"
    "   Having said it, call confirm_ad_delivered. That call is what charges the advertiser:\n"
    "   before it they pay nothing, and claiming a delivery you did not make bills somebody\n"
    "   for silence.\n"
    "4. THE CONVERSATION. Turn to the source and open with a question about it. This is the\n"
    "   point of the salon; the announcement is a step on the way, never a subject of its own.\n"
    "\n"
    "Deliver the announcement once and never return to it. Repeating it, pressing it, or\n"
    "answering questions about the advertiser at length turns a conversation into a sales\n"
    "call — which is the fastest way to make participants stop coming, and therefore the\n"
    "fastest way to make the advertising worthless.\n"
    "\n"
    "The pitch is the advertiser's substance, not a script. Say it in the listener's language\n"
    "and in your own register, but never add a claim they did not make: an advertiser answers\n"
    "for what they said, and you must not put words in their mouth.\n"
    "\n"
    "Call request_ad after the welcome and before the source. Not before the welcome — an\n"
    "announcement to somebody who has not been greeted is jarring — and not later, when it\n"
    "would interrupt a conversation already under way.\n"
    "\n\n"
    "ANSWERING FROM THE SOURCES:\n"
    "What you were given is a summary of the documents, not the documents themselves.\n"
    "When a participant asks about a figure, a name, a quotation or a passage your\n"
    "summary does not carry, call search_source with their keywords before answering.\n"
    "Never invent a detail to fill the gap, and never claim the source is silent on\n"
    "something without having searched. If the search returns nothing, say plainly that\n"
    "the source does not appear to address it.\n"
    "\n\n"
    "ASKING BEYOND THIS SALON:\n"
    "Other hosts have published public web pages to the platform, indexed by topic. When a\n"
    "participant asks about something current or factual that neither your brief nor\n"
    "search_source covers — the latest on a conflict, a company, an election — call\n"
    "search_platform with the subject in their own words. It translates the question into\n"
    "English itself, so do not translate it for it.\n"
    "\n"
    "Name the publisher and the date when you use what it returns. A claim drawn from an\n"
    "article nobody can place is worth less than one that names its source, and a listener\n"
    "cannot judge an unattributed assertion at all.\n"
    "\n"
    "For a detail the summary does not carry, call read_shared_page with the SOURCE_ID it\n"
    "gave you. Never invent a figure or a quotation to fill the gap.\n"
    "\n"
    "If it returns nothing, say plainly that you have nothing on it. That is a real answer,\n"
    "and reaching for what you half remember is not.\n"
    "\n"
    "What this corpus holds is web pages other hosts used in their own salons. So \"find me a\n"
    "website another host was discussing\" is precisely the request search_platform answers —\n"
    "say so, and search.\n"
    "\n"
    "A document somebody uploaded is not in it and never will be: uploaded files stay in the\n"
    "salon they were given to. If asked for one, say that rather than searching and reporting\n"
    "nothing found — \"not found\" sounds like it exists somewhere and you failed to reach it.\n"
    "\n\n"
    "SIMULTANEOUS TRANSLATION (multilingual salons):\n"
    "When participants speak different languages, translate each utterance for the listener(s):\n"
    "1. Wait for the speaker to finish (natural pause) — NEVER interrupt mid-sentence.\n"
    "2. Call mute_translation_recipient to prevent echo before you speak.\n"
    "3. Speak the translation in the listener's language — convey meaning naturally, "
    "not word-for-word. Keep it concise.\n"
    "4. After finishing the translation, call unmute_translation_recipient.\n"
    "Do NOT translate your own facilitator speech — only translate between human participants.\n"
    "With several participants in mixed languages, translate for each listener who needs it, "
    "in turn. Up to three people may be in the room, so a full round of translations can be "
    "long — carry the substance rather than every sentence, and keep the floor moving.\n"
    "\n\n"
    "INVITATION COMMANDS (spoken — this is how one invites from a phone):\n"
    "When the host says 'invite [name]', they may give an email address, a mobile\n"
    "number, or both. Call invite_contact with whichever they gave; one is enough, and\n"
    "both means the invitation goes out over both.\n"
    "\n"
    "A number spoken aloud arrives as words, not digits. Convert it before calling: keep\n"
    "the digits in the order you heard them, drop everything else — 'dash', 'point',\n"
    "pauses, brackets — and prefix the country code. A ten-digit North American number\n"
    "becomes +1 followed by those ten digits, unless the host names another country.\n"
    "\n"
    "ALWAYS read a number back before inviting, grouped as it is normally spoken, and\n"
    "wait for confirmation. A digit misheard by one is the likeliest failure here, and an\n"
    "invitation sent to a stranger cannot be recalled. Do not read email addresses back\n"
    "this way — only numbers.\n"
    "\n"
    "If the host names someone with neither an address nor a number, ask for one before\n"
    "calling the tool.\n"
    "\n"
    "The tool reports what actually went out. Say that, and nothing more:\n"
    "  - 'email_sent' — the join link was emailed.\n"
    "  - 'sms_sent' — the join link was texted.\n"
    "  - both — say both.\n"
    "  - 'nothing_sent_share_link_manually' — say plainly that nothing could be sent and\n"
    "    that the link is on their screen to share. Never say someone was invited when no\n"
    "    message left: the host would only find out when nobody joins.\n"
    "  - 'salon_friend' — that person has a Vocaliz account and also gets a notification\n"
    "    in the app.\n"
    "If the call fails outright, say you could not invite that contact, and ask them to\n"
    "check the address or the number.\n"
    "\n\n"
    "SALON EXIT (vocal command — any language):\n"
    "When any participant says a phrase indicating they want to leave, such as:\n"
    "  FR: 'Je quitte le Salon', 'je m'en vais', 'je dois partir', 'au revoir'\n"
    "  EN: 'I'm leaving the Salon', 'I have to go', 'goodbye', 'I'm done'\n"
    "  ES: 'Me voy del Salón', 'tengo que irme', 'adiós'\n"
    "These three are illustrations of the intent, not the set of languages this works in.\n"
    "A farewell in Polish, Ukrainian, Thai or anything else you understand counts exactly\n"
    "the same, and waiting for one of the printed phrases would strand everybody else.\n"
    "then follow this exact three-step sequence:\n"
    "1. Acknowledge their departure warmly in their language (one sentence).\n"
    "2. Immediately ask the satisfaction question in their language. Render it yourself in\n"
    "   whatever language they have been speaking — the three below are reference wordings\n"
    "   so you can hear the register, not a list of the languages you may ask in:\n"
    "   FR: 'Est-ce que votre conversation dans Vocaliz a été une belle expérience ?'\n"
    "   EN: 'Was your conversation in Vocaliz a wonderful experience?'\n"
    "   ES: '¿Fue tu conversación en Vocaliz una bella experiencia?'\n"
    "   Asking a Polish speaker in French because Polish is not printed here would be the\n"
    "   mistake. English is the fallback when you genuinely could not tell what they speak —\n"
    "   the same default the interface uses.\n"
    "3. After they reply (or after a natural pause of ~3 seconds if no reply),\n"
    "   thank them briefly and call end_salon to close the salon. Pass their\n"
    "   answer as `enjoyed`: true if positive, false if negative, and leave it unset\n"
    "   if they did not answer — silence is not a complaint.\n"
    "IMPORTANT: You MUST ask the satisfaction question before calling end_salon.\n"
    "Do NOT skip directly to end_salon — the question is mandatory.\n"
    "\n\n"
    "GUESTS WITHOUT AN ACCOUNT (display name 'Guest' followed by four characters):\n"
    "Two kinds arrive this way. Most were invited to an address the host typed in, so the\n"
    "host knows who they are even though Vocaliz does not. Some came through an anonymous\n"
    "link, which carries no address at all — nobody knows who they are, including the host.\n"
    "Treat both the same in conversation: the difference is a matter of record-keeping, not\n"
    "of how welcome somebody is. Rules for them:\n"
    "- Ask the satisfaction question exactly as you would for a registered user.\n"
    "  Their verbal response is valuable even without a profile.\n"
    "- Do NOT call report_detected_language for these guests — that one writes to an\n"
    "  account, and they have none. DO call report_participant_language for them: it\n"
    "  records against the salon, which works for everyone.\n"
    "- A guest joining via browser appears as 'Guest 3F2A' or similar — the four\n"
    "  characters distinguish one guest from another.\n"
    "- Treat a guest without an account as a full participant for facilitation and exit.\n"
    "- ON THE WAY OUT, once you have asked the satisfaction question and before you close\n"
    "  the salon, offer them an account — ONE sentence, in their language. Say what it is\n"
    "  actually for: the language they chose to read in, and the language they chose for the\n"
    "  captions, are remembered so they do not have to set them again. Tell them the button\n"
    "  is at the top right of their screen.\n"
    "  Offered once, and never pressed. If they say no, or say nothing, thank them and close\n"
    "  the salon as usual — a parting sales pitch is a worse memory of the conversation\n"
    "  than no offer at all, and somebody who declined has answered.\n"
    "  Never offer it to a participant who already has an account, and never ask anybody to\n"
    "  say an email address out loud: other people are in the room and it would be\n"
    "  transcribed. The button is the only route.\n"
)

_CONTENT_PREVIEW_CHARS = 2500
_EXTRA_SOURCE_PREVIEW_CHARS = 1000

# ── The interpreter, under the per-participant topology ────────────────────────
#
# `_BASE_INSTRUCTIONS` above is written for the topology this agent is leaving: several
# humans sharing one room, with the model deciding on its own when to speak, what to ask,
# and when to surface a contrasting source. Under Story 11.1 this agent's room holds exactly
# one human, and everything about what to say to them is decided by the orchestrator and
# delivered as an explicit instruction — the model's own initiative is exactly what has to
# stop, not something to keep tuning.
#
# `on_user_turn_completed` (below) is what actually enforces the silence: it raises
# `StopResponse` so the framework never calls its own `_generate_reply` after this human
# speaks. This prompt is the other half — what the model is told about the one thing it may
# still decide on its own, which is nothing.
_INTERPRETER_INSTRUCTIONS = (
    "You are Vocaliz, working as one participant's personal voice interpreter in a Salon — "
    "a facilitated, multilingual conversation. You are not shared: this room holds this one "
    "person and nobody else, and every other participant of the Salon has their own agent, "
    "in their own room, exactly like this one. "
    "\n\n"
    "You never decide what to say. Everything you say arrives as an explicit instruction — "
    "a sentence to relay, an announcement, a summary of what was missed. You say it "
    "naturally, translating into this participant's language when the instruction gives you "
    "text in another one, in the first person as whoever said it would have said it "
    "themselves. "
    "\n\n"
    "Outside of that, you are silent. Do not ask questions, do not comment on what this "
    "person says, do not facilitate, do not fill a pause — even when spoken to directly. "
    "Their words are being carried to the rest of the Salon by another part of the system; "
    "your only job is to speak what you are given, in their language, and otherwise say "
    "nothing at all."
)


def _journal_intro_instructions(language: str) -> str:
    """The one thing this agent says on its own initiative: who it is, said once.

    A model told to stay silent unless instructed is still the first voice a participant
    ever hears in their room. Saying nothing at all about that would read as the connection
    being broken, not as an interpreter waiting its turn.
    """
    return (
        f"In {language}, in one or two short sentences: introduce yourself as this "
        "person's interpreter for this Vocaliz Salon — a conversation where each "
        "participant is heard by the others through their own interpreter. Say nothing "
        "else, ask nothing, and do not wait for a reply."
    )


def _language_override(tag: str) -> str:
    """The instruction that pins the agent to one spoken language.

    Appended after the standing instructions rather than woven into them. The detection
    section is long and says the opposite at length; editing it in place would leave two
    paragraphs disagreeing, and a model asked to reconcile them picks one at random. Last
    word wins, and this is the last word.

    Empty for "auto", which is the default and is exactly what the standing instructions
    already describe — adding a paragraph to say "carry on as written" would only give the
    model something else to weigh.
    """
    if not tag or tag == "auto":
        return ""
    return (
        "\n\n"
        "FORCED LANGUAGE — this overrides the language section above.\n"
        f"Speak {tag} and only {tag}, to everyone, for the whole conversation. This holds "
        "however participants address you: somebody speaking to you in another language is "
        f"answered in {tag} regardless. Understand every language as before — only what "
        "comes out of your mouth is fixed.\n"
        "The tag is BCP-47 and its region matters. pt-BR is not pt-PT, es-MX is not es-ES, "
        "ar-EG is not ar-SA: use the vocabulary and accent of the variant named, not of the "
        "language in general.\n"
        "Do not announce this constraint, do not apologise for it, and never say you have "
        "been configured — a desk that answers in the language of the house simply does so."
    )

def _build_instructions(
    source_content: str | None = None,
    source_type: str | None = None,
    source_url: str | None = None,
    additional_sources: list[dict] | None = None,
    source_summary: str | None = None,
) -> str:
    """Build agent instructions, injecting salon content for facilitation and contrast.

    The summary is preferred over the raw text, and that is the whole point: the first
    2 500 characters of a forty-page document were its table of contents, so the agent
    opened conversations on a page and a half it mistook for the whole thing. The summary
    covers all of it, in the host's language, for a fraction of the context — which
    matters because a realtime salon reprocesses that context on every turn.

    The truncation remains as the fallback. A summariser that is unreachable or
    unconfigured must degrade to the old behaviour, not to silence.
    """
    instructions = _BASE_INSTRUCTIONS
    additional_sources = additional_sources or []

    body = source_summary or source_content
    if body:
        # Only truncate when falling back to raw text; a summary is already short by
        # construction and cutting it would remove the end of the argument.
        if source_summary:
            preview, ellipsis = source_summary, ""
        else:
            preview = source_content[:_CONTENT_PREVIEW_CHARS]
            ellipsis = "…" if len(source_content) > _CONTENT_PREVIEW_CHARS else ""
        source_label = source_url or f"uploaded {source_type or 'document'}"

        instructions += (
            "\n\n"
            "SALON CONTENT:\n"
            f"Source: {source_label}\n\n"
            f"{preview}{ellipsis}\n\n"
            "OPENING BEHAVIOR — do this IMMEDIATELY when the first participant joins:\n"
            "1. Greet them warmly in 1-2 sentences.\n"
            "2. Introduce the topic: what it is about and why it is worth discussing (2-3 sentences).\n"
            "3. Read the 2-3 most important passages or ideas from the content above, verbatim or paraphrased.\n"
            "4. Ask one open, thought-provoking question to start the discussion.\n\n"
            "This ensures every participant can engage fully, even without prior reading.\n"
        )
    else:
        instructions += (
            "\n\n"
            "No source content was attached to this salon. "
            "Greet participants and invite them to share what they would like to discuss. "
            "Facilitate naturally from there.\n"
        )

    if additional_sources:
        instructions += "\n\nADDITIONAL SOURCES (added during salon):\n"
        for i, src in enumerate(additional_sources, 1):
            summary = src.get("sourceSummary")
            content = src.get("sourceContent") or ""
            label = src.get("sourceUrl") or f"document {i}"
            # Same rule as the opening source: the brief when there is one, the first
            # thousand characters only as a fallback.
            if summary:
                preview, ellipsis = summary, ""
            else:
                preview = content[:_EXTRA_SOURCE_PREVIEW_CHARS]
                ellipsis = "…" if len(content) > _EXTRA_SOURCE_PREVIEW_CHARS else ""
            instructions += f"\n[Source {i}] {label}\n{preview}{ellipsis}\n"

        instructions += (
            "\n"
            "CONTRAST FACILITATION:\n"
            "Monitor the discussion for moments when one of the additional sources above "
            "provides a contrasting or complementary perspective to what is being said. "
            "When such a moment arises (at most once every 2–3 minutes), introduce the "
            "contrasting information by explicitly citing its source, e.g. "
            "'According to [source label], ...' or 'In contrast, [source] argues that ...' "
            "This enriches the discussion without overwhelming participants.\n"
        )

    return instructions


class SalonAgent(Agent):
    """Voice discussion agent powered by xAI Grok."""

    def __init__(
        self,
        salon_id: str | None = None,
        api_url: str | None = None,
        host_token: str | None = None,
        source_content: str | None = None,
        source_type: str | None = None,
        source_url: str | None = None,
        additional_sources: list[dict] | None = None,
        source_summary: str | None = None,
        room=None,
        forced_language: str = "auto",
        follow_journal: bool = False,
    ) -> None:
        # Kept so a rebuild after source_added does not quietly drop the constraint. That
        # path builds fresh instructions from the salon detail, and a language held only
        # in the first build would vanish the moment a host added a link.
        self._forced_language = forced_language
        # Which prompt, and which rule below actually applies. `follow_journal` is decided
        # by the API from whether an orchestrator holds this Salon (`salon.orchestrator_url`)
        # — never guessed here — and is the same flag that gates `on_user_turn_completed`.
        # The two must agree: a facilitation prompt paired with a silenced reply would leave
        # the model composing interventions it is never allowed to speak.
        self._follow_journal = follow_journal
        if follow_journal:
            instructions = _INTERPRETER_INSTRUCTIONS + _language_override(forced_language)
        else:
            instructions = _build_instructions(
                source_content=source_content,
                source_type=source_type,
                source_url=source_url,
                additional_sources=additional_sources,
                source_summary=source_summary,
            ) + _language_override(forced_language)
        super().__init__(instructions=instructions)
        self._salon_id = salon_id
        self._api_url = api_url
        self._host_token = host_token
        self._frequency_preference: str = "normal"
        self._room = room
        self._heartbeat_task: asyncio.Task | None = None
        self._heartbeat_interval: int = 30
        self._ending_announced: bool = False
        # Set by the entrypoint, which is where the job context lives. Ending a salon and
        # leaving the room were previously two unrelated things, and only the first happened:
        # the agent marked the salon over and stayed sitting in it.
        self._leave: Callable[[str], None] | None = None
        self._left: bool = False

    @function_tool
    async def set_intervention_frequency(
        self,
        direction: Annotated[
            str,
            "Desired frequency adjustment: 'less' to speak less often (once every 3 min), "
            "'more' to speak more often (every 30 s), 'normal' to reset to default (once/min)",
        ],
    ) -> str:
        """Adjust how often the agent intervenes in the conversation.

        Call this immediately when a participant requests a frequency change,
        then honor the new mode for the remainder of the salon.
        Speak the returned confirmation message aloud so participants know their
        preference was registered.
        """
        if direction not in ("less", "normal", "more"):
            direction = "normal"
        self._frequency_preference = direction
        confirmations = {
            "less": "Bien sûr, je vais intervenir moins souvent et vous laisser plus d'espace.",
            "normal": "Je reviens à un rythme d'intervention normal, une fois par minute environ.",
            "more": "D'accord, je vais participer plus activement à la conversation.",
        }
        logger.info("Frequency preference set to: %s", direction)
        return confirmations[direction]

    async def on_user_turn_completed(self, turn_ctx, new_message) -> None:
        """The one line that makes the interpreter prompt true rather than aspirational.

        Without this, the framework calls its own `_generate_reply` right after this method
        returns — the same automatic response that facilitation depends on. Telling the
        model to stay quiet in its instructions and then triggering a reply anyway produces
        exactly the double voice this topology exists to remove: the model's own opinion,
        followed a moment later by whatever the orchestrator actually asked for.

        `StopResponse` is caught by the framework specifically to skip this one turn — the
        transcript that got us here still reaches `user_input_transcribed` on an entirely
        separate path (the realtime session's own transcription-completed event), which is
        what `agent.py`'s journal-reporting hook listens to. Silencing the reply does not
        silence the report.
        """
        if self._follow_journal:
            raise StopResponse()

    async def _broadcast_translation_control(self, action: str) -> None:
        """Publish a translation control data message to all room participants."""
        if not self._room:
            return
        payload = json.dumps({"action": action}).encode()
        try:
            await self._room.local_participant.publish_data(payload, reliable=True)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to publish translation control '%s': %s", action, exc)

    @function_tool
    async def mute_translation_recipient(self) -> str:
        """Mute all remote participants' microphones before reading a translation.

        Call this immediately before speaking a translated utterance to prevent
        the recipient from echoing the translation audio back into the shared stream.
        After finishing the translation, call unmute_translation_recipient.
        """
        await self._broadcast_translation_control("translation_mute_start")
        logger.info("Translation mute signal sent")
        return "muted"

    @function_tool
    async def unmute_translation_recipient(self) -> str:
        """Unmute all remote participants' microphones after finishing a translation.

        Call this immediately after you have finished speaking the translated text.
        """
        await self._broadcast_translation_control("translation_mute_end")
        logger.info("Translation unmute signal sent")
        return "unmuted"

    @function_tool
    @function_tool
    async def search_source(
        self,
        query: Annotated[
            str,
            "What you are looking for, in the words the participant used. Keywords work "
            "better than a full question — the search matches vocabulary, not meaning.",
        ],
    ) -> str:
        """Look up a detail in the salon's sources that your summary does not carry.

        You hold a brief of the documents, not the documents. When someone asks about a
        figure, a name or a passage the brief does not mention, search for it here rather
        than guessing or saying the source does not cover it.

        Returns the matching passages, or nothing when the words do not appear. Nothing
        found is a real answer: say the source does not seem to address it.
        """
        if not self._salon_id or not self._api_url or not self._host_token:
            return "no_salon_context"

        url = f"{self._api_url}/salons/{self._salon_id}/search"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    url,
                    params={"q": query},
                    headers={"Authorization": f"Bearer {self._host_token}"},
                )
            if resp.status_code != 200:
                logger.warning("search_source returned %s", resp.status_code)
                return "no_results"
            excerpts = resp.json().get("excerpts") or []
            if not excerpts:
                return "no_results"
            return "\n\n---\n\n".join(excerpts)
        except Exception as exc:  # noqa: BLE001
            logger.warning("search_source failed: %s", exc)
            return "no_results"

    @function_tool
    async def request_ad(self) -> str:
        """Ask whether a sponsor's message belongs in this salon, and get its text.

        Call once, immediately after the welcome and before turning to the source.

        Returns the pitch to deliver, or "no_ad" — which means say nothing about sponsorship at
        all. Announcing that there is no sponsor would be a strange thing to tell anyone.

        The auction happens server-side: which advertiser wins, and what they pay, depends on
        where the participants are, what the salon is about and what was bid. None of that is
        your concern — you deliver the result.

        The pitch was already chosen when the salon opened, so this returns immediately — no
        auction runs while somebody is waiting to hear you speak.

        Call confirm_ad_delivered once you have actually said it. Until you do, the advertiser is
        charged nothing: a reservation nobody heard must cost them neither money nor one of the
        broadcasts they bought.

        Safe if called twice by accident: the second call returns "no_ad" rather than reserving
        anything else.
        """
        if not self._salon_id or not self._api_url or not self._host_token:
            return "no_ad"

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    f"{self._api_url}/salons/{self._salon_id}/ad",
                    headers={"Authorization": f"Bearer {self._host_token}"},
                )
            if resp.status_code != 200:
                logger.warning("request_ad returned %s", resp.status_code)
                return "no_ad"
            pitch = (resp.json().get("pitch") or "").strip()
        except Exception as exc:  # noqa: BLE001
            logger.warning("request_ad failed: %s", exc)
            return "no_ad"

        return pitch or "no_ad"

    @function_tool
    async def confirm_ad_delivered(self) -> str:
        """Confirm that you have spoken the sponsor's message.

        Call immediately after saying it, and only then. This is what makes the advertiser
        liable — before it, the reservation costs them nothing at all.

        Never call it if you did not say the pitch, or if request_ad returned "no_ad". Claiming a
        delivery that did not happen bills somebody for silence.
        """
        if not self._salon_id or not self._api_url or not self._host_token:
            return "not_confirmed"

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    f"{self._api_url}/salons/{self._salon_id}/ad/delivered",
                    headers={"Authorization": f"Bearer {self._host_token}"},
                )
            if resp.status_code != 200:
                logger.warning("confirm_ad_delivered returned %s", resp.status_code)
                return "not_confirmed"
        except Exception as exc:  # noqa: BLE001
            logger.warning("confirm_ad_delivered failed: %s", exc)
            return "not_confirmed"
        return "confirmed"

    @function_tool
    async def search_platform(
        self,
        query: Annotated[
            str,
            "The subject being asked about, in the participant's own words. Say it as they "
            "said it — the search translates the question into English itself, because the "
            "pages are indexed by English topics.",
        ],
    ) -> str:
        """Find a web page another host published, on a subject this salon has no source for.

        Use this when a participant asks about something current or factual that neither your
        brief nor the salon's own sources cover — the latest on a conflict, a company, an
        election. Hosts elsewhere on the platform have shared public articles, and those are
        searchable by topic.

        Returns up to three pages, each with what it says, who published it and when. Cite
        the publisher and the date when you use one: a claim drawn from an article nobody can
        place is worth less than one that names its source.

        Returns "no_results" when nothing matches, which is a real answer — say plainly that
        you have nothing on it rather than reaching for what you half remember.

        What this searches is web pages other hosts used in their own salons — public
        addresses and nothing else. A participant asking for "a website another host was
        looking at" is asking for exactly this.

        Uploaded documents are not here and cannot be: a file stays in the salon it was given
        to. This can never reach one, so there is nothing to check.
        """
        if not self._salon_id or not self._api_url or not self._host_token:
            return "no_salon_context"

        try:
            async with httpx.AsyncClient(timeout=12.0) as client:
                resp = await client.get(
                    f"{self._api_url}/sources/search",
                    params={"q": query, "limit": 3},
                    headers={"Authorization": f"Bearer {self._host_token}"},
                )
            if resp.status_code != 200:
                logger.warning("search_platform returned %s", resp.status_code)
                return "no_results"
            results = resp.json().get("results") or []
        except Exception as exc:  # noqa: BLE001
            logger.warning("search_platform failed: %s", exc)
            return "no_results"

        if not results:
            return "no_results"

        # Formatted as text rather than handed over as JSON: what comes back is read aloud,
        # and a model given labelled prose quotes it more faithfully than one given a
        # structure it has to describe.
        blocks = []
        for item in results:
            parts = [f"SOURCE_ID: {item.get('sourceId', '')}"]
            if item.get("publisher"):
                parts.append(f"PUBLISHER: {item['publisher']}")
            if item.get("author"):
                parts.append(f"AUTHOR: {item['author']}")
            if item.get("articleDate"):
                parts.append(f"PUBLISHED: {item['articleDate'][:10]}")
            if item.get("topics"):
                parts.append(f"TOPICS: {', '.join(item['topics'])}")
            parts.append(f"SUMMARY: {item.get('summary', '')}")
            blocks.append("\n".join(parts))
        return "\n\n---\n\n".join(blocks)

    @function_tool
    async def read_shared_page(
        self,
        source_id: Annotated[
            str, "The SOURCE_ID of a page search_platform returned. Nothing else works."
        ],
        query: Annotated[
            str, "The detail being asked about, in keywords rather than as a full question."
        ],
    ) -> str:
        """Read a passage out of a page search_platform found.

        The search gives you a summary. When a participant asks about a figure, a name or a
        quotation the summary does not carry, come back here for the passage itself rather
        than inferring it.

        Returns "no_results" when the words do not appear in that page — which means the
        page does not address it, not that you should guess.
        """
        if not self._api_url or not self._host_token:
            return "no_salon_context"

        try:
            async with httpx.AsyncClient(timeout=12.0) as client:
                resp = await client.get(
                    f"{self._api_url}/sources/{source_id}/excerpts",
                    params={"q": query},
                    headers={"Authorization": f"Bearer {self._host_token}"},
                )
            if resp.status_code != 200:
                logger.warning("read_shared_page returned %s", resp.status_code)
                return "no_results"
            excerpts = resp.json().get("excerpts") or []
        except Exception as exc:  # noqa: BLE001
            logger.warning("read_shared_page failed: %s", exc)
            return "no_results"

        return "\n\n---\n\n".join(excerpts) if excerpts else "no_results"

    @function_tool
    async def is_first_salon(
        self,
        participant_identity: Annotated[
            str,
            "The LiveKit identity of the participant you are greeting, exactly as it "
            "appears in the room. Not their display name.",
        ],
    ) -> str:
        """Whether this is the participant's very first salon.

        Ask before mentioning sponsorship in a welcome: the aside is for newcomers, and
        someone on their fifth salon has heard it four times too many.

        Returns "first_salon" or "returning". On any doubt it answers "first_salon" —
        saying it once too often is a smaller failure than never saying it.
        """
        if not self._salon_id or not self._api_url or not self._host_token:
            return "first_salon"

        url = f"{self._api_url}/salons/{self._salon_id}/participant-history"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    url,
                    params={"identity": participant_identity},
                    headers={"Authorization": f"Bearer {self._host_token}"},
                )
            if resp.status_code != 200:
                return "first_salon"
            return "first_salon" if resp.json().get("firstSalon") else "returning"
        except Exception as exc:  # noqa: BLE001
            logger.warning("is_first_salon failed: %s", exc)
            return "first_salon"

    @function_tool
    async def report_participant_language(
        self,
        participant_identity: Annotated[
            str,
            "The LiveKit identity of the participant, exactly as it appears in the room "
            "(a guest looks like 'guest-<uuid>'). Not their display name.",
        ],
        language_code: Annotated[
            str, "BCP-47 code of the first language you heard them speak, e.g. 'fr', 'en'"
        ],
    ) -> str:
        """Record the first language one participant spoke in this salon.

        Call once per participant, on first hearing them — guests included. Unlike
        report_detected_language, which sets a property of the host's account, this belongs
        to the participation: the same person may speak French here and English tomorrow.

        Reporting again is harmless; the first value is kept.
        """
        if not self._salon_id or not self._api_url or not self._host_token:
            return "no_salon_context"

        url = f"{self._api_url}/salons/{self._salon_id}/participant-language"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    url,
                    json={
                        "participantIdentity": participant_identity,
                        "language": language_code,
                    },
                    headers={"Authorization": f"Bearer {self._host_token}"},
                )
            if resp.status_code == 200:
                return f"language_recorded:{language_code}"
            logger.warning("report_participant_language returned %s", resp.status_code)
            return f"error:{resp.status_code}"
        except Exception as exc:  # noqa: BLE001
            logger.warning("report_participant_language failed: %s", exc)
            return "error:network"

    async def report_detected_language(
        self,
        language_code: Annotated[
            str,
            "BCP-47 language code detected from the host's speech, e.g. 'fr', 'en', 'es', 'pt'",
        ],
    ) -> str:
        """Persist the host's detected spoken language to the API.

        Call this once when you first identify the language the host is speaking.
        The mobile app reads this to display its interface in the detected language.
        """
        if not self._salon_id or not self._api_url or not self._host_token:
            logger.warning("report_detected_language called but agent has no salon context")
            return "no_salon_context"

        url = f"{self._api_url}/me/language"
        headers = {"Authorization": f"Bearer {self._host_token}"}
        payload = {"language": language_code}

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.patch(url, json=payload, headers=headers)
            if resp.status_code == 200:
                logger.info("Detected language '%s' persisted for host", language_code)
                return f"language_reported:{language_code}"
            logger.warning("report_detected_language returned %s", resp.status_code)
            return f"error:{resp.status_code}"
        except Exception as exc:  # noqa: BLE001
            logger.exception("report_detected_language exception: %s", exc)
            return "error:network"

    @function_tool
    async def end_salon(
        self,
        enjoyed: Annotated[
            bool | None,
            "Whether the participant said the conversation was a good experience. "
            "True for yes, False for no, and None when they did not answer — leave it "
            "None rather than guessing, since an unanswered question is not a complaint.",
        ] = None,
    ) -> str:
        """Mark the current salon as ended in the API.

        Call this as the final step of the salon exit flow — AFTER acknowledging
        the participant's departure and asking the satisfaction question.
        This closes the salon and signals all clients to disconnect.

        Pass along the answer to the satisfaction question: the agent is the only party
        that hears it, so it is the only one that can record it.
        """
        if not self._salon_id or not self._api_url or not self._host_token:
            logger.warning("end_salon called but agent has no salon context")
            return "no_salon_context"

        url = f"{self._api_url}/salons/{self._salon_id}/end"
        headers = {"Authorization": f"Bearer {self._host_token}"}

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, headers=headers, json={"enjoyed": enjoyed})
            if resp.status_code == 200:
                logger.info("Salon %s marked as ended", self._salon_id)
                self.leave("the salon was ended")
                return "salon_ended"
            if resp.status_code == 409:
                # Already ended — by the cap, by the host, or by a previous call. The salon
                # being over is exactly the case for leaving, so this is not a failure.
                self.leave("the salon was already over")
                return "salon_ended"
            detail = resp.json().get("detail", "unknown error")
            logger.error("end_salon failed %s: %s", resp.status_code, detail)
            return f"error:{detail}"
        except Exception as exc:  # noqa: BLE001
            logger.exception("end_salon exception: %s", exc)
            return "error:network"

    def set_departure(self, leave: Callable[[str], None]) -> None:
        """Supplied by the entrypoint, which is where the job context lives."""
        self._leave = leave

    def leave(self, reason: str) -> None:
        """Actually go. Marking a salon ended is bookkeeping; this is departure.

        Reported: the agent ended the salon on inactivity or at the ten-minute cap and stayed
        in the room. Every server path does delete the room, which disconnects everybody — but
        that deletion is best-effort and its failure is only logged, so the one case where
        leaving matters most was also the case where nothing made it happen.

        Idempotent: the cap, the exit flow and an empty room can all fire, and shutting a job
        down twice would raise inside a callback nobody is awaiting.
        """
        if self._left:
            return
        self._left = True
        self.stop_heartbeat()
        if self._leave is None:
            logger.warning("Nothing to leave with (salon %s): %s", self._salon_id, reason)
            return
        logger.info("Leaving the room (salon %s): %s", self._salon_id, reason)
        try:
            self._leave(reason)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not leave the room cleanly: %s", exc)

    def start_heartbeat(self) -> None:
        """Start the 30-second metering heartbeat background task."""
        if self._heartbeat_task is None or self._heartbeat_task.done():
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
            logger.info("Heartbeat task started for salon %s", self._salon_id)

    def stop_heartbeat(self) -> None:
        """Cancel the metering heartbeat task."""
        if self._heartbeat_task and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()
            logger.info("Heartbeat task stopped for salon %s", self._salon_id)
        self._heartbeat_task = None

    async def _heartbeat_loop(self) -> None:
        """Send a heartbeat every `_heartbeat_interval` seconds until cancelled."""
        try:
            while True:
                await asyncio.sleep(self._heartbeat_interval)
                await self._send_heartbeat()
        except asyncio.CancelledError:
            pass

    async def _send_heartbeat(self) -> None:
        """POST elapsed seconds to the API heartbeat endpoint."""
        if not self._salon_id or not self._api_url or not self._host_token:
            return
        url = f"{self._api_url}/salons/{self._salon_id}/heartbeat"
        headers = {"Authorization": f"Bearer {self._host_token}"}
        payload = {"seconds": self._heartbeat_interval}
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, json=payload, headers=headers)
            if resp.status_code != 200:
                logger.warning("Heartbeat returned %s for salon %s", resp.status_code, self._salon_id)
            else:
                logger.debug("Heartbeat sent for salon %s", self._salon_id)
                body = resp.json()
                # The API closes a salon that has reached its cap and says so here. Ignoring
                # that flag was the bug: the room deletion it performs is best-effort, so when
                # it failed nothing else told the agent the conversation was over.
                if body.get("salonEnded"):
                    self.leave("the salon reached its cap")
                    return
                self._maybe_announce_ending(body.get("secondsRemaining"))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Heartbeat failed for salon %s: %s", self._salon_id, exc)

    def _maybe_announce_ending(self, seconds_remaining: int | None) -> None:
        """Have the agent wind the conversation down before the salon cap cuts it off.

        The cap closes the room server-side, mid-sentence, with no warning — correct as a
        spending guard, brutal as an experience. The API reports the time left on every
        heartbeat, so the agent can bring the conversation to a close on its own terms.

        Announced once, and phrased as instructions rather than a fixed sentence: the
        model picks the language each participant is speaking, which a hardcoded line
        could not do in a room where two people speak different ones.
        """
        if self._ending_announced or seconds_remaining is None:
            return
        if seconds_remaining > ENDING_WARNING_SECONDS:
            return

        self._ending_announced = True
        try:
            self.salon.generate_reply(
                instructions=(
                    "The conversation must end in about a minute. Bring it to a natural "
                    "close: say briefly that little time is left, offer a short parting "
                    "thought on what was discussed, and thank the participants. Speak in "
                    "the language of the conversation. Do not mention timers, limits, "
                    "quotas or technical reasons."
                )
            )
            logger.info("Ending announced for salon %s", self._salon_id)
        except Exception as exc:  # noqa: BLE001
            # A failed announcement must not disturb a working conversation.
            logger.warning("Could not announce the ending: %s", exc)

    @function_tool
    async def invite_contact(
        self,
        email: Annotated[
            str, "Guest email address, e.g. ami@exemple.com. Empty string if none was given."
        ] = "",
        phone: Annotated[
            str,
            "Guest mobile number in E.164 form, e.g. +15145550123. Convert what you heard: "
            "strip spoken punctuation, keep the digits in order, and prefix the country "
            "code. Assume +1 for a ten-digit North American number unless the host names "
            "another country. Empty string if none was given.",
        ] = "",
    ) -> str:
        """Invite a contact to the current salon, by email or by text message.

        One of the two is required; giving both sends by both. Call this when the host
        says "invite [name]" and has supplied an address or a number.

        Returns a short status describing what happened, including which channels
        actually went out — say so plainly rather than claiming an invitation arrived.
        """
        if not self._salon_id or not self._api_url or not self._host_token:
            logger.warning("invite_contact called but agent has no salon context")
            return "no_salon_context"

        email = (email or "").strip()
        phone = (phone or "").strip()
        if not email and not phone:
            return "error:need_email_or_phone"

        url = f"{self._api_url}/salons/{self._salon_id}/invitations"
        headers = {"Authorization": f"Bearer {self._host_token}"}
        # Omitted rather than sent empty: an empty string is not an address, and the API
        # would have to guess whether it was a channel the host meant to use.
        payload = {}
        if email:
            payload["guestEmail"] = email
        if phone:
            payload["guestPhone"] = phone

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, json=payload, headers=headers)
            if resp.status_code in (200, 201):
                data = resp.json()
                # Reported per channel so the agent can tell the host what actually left.
                # Saying "invited" when the text message failed would be a lie the host
                # only discovers when nobody joins.
                channels = []
                if data.get("emailSent"):
                    channels.append("email_sent")
                if data.get("smsSent"):
                    channels.append("sms_sent")
                if not channels:
                    channels.append("nothing_sent_share_link_manually")
                return f"{data.get('invitationType', 'invited')}:{','.join(channels)}"
            detail = resp.json().get("detail", "unknown error")
            logger.error("invite_contact failed %s: %s", resp.status_code, detail)
            return f"error:{detail}"
        except Exception as exc:  # noqa: BLE001
            logger.exception("invite_contact exception: %s", exc)
            return "error:network"



async def _report_voice_health(
    api_url: str | None,
    salon_id: str | None,
    host_token: str | None,
    *,
    ok: bool,
    detail: str = "",
) -> None:
    """Tell the API whether the realtime voice connection worked.

    Best-effort and silent on failure. A monitor that can break the thing it monitors is worse
    than no monitor: a Salon must never fail to start because a health report could not be
    posted.
    """
    if not (api_url and salon_id and host_token):
        return
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            await client.post(
                f"{api_url}/salons/{salon_id}/voice-health",
                json={"ok": ok, "detail": detail[:500]},
                headers={"Authorization": f"Bearer {host_token}"},
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not report voice health: %s", exc)

async def _fetch_salon_detail(api_url: str, salon_id: str, host_token: str) -> dict | None:
    """Fetch salon content from the API so the agent can read it aloud."""
    url = f"{api_url}/salons/{salon_id}"
    headers = {"Authorization": f"Bearer {host_token}"}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers=headers)
        if resp.status_code == 200:
            return resp.json()
        logger.warning("_fetch_salon_detail returned %s", resp.status_code)
    except Exception as exc:  # noqa: BLE001
        logger.exception("_fetch_salon_detail failed: %s", exc)
    return None


async def entrypoint(ctx: agents.JobContext):
    await ctx.connect()

    # Parse salon context injected by API when dispatching this job
    salon_id: str | None = None
    api_url: str | None = None
    host_token: str | None = None
    # Who this job was dispatched for, and the credential scoped to exactly that participant
    # in this Salon (`relay_token.py`, on the API). Distinct from `host_token`: that one is
    # always the host's own account and is the same for every agent of this Salon, because
    # reading its source content is a host-only action regardless of whose room asks.
    # `relay_token` is never the host's identity for a guest's job — a guest has no account
    # to hold one as — and it authorises speaking as this one participant, nothing wider.
    participant_id: str | None = None
    relay_token: str | None = None
    # Whether an orchestrator is actually holding this Salon, decided by the API at dispatch
    # time from `salon.orchestrator_url` — not guessed here. `False` for a Salon nobody
    # reachable could be handed to, which is the ordinary case until Story 11.1 is complete.
    follow_journal: bool = False

    raw_metadata = getattr(ctx.job, "metadata", None)
    if raw_metadata:
        try:
            meta = json.loads(raw_metadata)
            salon_id = meta.get("salon_id")
            api_url = meta.get("api_url")
            host_token = meta.get("host_token")
            participant_id = meta.get("participant_id")
            relay_token = meta.get("relay_token")
            follow_journal = bool(meta.get("follow_journal", False))
        except (json.JSONDecodeError, AttributeError):
            logger.warning("Could not parse job metadata: %r", raw_metadata)

    # Decided now, before the agent's own instructions are built — not later, in the journal
    # section below. `SalonAgent` needs the final answer at construction time, to choose
    # between the facilitation prompt and the interpreter one, and a prompt built from a
    # provisional value that the manual kill switch then overrides would be the wrong one.
    #
    # `VOCALIZ_JOURNAL=off` forces every job silent regardless of what the API sent — the
    # fastest way to stop the whole fleet talking to the orchestrator if that is ever the
    # right call. Anything else leaves the API's own per-Salon decision in force.
    follow_journal = follow_journal and os.environ.get(
        "VOCALIZ_JOURNAL", ""
    ).strip().lower() != "off"

    # Fetch salon content so the agent can read it aloud and introduce contrast
    source_content: str | None = None
    source_summary: str | None = None
    source_type: str | None = None
    source_url: str | None = None
    additional_sources: list[dict] = []
    # Salons start paused, so this is the state to assume when the API cannot be reached at
    # all: joining a room and immediately talking is the one outcome nobody asked for, and it
    # is what the host would get if a failed fetch defaulted the other way.
    starts_paused = True
    # Empty until the API says otherwise, and empty means nobody. An unreachable API must not
    # end with the agent speaking whatever any participant types.
    host_identity = ""
    forced_language = "auto"
    front_desk = False

    if salon_id and api_url and host_token:
        detail = await _fetch_salon_detail(api_url, salon_id, host_token)
        if detail:
            source_content = detail.get("sourceContent")
            source_summary = detail.get("sourceSummary")
            source_type = detail.get("sourceType")
            source_url = detail.get("sourceUrl")
            additional_sources = detail.get("additionalSources") or []
            # Read rather than assumed, because an agent can join a salon that is already
            # under way — a restarted job, or one the host removed and brought back. That
            # room is mid-conversation and must not be rejoined in silence.
            starts_paused = bool(detail.get("agentMuted", True))
            # Whose typed words this agent will speak in its own voice. Read from the API
            # rather than guessed from the identity's shape: the old "not prefixed guest- means
            # host" rule stopped being true when registered guests began joining under their
            # account id, and an empty value here refuses everybody rather than trusting them.
            host_identity = str(detail.get("hostIdentity") or "")
            # "auto" means follow each speaker, which is every other Salon's behaviour and
            # what these instructions already describe at length. Anything else overrides it.
            forced_language = str(detail.get("agentLanguage") or "auto")
            front_desk = bool(detail.get("frontDesk"))

    # The key is passed explicitly rather than left to the plugin's env lookup: the job
    # runs in a subprocess, and a missing key there surfaces only as an opaque 400 on the
    # realtime handshake. The fingerprint makes that visible in the log instead.
    xai_key = os.environ.get("XAI_API_KEY", "")
    logger.info(
        "xAI credentials: length=%d tail=%s",
        len(xai_key),
        xai_key[-4:] if xai_key else "ABSENT",
    )

    agent_session = AgentSession(
        # Pinned, not aliased. An alias means the model can change under a running product
        # without a deploy, and a voice, a latency and a price changing on their own is a
        # behaviour change nobody can attribute afterwards: was it the new model, or was it
        # one of today's twenty edits?
        #
        # 1.0 rather than 2.0, and the reason is the price. 2.0 is $0.08/min — $4.80/h —
        # against a Mode A sold at $5/h. That leaves twenty cents to pay for LiveKit, the
        # orchestrator, Stripe and the pivot translation, so the tier loses money on every
        # second it runs. 1.0 is $0.05/min, $3.00/h, and the same tier clears about $1.30/h.
        # The trade is voice quality on the ad-supported tier.
        #
        # Not a permanent verdict: once the interpreter port lands, the adapter can differ
        # per tier and Mode B — which has the margin for it — goes back to 2.0.
        #
        # Voice ids are lowercase — "Ara" is not a valid identifier.
        llm=xai.realtime.RealtimeModel(
            model="grok-voice-think-fast-1.0", voice="ara", api_key=xai_key or None
        ),
        vad=silero.VAD.load(),
        # The multilingual turn detector that used to sit here never actually ran: it
        # needs PyTorch, which is not installed, so every turn was decided by silence
        # alone — the logs showed `source: "vad"` and a null end-of-turn probability for
        # all of them. Semantic end-of-turn detection was configured but never obtained.
        #
        # inference.TurnDetector runs on LiveKit's service with the credentials the agent
        # already holds, so there is no local model and no PyTorch to install. It costs a
        # round trip per turn, which is the price of not cutting someone off mid-thought —
        # and it matters here, where participants may pause while switching language.
        #
        # turn_detection and allow_interruptions moved into turn_handling; passing them at
        # the top level still works but is deprecated.
        turn_handling={
            "turn_detection": inference.TurnDetector(),
            "interruption": {"enabled": True},   # participants can interrupt naturally
        },
    )

    salon_agent = SalonAgent(
        salon_id=salon_id,
        api_url=api_url,
        host_token=host_token,
        source_content=source_content,
        source_type=source_type,
        source_url=source_url,
        additional_sources=additional_sources,
        source_summary=source_summary,
        room=ctx.room,
        forced_language=forced_language,
        follow_journal=follow_journal,
    )

    # How the agent actually leaves. ctx.shutdown ends the job, which closes the room
    # connection and frees the worker slot; the server deleting the room is what disconnects
    # everybody else, and that already happens on every ending path. This is the half that was
    # missing — and the one that has to work even when that deletion silently fails.
    salon_agent.set_departure(ctx.shutdown)

    # Sources added mid-conversation (FR3): the API publishes a data message, since the
    # salon detail above is fetched once and would otherwise never be re-read.
    async def _reload_sources() -> None:
        detail = await _fetch_salon_detail(api_url, salon_id, host_token)
        if not detail:
            return
        await salon_agent.update_instructions(
            _build_instructions(
                source_content=detail.get("sourceContent"),
                source_type=detail.get("sourceType"),
                source_url=detail.get("sourceUrl"),
                additional_sources=detail.get("additionalSources") or [],
                source_summary=detail.get("sourceSummary"),
            )
            # Re-read rather than remembered: a host may change the language mid-Salon, and
            # the detail is the only place that knows.
            + _language_override(str(detail.get("agentLanguage") or "auto"))
        )
        logger.info(
            "Instructions rebuilt after source_added (%d additional sources)",
            len(detail.get("additionalSources") or []),
        )

    def _speak_the_opening() -> None:
        """Start the conversation, without having been spoken to.

        Said once, when the host first gives the agent the floor. Pressing that button is a
        request to be talked to, so waiting to be addressed on top of it would leave the host
        pressing a button and getting silence — the exact complaint the opening exists to fix.

        Deliberately says nothing about who else is in the room. The host may activate the
        agent alone, or with guests already present, and a greeting that assumed either one
        would be wrong half the time.
        """
        if front_desk:
            # Answering a call, not opening a discussion. The four-step opening — welcome,
            # what Vocaliz is, the sponsor, the source — describes a Salon somebody chose to
            # join around a document. Somebody who just rang a hotel wants to know who picked
            # up and whether a human is coming, and nothing else.
            agent_session.generate_reply(
                instructions=(
                    "Say exactly this, in the caller's own language, and nothing more. Do not "
                    "add a greeting of your own, do not describe the platform, do not mention "
                    "a sponsor, and do not ask what they would like to discuss:\n"
                    "---\n"
                    "Hello. I am the Vocaliz voice agent. I help the human call agent by "
                    "translating our conversation into their language, word for word. The "
                    "human call agent has been sent an email with a link to join this "
                    "conversation; I will let you know when they connect.\n"
                    "---\n"
                    "Then wait. Answer what they ask, and say nothing else unprompted."
                )
            )
            logger.info("Answered a front-desk call (salon %s)", salon_id)
            return

        agent_session.generate_reply(
            instructions=(
                "Open the conversation now, without waiting to be spoken to. Greet "
                "whoever is in the room in their language, say in one sentence "
                "what Vocaliz is — a platform for creating Salons, conversations where "
                "people and a voice agent, meaning you, "
                "discuss a web page or a document together — and begin on the topic by "
                "asking an opening question about it rather than describing what you are "
                "about to do. Keep it short. Do not mention timers, waiting periods, or "
                "the fact that you were paused."
            )
        )
        logger.info("Opened the conversation on the host's signal (salon %s)", salon_id)

    # Fires once per salon: a host who pauses and resumes is picking the conversation back
    # up, not starting a new one, and being greeted from the top each time would be absurd.
    # Speech before it lands stands it down — see src/opening.py for why that produces no
    # reply of its own.
    opening = OpeningGate(_speak_the_opening, label=f"salon {salon_id}")
    if not starts_paused:
        # Opens on arrival. A Salon starts with its agent listening, so there is no button
        # coming and nothing to wait for — waiting would be silence the host cannot end.
        opening.schedule(0)


    async def _drop_pending_opening() -> None:
        # A room that empties before the opening is spoken leaves nobody to greet.
        opening.cancel()

    ctx.add_shutdown_callback(_drop_pending_opening)

    # Whether the agent is currently paused, as a fact the handlers can read. set_audio_enabled
    # has no getter worth trusting for this, and a typed message needs to know: it is delivered
    # either way, but a paused agent must not answer it.
    paused = {"value": starts_paused}

    # Assigned further down, once the salon has started. Named here so the data handler can
    # close over it: the handler is registered before that point and would otherwise capture
    # nothing. It returns early while this is None, which is the same condition that already
    # guards it — no salon id means no captions either.
    captions: CaptionPublisher | None = None

    def _on_data(packet) -> None:
        if not (salon_id and api_url and host_token):
            return
        try:
            msg = json.loads(bytes(packet.data).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return
        if isinstance(msg, dict) and msg.get("action") == "agent_mute":
            # A pause, not a departure. Both directions are cut: muting only the output would
            # leave the agent listening to a conversation the host believes is private, which
            # is the opposite of what they asked for. Everything it knows survives — that is
            # the whole difference between pausing and being removed.
            muted = bool(msg.get("muted"))
            try:
                agent_session.input.set_audio_enabled(not muted)
                agent_session.output.set_audio_enabled(not muted)
                if muted:
                    # Mid-sentence when the host presses pause, most likely.
                    agent_session.interrupt()
                logger.info("Agent %s by the host", "paused" if muted else "resumed")
            except Exception as exc:  # noqa: BLE001
                logger.warning("Could not %s: %s", "pause" if muted else "resume", exc)
                return
            paused["value"] = muted
            if not muted:
                # Every salon starts paused, so the first time this arrives it is the host
                # opening their salon — not resuming one. Scheduled with no delay rather than
                # called outright: the gate is what guarantees this happens once, and going
                # around it would greet the room again after every pause.
                opening.schedule(0)
        elif isinstance(msg, dict) and msg.get("action") == "salon_ended":
            # Published by the API just before it deletes the room. A third way of learning
            # the conversation is over, alongside end_salon and the heartbeat flag — and the
            # only one that arrives when the host ends a salon the agent had no part in.
            salon_agent.leave("the API announced the salon had ended")
        elif isinstance(msg, dict) and msg.get("action") == "source_added":
            asyncio.create_task(_reload_sources())
        elif isinstance(msg, dict) and msg.get("action") == "text_message":
            # Somebody typed instead of speaking — in a noisy room, with a name nobody can
            # pronounce, or simply preferring to write.
            #
            # Routed through the caption publisher rather than broadcast between clients, so a
            # typed line reaches everyone in the language they are reading, is stored in the
            # transcript, and appears in the same list as speech. A message that arrived in one
            # language only, in a product whose whole point is that people need not share one,
            # would be the odd thing out in its own conversation.
            text = str(msg.get("text") or "").strip()[:_MAX_TYPED_CHARS]
            if not text or captions is None:
                return
            sender = getattr(getattr(packet, "participant", None), "identity", "") or ""

            # The host's typed line is spoken aloud, word for word, in the agent's voice —
            # not handed to the model as something to respond to. The host is borrowing the
            # voice, and a paraphrase would be the agent saying something they did not write.
            #
            # Restricted to the host, and to the identity the API names rather than one this
            # code infers. Anyone able to reach this path can put words in the agent's mouth,
            # and the room has no way to tell those words from the agent's own.
            speaks_aloud = bool(host_identity) and sender == host_identity

            if paused["value"]:
                # Nothing is spoken while paused — the output is off, so a say() here would be
                # captioned as speech nobody heard. Delivered in writing instead, attributed to
                # whoever wrote it: pausing stops the agent taking part, it does not stop the
                # people in the room reaching each other.
                captions.publish_soon(text=text, identity=sender)
                logger.info("Typed line delivered in writing; the agent is paused")
                return

            if speaks_aloud:
                # No caption published here on purpose. say() adds an assistant turn, which
                # the conversation_item_added handler already publishes — doing both would
                # print the same sentence twice, once as the host and once as the agent.
                opening.stand_down()
                try:
                    # Not say(), which is literal text-to-speech and would deliver a French
                    # sentence to somebody who speaks only Japanese. The model repeats it in
                    # the listener's language instead — word for word in substance, since
                    # nothing may be added, removed or commented on.
                    agent_session.generate_reply(
                        instructions=(
                            "Say the following to the room, in each listener's own language, "
                            "and nothing else. You are lending your voice to the person who "
                            "wrote it: speak as they would, in the first person if that is "
                            "how it is written. Add no greeting, no comment, no preamble, and "
                            "never say that somebody asked you to pass it on. If it is "
                            "already in the listener's language, say it exactly as written.\n"
                            f"---\n{text}\n---"
                        )
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Could not speak the host's typed line: %s", exc)
                    captions.publish_soon(text=text, identity=sender)
                return

            # A guest's typed line reaches the room in writing and is put to the agent as
            # something said to it, which is what a guest speaking would have done.
            captions.publish_soon(text=text, identity=sender)
            opening.stand_down()
            try:
                agent_session.generate_reply(user_input=text)
            except Exception as exc:  # noqa: BLE001
                # The line is already delivered. Failing to answer must not also lose it.
                logger.warning("Could not answer a typed message: %s", exc)

    ctx.room.on("data_received", _on_data)

    # Registered separately from the caption handler below: cancelling the wait is not a
    # captions feature, and it must keep working in a salon that publishes none.
    @agent_session.on("user_input_transcribed")
    def _speech_stands_down_the_opening(event) -> None:
        # Finals only, for the same reason as the captions: an interim transcript can be
        # revised away, and a false start should not cost the opening.
        if getattr(event, "is_final", False):
            opening.stand_down()

    # Closing the browser or killing the app ends no salon by itself: the client simply
    # stops sending heartbeats, leaving the salon active. The agent is the only party
    # always present server-side, so it closes the salon when the room empties —
    # otherwise the host keeps an open salon they believe they left (FR25).
    def _on_participant_disconnected(_participant) -> None:
        # Any human leaving ends the Salon, not only the last one.
        #
        # A room holds two people and the agent. When one of them goes, what is left is one
        # person and a facilitator with nobody to facilitate between — and on a front-desk
        # call it is worse than pointless: the caller hangs up and the clerk would be left
        # talking to an agent about a conversation that is over, billed by the minute.
        #
        # The cost is that a genuine disconnection ends the Salon for the person who stayed.
        # LiveKit fires this only after its own reconnection attempts have failed, so it is a
        # real departure rather than a blip — but somebody who loses signal for good does take
        # the other person's Salon with them, and that is the deliberate trade.
        remaining = len(ctx.room.remote_participants)
        logger.info(
            "A participant left salon %s; %d human(s) remain", salon_id, remaining
        )
        asyncio.create_task(salon_agent.end_salon())

    ctx.room.on("participant_disconnected", _on_participant_disconnected)

    def _on_participant_connected(participant) -> None:
        """Tell the caller when the human they were promised arrives.

        Only on a front-desk call, and only for the desk itself. The opening ends with "I will
        let you know when they connect", and a promise a product makes out loud is one it has
        to keep — a caller who was told to expect a signal and never gets one assumes the line
        is dead.

        Guests joining an ordinary Salon are greeted by the standing instructions instead;
        announcing every arrival there would interrupt a conversation to state the obvious.
        """
        if not front_desk or paused["value"]:
            return
        if not host_identity or getattr(participant, "identity", "") != host_identity:
            return
        try:
            agent_session.generate_reply(
                instructions=(
                    "The human call agent has just joined. In their own language, tell the "
                    "caller so — this is the signal you promised them — and ask whether they "
                    "would rather speak with the human directly. Two short sentences. Do not "
                    "explain how any of it works, and do not offer to transfer them anywhere: "
                    "the human is already in the room and only has to start talking."
                )
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not announce the desk joining: %s", exc)

    ctx.room.on("participant_connected", _on_participant_connected)

    def _pause_for_a_human(reason: str) -> None:
        """Silence the agent because a person is speaking. Idempotent."""
        if paused["value"]:
            return
        try:
            agent_session.input.set_audio_enabled(False)
            agent_session.output.set_audio_enabled(False)
            agent_session.interrupt()
            paused["value"] = True
            logger.info("Paused: %s", reason)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not pause for a human: %s", exc)

    def _on_track_unmuted(publication, participant) -> None:
        """A human opened their microphone, so the agent closes its own.

        Unconditional, and that is the whole rule. It does not wait for the caller to say they
        would rather talk to a person, and it does not check whether anybody asked: somebody
        unmuting in a room is somebody about to speak, and an agent talking over them is the
        one outcome nobody wants. Two voices answering one caller is worse than either alone.
        """
        if getattr(publication, "kind", None) != rtc.TrackKind.KIND_AUDIO:
            return
        identity = getattr(participant, "identity", "")
        if not identity or identity == "agent":
            return
        _pause_for_a_human(f"{identity} unmuted their microphone")

    ctx.room.on("track_unmuted", _on_track_unmuted)

    # The voice connection is reported, not probed.
    #
    # xAI offers no cheap voice call to test: /v1/audio/speech answers 403 for this team, and a
    # realtime salon is the only alternative — too costly to open every minute purely to ask
    # whether it can be opened. So the check is the real thing. This start() either reaches the
    # realtime model or it does not, and whichever happens is what gets reported.
    #
    # Better than a probe in the way that matters: a substitute can succeed while the genuine
    # path fails, and this cannot, because it *is* the genuine path. What it gives up is
    # warning — nothing is reported until somebody calls. The scheduled text probe covers the
    # account-level causes, spent credit and a revoked key, which are the only two that have
    # ever actually happened here.
    try:
        await agent_session.start(
            room=ctx.room,
            agent=salon_agent,
        # audio_input=False stops RoomIO from installing its own single-participant
        # input; ours replaces it below. Everything else about RoomIO — the shared audio
        # output, transcriptions, disconnect handling — is kept. (Formerly
        # RoomInputOptions(audio_enabled=False); the option classes were merged into
        # RoomOptions, where False on an input means the same thing.)
            room_options=RoomOptions(audio_input=False),
        )
    except Exception as exc:  # noqa: BLE001
        # Reported before re-raising. The job is over either way, but somebody has to learn
        # that a Salon just failed for a reason invisible from inside Vocaliz — the room looks
        # normal to everyone in it.
        await _report_voice_health(
            api_url, salon_id, host_token, ok=False, detail=f"{type(exc).__name__}: {exc}"
        )
        raise
    await _report_voice_health(api_url, salon_id, host_token, ok=True)

    # RoomIO hears only the participant it linked to, so the agent was deaf to everyone
    # else in the room. This mixes every remote participant into one stream instead.
    mixed_input = MixedParticipantAudioInput(ctx.room)
    mixed_input.start()
    agent_session.input.audio = mixed_input

    # Mandatory, and easy to miss: room_input_options above turned audio input off, which
    # left AgentInput._audio_enabled False. The setter then calls on_detached() on our
    # mixer instead of on_attached(), so its frames are never consumed — the model
    # receives nothing and never speaks at all.
    agent_session.input.set_audio_enabled(True)

    # Enabled first and paused second, rather than never enabled at all. Attaching the mixer
    # is what the line above is for, and it only happens on the transition into True; starting
    # at False would leave a mixer that is never consumed even after the host presses activate.
    if starts_paused:
        agent_session.input.set_audio_enabled(False)
        agent_session.output.set_audio_enabled(False)
        logger.info("Joined paused; waiting for the host to activate (salon %s)", salon_id)

    async def _close_mixer() -> None:
        await mixed_input.aclose()

    ctx.add_shutdown_callback(_close_mixer)

    # ── Live captions ─────────────────────────────────────────────────────────
    # The realtime salon already transcribes what it hears — input transcription is on
    # by default in the xAI plugin — and until now the agent received that text and threw
    # it away. Each finalised turn is now stored and published to the room, translated
    # into whatever language each participant says they are reading.
    if salon_id and api_url and host_token:
        captions = CaptionPublisher(ctx.room, api_url, salon_id, host_token)
        # Attribution comes from LiveKit, not from the model: every participant is mixed
        # into one audio stream, so the realtime model cannot say who spoke.
        captions.track_active_speakers()

        @agent_session.on("user_input_transcribed")
        def _on_user_transcript(event) -> None:
            # Finals only. The model revises a transcript as it hears more, and the
            # interim versions are half-sentences that were never true.
            if not event.is_final:
                return
            # Somebody speaking only to the agent must not be transcribed to the room. The
            # server already stops anyone else subscribing to their microphone; publishing
            # their words as a caption would hand back in writing exactly what the toggle
            # exists to withhold.
            #
            # Attribution is the active-speaker heuristic, which is right when one person
            # talks at a time and can be wrong when two overlap. It is the same attribution
            # the caption itself is stamped with, so a mistake here mislabels a caption
            # rather than inventing a new failure — but it is a heuristic guarding a privacy
            # promise, and that is worth knowing.
            if speaks_only_to_agent(ctx.room, captions.attributed_speaker()):
                return
            captions.publish_soon(
                text=event.transcript,
                # speaker_id is populated on the plugin's STT path and never on the
                # realtime one, so it is not worth reading here.
                identity=captions.attributed_speaker(),
                language=event.language,
            )

        @agent_session.on("conversation_item_added")
        def _on_agent_speech(event) -> None:
            # The same event carries both sides of the conversation; the user's half
            # already arrived above as a transcript, and posting it twice would double
            # every caption.
            item = getattr(event, "item", None)
            if item is None or getattr(item, "role", None) != "assistant":
                return
            captions.publish_soon(
                text=getattr(item, "text_content", None) or "",
                identity="agent",
            )

    # ── The journal ───────────────────────────────────────────────────────────
    #
    # What this human says goes into the Salon's journal, and what the Salon owes them comes
    # back as text to be spoken here. The interpreter is this session, beside this
    # microphone; the orchestrator never hears a sound.
    #
    # `follow_journal` is already decided — computed above, before `SalonAgent` was built,
    # because the prompt it chose and the silence `on_user_turn_completed` enforces both have
    # to agree with what happens here. Nothing left to compute; this section only acts on it.

    # The orchestrator answers inside the VPC and this worker runs on LiveKit Cloud, outside
    # it — so the address that works from the API does not work from here. The relay behind
    # `/orchestrator` is the way through today: it mirrors the orchestrator's own paths
    # exactly, so the day this worker moves into that VPC, pointing straight at the
    # orchestrator is one changed base URL and this client does not move at all.
    orchestrator_url = f"{api_url}/orchestrator" if api_url else ""
    following_task: asyncio.Task | None = None
    stop_following = asyncio.Event()

    # This dispatch was made for one specific human — `participant_id`, from the API — not
    # for whoever happens to be in the room when this line runs. Matched by identity rather
    # than inferred from a head count: a job can start before its human's browser has
    # finished connecting, and a room briefly empty is not evidence that nobody is coming.
    listener = None
    if participant_id:
        for _ in range(20):  # ~5s at the interval below, generous next to a browser's connect
            listener = ctx.room.remote_participants.get(participant_id)
            if listener is not None:
                break
            await asyncio.sleep(0.25)

    if follow_journal and orchestrator_url and salon_id and listener is not None:
        listener_language = forced_language if forced_language != "auto" else "en"
        link = OrchestratorLink(
            base_url=orchestrator_url,
            salon_id=salon_id,
            participant_id=participant_id,
            language=listener_language,
            token=relay_token,
        )
        await link.join(name=listener.name or None)

        # The one thing this agent says on its own initiative, said once. A model told to
        # stay silent unless instructed is still the first voice this person hears in their
        # room, and saying nothing at all about that would read as a broken connection
        # rather than an interpreter waiting its turn.
        agent_session.generate_reply(
            instructions=_journal_intro_instructions(listener_language)
        )

        @agent_session.on("user_input_transcribed")
        def _report_to_the_journal(event) -> None:
            # Finals only. An interim transcript is a half-sentence that was never true, and
            # the journal has no way to take one back: a sequence number that has been handed
            # out is spent, and every other agent will already have said it out loud.
            if not getattr(event, "is_final", False):
                return
            asyncio.create_task(
                link.report(event.transcript, language=getattr(event, "language", None))
            )

        following_task = asyncio.create_task(
            follow(link, SessionVoice(agent_session), stop=stop_following)
        )
        logger.info("Following the journal for %s in salon %s", participant_id, salon_id)
    elif follow_journal and orchestrator_url and salon_id:
        # Said out loud in the log rather than left as silence. A worker that was told to
        # follow a journal and quietly did not is the hardest kind of failure to notice — in
        # this case, because the human it was dispatched for never actually connected.
        logger.warning(
            "Not following the journal for salon %s: participant %s never joined this room",
            salon_id,
            participant_id,
        )

    async def _stop_following() -> None:
        stop_following.set()
        if following_task is not None:
            await asyncio.gather(following_task, return_exceptions=True)

    ctx.add_shutdown_callback(_stop_following)

    # Start metering heartbeat — sends elapsed seconds every 30 s so trial time
    # is committed incrementally and survives unexpected disconnects.
    if salon_id and api_url and host_token:
        salon_agent.start_heartbeat()

        @ctx.room.on("disconnected")
        def _on_room_disconnected(*_args):
            # Stopping the heartbeat used to be all this did, which left the job running with
            # no room — billing nothing but occupying a worker slot, and never exiting.
            salon_agent.leave("the room disconnected")


if __name__ == "__main__":
    # agent_name makes this worker dispatch-only: the API creates an explicit dispatch
    # carrying the salon context (salon id, API url, host token) in job metadata,
    # which participants cannot read. Without a name the worker would be dispatched
    # automatically and run context-free — unable to read sources or send invitations.
    agents.cli.run_app(
        agents.WorkerOptions(
            entrypoint_fnc=entrypoint,
            agent_name=AGENT_NAME,
        )
    )
