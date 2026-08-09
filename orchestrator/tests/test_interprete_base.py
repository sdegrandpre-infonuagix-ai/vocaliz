"""What is true of the Base adapter and of no other.

The contract it shares with every adapter is in `test_interprete_port.py`, and satisfying
it unchanged is this story's first acceptance criterion — the orchestrator is never told
which tier anybody is on and has no way to find out.

What is here is the part that differs in kind. Speech-to-speech hands a turn to one model
and gets voice back in one movement. Base has three collaborators with a text step between
them, so it can be wrong in three places the other cannot.
"""
import pytest

from src.interprete import (
    Annonce,
    InterpreteBase,
    Participant,
    ProviderUnavailable,
    Tour,
    UnsupportedLanguage,
)
from tests.harness import (
    RecordingVoice,
    StubLanguageModel,
    StubSpeechToText,
    StubTextToSpeech,
)

MARIE = Participant(id="marie", language="fr", name="Marie")

GUTEN_TAG = Tour(participant_id="hans", text="Guten Tag", language="de")


@pytest.fixture
def stack():
    """The three collaborators, together — reading a test means reading the sequence: what
    was heard, what was rendered, what was said."""

    class Stack:
        def __init__(self):
            self.stt = StubSpeechToText()
            self.llm = StubLanguageModel()
            self.tts = StubTextToSpeech()

        heard = property(lambda self: self.stt.heard)
        rendered = property(lambda self: self.llm.calls)
        condensed = property(lambda self: self.llm.condensed)
        spoken = property(lambda self: self.tts.spoken)
        said = property(lambda self: self.tts.words)
        unsupported = property(lambda self: self.tts.unsupported)
        closes = property(lambda self: self.stt.closes)

    return Stack()


@pytest.fixture
def interprete(stack):
    return InterpreteBase(
        participant=MARIE,
        stt=stack.stt,
        llm=stack.llm,
        tts=stack.tts,
        fallback_voice=RecordingVoice(),
    )


async def test_a_participant_in_base_takes_part_like_anybody_else(interprete, stack):
    """The story in one test: Marie speaks, Marie is answered in a synthetic voice, and
    nothing about the Salon knows the difference."""
    stack.heard.append(("Où en sommes-nous ?", "fr"))

    tour = await interprete.ingest()
    await interprete.render(Tour(participant_id="hans", text="Fast fertig", language="de"))

    assert tour.text == "Où en sommes-nous ?"
    assert stack.said == ["Fast fertig [de→fr]"]


async def test_a_turn_is_rendered_and_then_spoken(interprete, stack):
    """The difference from speech-to-speech, which does both at once. Here the text step is
    real, and what comes out of it is what the voice is handed."""
    await interprete.render(GUTEN_TAG)

    assert stack.rendered == [("Guten Tag", "de", "fr")]
    assert stack.said == ["Guten Tag [de→fr]"]


async def test_a_turn_already_in_the_right_language_is_never_rendered(interprete, stack):
    """No model call for something already in the listener's language — the same rule the
    journal follows, and the reason a Salon in one language costs nothing to render."""
    await interprete.render(Tour(participant_id="luc", text="Bonjour", language="fr"))

    assert stack.rendered == []
    assert stack.said == ["Bonjour"]


async def test_it_is_spoken_in_the_language_of_its_own_human(interprete, stack):
    await interprete.render(GUTEN_TAG)

    assert [line.language for line in stack.spoken] == ["fr"]


async def test_an_announcement_is_spoken_as_it_was_composed(interprete, stack):
    """Already in this participant's language, so there is nothing to render."""
    await interprete.insert_annonce(Annonce(text="Hans a rejoint", language="fr"))

    assert stack.rendered == []
    assert stack.said == ["Hans a rejoint"]


async def test_a_condensation_goes_to_the_renderer_whole(interprete, stack):
    """Story 7.2. One call for the interval — a summary made turn by turn is not a summary
    — and no source language is claimed, because several people may have spoken in it."""
    await interprete.condense(
        [
            Tour(participant_id="hans", text="Guten Morgen", language="de"),
            Tour(participant_id="marie", text="Bonjour", language="fr"),
        ]
    )

    assert stack.condensed == [(("Guten Morgen", "Bonjour"), "fr")]
    # Condensing is its own verb, not a rendering with a long argument: what comes back is
    # shorter than what went in, which is the one thing `render` must never do.
    assert stack.rendered == []
    assert len(stack.said) == 1


async def test_condensing_nothing_asks_nothing_of_anybody(interprete, stack):
    await interprete.condense([])

    assert stack.rendered == []
    assert stack.said == []


async def test_nothing_is_transcribed_once_the_room_has_closed(interprete, stack):
    stack.heard.append(("Bonjour", "fr"))
    await interprete.aclose()

    assert await interprete.ingest() is None


async def test_closing_shuts_the_chain_once(interprete, stack):
    """One provider often serves two of the three roles, and closing the same connection
    twice is at best wasted and at worst an error from a client already told to stop."""
    await interprete.aclose()
    await interprete.aclose()

    assert stack.closes == 1


async def test_a_closed_interpreter_refuses_to_speak(interprete, stack):
    await interprete.aclose()

    with pytest.raises(ProviderUnavailable):
        await interprete.render(GUTEN_TAG)

    assert stack.said == []


# ── Three places to fail ──────────────────────────────────────────────────────


async def test_a_transcriber_that_fails_is_a_typed_error(interprete, stack):
    stack.stt.fail_with = ConnectionError("stt gone")

    with pytest.raises(ProviderUnavailable):
        await interprete.ingest()

    assert len(interprete.fallback_voice.said) == 1


async def test_a_renderer_that_fails_is_a_typed_error(interprete, stack):
    """The middle step, which speech-to-speech does not have at all — and the participant
    is owed the same spoken warning for it."""
    stack.llm.fail_with = TimeoutError("model gone")

    with pytest.raises(ProviderUnavailable):
        await interprete.render(GUTEN_TAG)

    assert stack.said == []
    assert len(interprete.fallback_voice.said) == 1


async def test_a_voice_that_fails_is_a_typed_error(interprete, stack):
    stack.tts.fail_with = ConnectionError("tts gone")

    with pytest.raises(ProviderUnavailable):
        await interprete.render(GUTEN_TAG)

    assert len(interprete.fallback_voice.said) == 1


async def test_a_renderer_failure_still_leaves_the_room_usable(interprete, stack):
    """One failed turn is one failed turn. The next one goes through, because nothing was
    torn down for it — the interpreter is not closed by a provider having a bad minute."""
    stack.llm.fail_with = TimeoutError("model gone")
    with pytest.raises(ProviderUnavailable):
        await interprete.render(GUTEN_TAG)

    stack.llm.fail_with = None
    await interprete.render(GUTEN_TAG)

    assert stack.said == ["Guten Tag [de→fr]"]


async def test_a_language_the_voice_cannot_say_is_refused_before_anything_is_rendered(
    interprete, stack
):
    """Cheaper and clearer: no point paying a model to produce text nothing can read out.
    And it is a refusal rather than a breakdown, so nobody is told their interpreter broke."""
    stack.unsupported.add("fr")

    with pytest.raises(UnsupportedLanguage):
        await interprete.render(GUTEN_TAG)

    assert stack.rendered == []
    assert stack.said == []
    assert interprete.fallback_voice.said == []
