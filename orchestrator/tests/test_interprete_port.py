"""The Interpreter port, and the contract every adapter owes it.

The tests below run against every implementation there is. That is the whole purpose of a
port: `InterpreteFake` and `InterpreteS2S` answer the same questions the same way, and
Story 6.7 will add `InterpreteBase` to the list without a line changing in the
orchestrator.
"""
import inspect
from pathlib import Path

import pytest

from src.interprete import (
    Annonce,
    Interprete,
    InterpreteError,
    Participant,
    ProviderUnavailable,
    Tour,
    UnsupportedLanguage,
)
from tests.harness import FakeHarness, S2SHarness

MARIE = Participant(id="marie", language="fr", name="Marie")

TOURS = [
    Tour(participant_id="hans", text="Guten Morgen", language="de", sequence=1),
    Tour(participant_id="hans", text="Wie geht es dir?", language="de", sequence=2),
]

# Every adapter of the port. Adding one here is how Story 6.7 proves `InterpreteBase`
# satisfies exactly the same contract as the speech-to-speech adapter.
ADAPTERS = pytest.mark.parametrize("harness_class", [FakeHarness, S2SHarness], ids=["fake", "s2s"])


@pytest.fixture
def marie(harness_class):
    return harness_class(MARIE)


# ── The interface itself ──────────────────────────────────────────────────────


def test_the_port_declares_exactly_the_four_methods_of_the_story():
    assert set(Interprete.__abstractmethods__) == {"ingest", "render", "insert_annonce", "condense"}


def test_every_method_of_the_port_is_awaitable():
    """An interpreter waits on a human and on a model; nothing it does can be synchronous."""
    for name in Interprete.__abstractmethods__:
        assert inspect.iscoroutinefunction(getattr(Interprete, name))


def test_the_orchestrator_never_reaches_for_a_provider_sdk():
    """The reason the port exists at all. One `import livekit` in the orchestrator would
    make the whole indirection decorative, and it is exactly the sort of import that
    arrives in a hurry — so it fails the build rather than a code review."""
    vendors = (
        "livekit",
        "xai",
        "openai",
        "anthropic",
        "deepgram",
        "elevenlabs",
        "cartesia",
    )
    source = Path(__file__).resolve().parents[1] / "src"

    offenders = [
        (path.name, stripped)
        for path in source.rglob("*.py")
        for stripped in (line.strip() for line in path.read_text(encoding="utf-8").splitlines())
        for vendor in vendors
        # Stripped first: an import deferred inside a function is indented, and that is
        # exactly the shape a provider SDK sneaks in under.
        if stripped.startswith((f"import {vendor}", f"from {vendor}"))
    ]

    assert offenders == []


def test_the_typed_errors_share_one_root():
    """An orchestrator that wants to catch "the interpreter failed" must have one name for
    it, whichever adapter and whichever provider produced it."""
    assert issubclass(ProviderUnavailable, InterpreteError)
    assert issubclass(UnsupportedLanguage, InterpreteError)


# ── The contract, owed by every adapter ───────────────────────────────────────


@ADAPTERS
async def test_an_interpreter_knows_whose_it_is(marie):
    assert marie.interprete.participant == MARIE


@ADAPTERS
async def test_ingest_returns_what_its_human_said(marie):
    marie.hears("Bonjour tout le monde", language="fr")

    tour = await marie.interprete.ingest()

    assert tour.participant_id == "marie"
    assert tour.text == "Bonjour tout le monde"
    assert tour.language == "fr"


@ADAPTERS
async def test_ingest_reports_the_language_actually_spoken(marie):
    """The speaker makes the original. A participant switching to English mid-Salon is
    recorded in English, whatever language their interpreter usually hears."""
    marie.hears("Actually, let me say that again", language="en")

    assert (await marie.interprete.ingest()).language == "en"


@ADAPTERS
async def test_ingest_leaves_the_sequence_to_the_journal(marie):
    """Arrival order is decided where messages arrive — by the orchestrator, in 6.3. An
    interpreter numbering its own turns would be numbering them against its own room."""
    marie.hears("Bonjour", language="fr")

    assert (await marie.interprete.ingest()).sequence is None


@ADAPTERS
async def test_ingest_returns_nothing_once_the_human_is_gone(marie):
    """None, not an exception: a participant leaving is the ordinary end of a Salon."""
    marie.close_room()

    assert await marie.interprete.ingest() is None


@ADAPTERS
async def test_render_speaks_a_turn_to_its_human(marie):
    await marie.interprete.render(TOURS[0])

    assert marie.spoken == ["Guten Morgen"]
    assert marie.kinds == ["tour"]


@ADAPTERS
async def test_render_asks_for_the_language_of_its_own_human(marie):
    await marie.interprete.render(TOURS[0])

    assert marie.spoken_languages == ["fr"]
    assert marie.verbatim == [False]


