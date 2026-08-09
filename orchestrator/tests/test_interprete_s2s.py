"""What is true of the speech-to-speech adapter and of no other.

The contract it shares with every adapter is in `test_interprete_port.py`. What is here is
the thing that makes this one different: the model hears the human and answers in voice,
with no text step inside the room.
"""
import pytest

from src.interprete import InterpreteS2S, Participant, ProviderUnavailable, Tour
from tests.harness import RecordingVoice, StubRealtimeSession

MARIE = Participant(id="marie", language="fr", name="Marie")


@pytest.fixture
def session():
    return StubRealtimeSession()


@pytest.fixture
def interprete(session):
    return InterpreteS2S(participant=MARIE, session=session, fallback_voice=RecordingVoice())


async def test_a_human_alone_in_a_room_converses_with_their_interpreter(interprete, session):
    """The story in one test: Marie speaks, Marie is answered, and the only thing in the
    room with her is her own interpreter."""
    session.heard.append(("Où en sommes-nous ?", "fr"))

    tour = await interprete.ingest()
    await interprete.render(Tour(participant_id="hans", text="Fast fertig", language="de"))

    assert tour.text == "Où en sommes-nous ?"
    assert [line.text for line in session.spoken] == ["Fast fertig"]
    assert [line.language for line in session.spoken] == ["fr"]


async def test_nothing_inside_the_room_passes_through_text(interprete, session):
    """Audio in, audio out. The adapter holds one realtime session and no transcription or
    synthesis component of its own — the text it exchanges with the orchestrator is what
    leaves the room, never a step inside it."""
    assert not hasattr(interprete, "stt")
    assert not hasattr(interprete, "tts")
    assert interprete.session is session


async def test_the_adapter_speaks_only_through_its_session(interprete, session):
    await interprete.render(Tour(participant_id="hans", text="Guten Tag", language="de"))

    assert len(session.spoken) == 1


async def test_a_turn_in_another_language_is_handed_over_for_the_model_to_render(
    interprete, session
):
    """`verbatim=False` is the instruction that carries the translation. It is the model's
    work, in voice, inside its own session — there is no separate translation call."""
    await interprete.render(Tour(participant_id="hans", text="Guten Tag", language="de"))

    (line,) = session.spoken
    assert line.verbatim is False
    assert line.language == "fr"
    assert line.text == "Guten Tag"


async def test_closing_the_interpreter_closes_the_session_once(interprete, session):
    await interprete.aclose()
    await interprete.aclose()

    assert session.closes == 1


async def test_a_closed_interpreter_stops_listening(interprete, session):
    session.heard.append(("Bonjour", "fr"))
    await interprete.aclose()

    assert await interprete.ingest() is None


async def test_a_closed_interpreter_refuses_to_speak_rather_than_reopening(interprete, session):
    """A turn arriving for a participant who has left is a typed error, not a session
    quietly brought back up for somebody who is no longer in the room."""
    await interprete.aclose()

    with pytest.raises(ProviderUnavailable):
        await interprete.render(Tour(participant_id="hans", text="Hallo", language="de"))

    assert session.spoken == []


async def test_a_failure_while_announcing_is_typed_and_spoken(interprete, session):
    """An announcement goes through the same model as everything else, so it fails the same
    way — and the participant is owed the same warning."""
    from src.interprete import Annonce

    session.fail_with = ConnectionError("session dropped")

    with pytest.raises(ProviderUnavailable):
        await interprete.insert_annonce(Annonce(text="Hans a rejoint", language="fr"))

    assert len(interprete.fallback_voice.said) == 1


async def test_a_failure_while_condensing_is_typed_too(interprete, session):
    session.fail_with = ConnectionError("session dropped")

    with pytest.raises(ProviderUnavailable):
        await interprete.condense([Tour(participant_id="hans", text="Hallo", language="de")])


async def test_an_interpreter_without_a_fallback_voice_still_raises(session):
    """The voice is optional — a Salon in which nothing can speak to the participant is
    worse served by a crash inside the error path than by a plain typed error."""
    interprete = InterpreteS2S(participant=MARIE, session=session)
    session.fail_with = ConnectionError("session dropped")

    with pytest.raises(ProviderUnavailable):
        await interprete.render(Tour(participant_id="hans", text="Hallo", language="de"))
