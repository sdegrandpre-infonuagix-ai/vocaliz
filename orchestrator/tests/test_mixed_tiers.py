"""One Salon, two tiers, and no way to tell from the outside.

The story's second acceptance criterion: a participant on Base and a participant on
speech-to-speech converse normally, and the Base experience is neither blocked nor
degraded. Degraded here has a precise meaning — later, slower or missing something. What it
does not mean is "synthetic rather than natural voice", which is the whole of what the
cheaper tier buys and is not a defect.

The orchestrator is never told which tier anybody is on. That is not an omission to be
fixed later; it is the acceptance criterion, and `Salon` has no parameter that could carry
the answer.
"""
import pytest

from src.interprete import InterpreteBase, InterpreteS2S, Participant
from src.journal import InMemoryJournalStore, SalonLog
from src.salon import InMemoryRoomProvisioner, Salon
from tests.harness import (
    RecordingVoice,
    StubLanguageModel,
    StubRealtimeSession,
    StubSpeechToText,
    StubTextToSpeech,
)

MARIE = Participant(id="marie", language="fr", name="Marie")  # Base
HANS = Participant(id="hans", language="de", name="Hans")  # speech-to-speech


async def translate(text, *, source, target):
    return f"{text} [{target}]"


@pytest.fixture
def base_parts():
    return StubSpeechToText(), StubLanguageModel(), StubTextToSpeech()


@pytest.fixture
def s2s_session():
    return StubRealtimeSession()


@pytest.fixture
async def salon(base_parts, s2s_session):
    stt, llm, tts = base_parts
    log = SalonLog(salon_id="salon-1", store=InMemoryJournalStore(), translate=translate)
    salon = Salon(log=log, rooms=InMemoryRoomProvisioner())

    await salon.join(
        MARIE,
        InterpreteBase(
            participant=MARIE, stt=stt, llm=llm, tts=tts, fallback_voice=RecordingVoice()
        ),
    )
    await salon.join(
        HANS,
        InterpreteS2S(participant=HANS, session=s2s_session, fallback_voice=RecordingVoice()),
    )
    return salon


async def test_both_tiers_are_heard_by_the_journal(salon, base_parts, s2s_session):
    stt, _, _ = base_parts
    stt.heard.append(("Bonjour tout le monde", "fr"))
    s2s_session.heard.append(("Guten Tag zusammen", "de"))

    await salon.collect()

    assert [(e.text, e.language) for e in salon.log.entries] == [
        ("Guten Tag zusammen", "de"),
        ("Bonjour tout le monde", "fr"),
    ]


async def test_each_tier_speaks_to_its_human_in_that_human_s_language(
    salon, base_parts, s2s_session
):
    _, _, tts = base_parts
    await salon.ingest(HANS.id, "Guten Tag", language="de")
    await salon.ingest(MARIE.id, "Bonjour", language="fr")

    await salon.deliver_all()

    # Marie is on Base: her voice is synthetic and the text reached it already in French.
    assert tts.words == ["Guten Tag [de→fr]"]
    assert [line.language for line in tts.spoken] == ["fr"]
    # Hans is on speech-to-speech: the original goes to his model, which renders and speaks
    # in one movement.
    assert [line.text for line in s2s_session.spoken] == ["Bonjour"]
    assert [line.language for line in s2s_session.spoken] == ["de"]


async def test_the_base_participant_is_never_behind_the_other(salon, base_parts):
    """Not blocked and not degraded: the same messages, at the same point in the journal."""
    _, _, tts = base_parts
    for text in ("eins", "zwei", "drei"):
        await salon.ingest(HANS.id, text, language="de")

    await salon.deliver_all()

    assert len(tts.words) == 3
    assert salon.pending_for(MARIE.id) == ()
    assert salon.log.lag_seconds(salon.log.cursor(MARIE.id)) == 0.0


async def test_the_orchestrator_is_not_told_which_tier_anybody_is_on(salon):
    """The acceptance criterion as an absence. Nothing in a `Participant` or a `Salon` names
    a tier, so nothing downstream can branch on one."""
    assert not hasattr(MARIE, "tier")
    assert [name for name in dir(salon) if "tier" in name.lower()] == []


async def test_a_failing_base_stack_leaves_the_other_tier_alone(salon, base_parts, s2s_session):
    """One tier's provider having a bad minute is one participant's problem — the same
    guarantee Story 6.4 makes for a room, restated across tiers."""
    _, llm, _ = base_parts
    llm.fail_with = TimeoutError("model gone")
    await salon.ingest(HANS.id, "Guten Tag", language="de")

    await salon.deliver_all()

    assert [line.text for line in s2s_session.spoken] == []
    assert len(salon.pending_for(MARIE.id)) == 1


async def test_a_base_participant_catches_up_once_their_stack_recovers(salon, base_parts):
    _, llm, tts = base_parts
    llm.fail_with = TimeoutError("model gone")
    await salon.ingest(HANS.id, "Guten Tag", language="de")
    await salon.deliver(MARIE.id)

    llm.fail_with = None
    await salon.deliver(MARIE.id)

    assert tts.words == ["Guten Tag [de→fr]"]
    assert salon.pending_for(MARIE.id) == ()