@ADAPTERS
async def test_a_turn_already_in_the_right_language_is_rendered_as_spoken(marie):
    """No round trip through a model for something already in the right language — the cost
    of a Salon follows the number of languages in it, never the number of turns."""
    await marie.interprete.render(
        Tour(participant_id="luc", text="Bonjour", language="fr", sequence=3)
    )

    assert marie.spoken == ["Bonjour"]
    assert marie.verbatim == [True]


@ADAPTERS
async def test_insert_annonce_is_spoken_but_never_becomes_a_turn(marie):
    """An announcement is said to one human. It is not something anybody said, so it never
    enters the journal and is never rendered to anyone else."""
    await marie.interprete.insert_annonce(Annonce(text="Hans parle allemand", language="fr"))

    assert marie.spoken == ["Hans parle allemand"]
    assert marie.kinds == ["annonce"]
    assert await marie.interprete.ingest() is None


@ADAPTERS
async def test_condense_says_the_substance_rather_than_every_turn(marie):
    await marie.interprete.condense(TOURS)

    assert len(marie.spoken) == 1
    assert marie.spoken[0] not in [tour.text for tour in TOURS]
    assert marie.kinds == ["condense"]


@ADAPTERS
async def test_condense_speaks_in_the_language_of_its_own_human(marie):
    await marie.interprete.condense(TOURS)

    assert marie.spoken_languages == ["fr"]


@ADAPTERS
async def test_condensing_nothing_says_nothing(marie):
    """A Salon whose reading position is already at the head has nothing to summarise, and
    an interpreter announcing a summary of nothing is worse than silence."""
    await marie.interprete.condense([])

    assert marie.spoken == []


@ADAPTERS
async def test_a_language_the_adapter_cannot_speak_is_a_typed_refusal(marie):
    """Story 6.7: the offered languages are the intersection of the adapters, never their
    union, and the refusal has to be legible enough for the orchestrator to act on."""
    marie.refuse_language("fr")

    with pytest.raises(UnsupportedLanguage) as excinfo:
        await marie.interprete.render(TOURS[0])

    assert excinfo.value.participant_id == "marie"
    assert marie.spoken == []


@ADAPTERS
async def test_a_provider_failure_is_a_typed_error(marie):
    """NFR3. The orchestrator gets a name for what went wrong, not somebody's SDK
    exception — which is the difference between handling it and logging it."""
    marie.fail_the_provider(TimeoutError("the model stopped answering"))

    with pytest.raises(ProviderUnavailable) as excinfo:
        await marie.interprete.render(TOURS[0])

    assert excinfo.value.participant_id == "marie"
    assert isinstance(excinfo.value.__cause__, TimeoutError)


@ADAPTERS
async def test_a_provider_failure_during_ingest_is_typed_too(marie):
    marie.hears("Bonjour", language="fr")
    marie.fail_the_provider(ConnectionError("socket closed"))

    with pytest.raises(ProviderUnavailable):
        await marie.interprete.ingest()


@ADAPTERS
async def test_a_provider_failure_is_told_to_the_participant_out_loud(marie):
    """NFR3, the half that faces the human. Somebody wearing headphones in a Salon has no
    screen to check and no other voice to ask: silence is indistinguishable from everyone
    else having stopped talking."""
    marie.fail_the_provider(TimeoutError("the model stopped answering"))

    with pytest.raises(ProviderUnavailable):
        await marie.interprete.render(TOURS[0])

    assert len(marie.voice.said) == 1
    _, language = marie.voice.said[0]
    assert language == "fr"


@ADAPTERS
async def test_the_spoken_notice_does_not_go_through_the_failed_provider(marie):
    """Telling somebody their interpreter is down, using the interpreter that is down."""
    marie.fail_the_provider(TimeoutError("the model stopped answering"))

    with pytest.raises(ProviderUnavailable):
        await marie.interprete.render(TOURS[0])

    assert marie.spoken == []


@ADAPTERS
async def test_a_notice_that_cannot_be_spoken_never_hides_the_real_error(marie):
    """Two things broken is still the first thing's fault. The orchestrator has to see the
    provider failure even when the fallback voice is unavailable too."""
    marie.fail_the_provider(TimeoutError("the model stopped answering"))
    marie.voice.fail_with = RuntimeError("no audio device")

    with pytest.raises(ProviderUnavailable):
        await marie.interprete.render(TOURS[0])


@ADAPTERS
async def test_an_unsupported_language_is_not_announced_as_a_breakdown(marie):
    """A language the adapter never spoke is a decision, not a failure — Story 6.7 settles
    what to do about it, and it is not "tell this participant their interpreter broke"."""
    marie.refuse_language("fr")

    with pytest.raises(UnsupportedLanguage):
        await marie.interprete.render(TOURS[0])

    assert marie.voice.said == []


@ADAPTERS
async def test_closing_an_interpreter_twice_is_harmless(marie):
    await marie.interprete.aclose()
    await marie.interprete.aclose()
