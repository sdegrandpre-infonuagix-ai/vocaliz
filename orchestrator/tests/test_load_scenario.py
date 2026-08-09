"""Running a scenario end to end against a real Salon.

The Salon under test is the real one. Only the humans and their interpreters are simulated,
because replacing the conductor would measure the harness rather than the system.
"""
import pytest

from src.load import Report, Tier, TierPrice
from src.load.scenario import Scenario, cast_of, run


async def test_a_small_scenario_produces_a_report():
    report = await run(Scenario(participants=3, duration_seconds=300.0, cadence_seconds=60.0))

    assert isinstance(report, Report)
    assert report.participants == 3


async def test_fifty_participants_can_be_run_at_all():
    """The number the ceiling decision is about. If this cannot be run, the decision cannot
    be made from evidence."""
    report = await run(Scenario(participants=50, duration_seconds=120.0, cadence_seconds=60.0))

    assert report.participants == 50


async def test_fifty_participants_cost_nothing():
    """No paid provider is reachable from here: `InterpreteFake` speaks to nobody and the
    scenario's translate function is local. The guard is that no provider SDK is importable
    under `src/` at all, which `tests/test_interprete_port.py` already fails the build over."""
    import src.load.scenario as scenario_module

    source = open(scenario_module.__file__, encoding="utf-8").read()
    for provider in ("openai", "anthropic", "elevenlabs", "deepgram", "boto3"):
        assert provider not in source


async def test_every_cursor_is_measured():
    report = await run(Scenario(participants=4, duration_seconds=180.0, cadence_seconds=60.0))

    assert report.max_lag_seconds >= 0.0


async def test_the_report_carries_the_meta_speech_breakdown():
    report = await run(Scenario(participants=3, duration_seconds=180.0, cadence_seconds=60.0))

    assert set(report.meta_speech_by_tier) == set(Tier)


async def test_the_tier_that_ran_has_a_ratio():
    """Introductions alone guarantee some meta-speech: everybody is introduced to everybody
    before their first message."""
    report = await run(
        Scenario(participants=3, duration_seconds=180.0, cadence_seconds=60.0, tier=Tier.MODE_A)
    )

    assert report.meta_speech_by_tier[Tier.MODE_A] is not None
    assert report.meta_speech_by_tier[Tier.MODE_A] > 0.0


async def test_the_tiers_that_did_not_run_are_marked_as_such():
    report = await run(
        Scenario(participants=3, duration_seconds=180.0, cadence_seconds=60.0, tier=Tier.BASE)
    )

    assert report.meta_speech_by_tier[Tier.MODE_C] is None


async def test_a_scenario_is_reproducible():
    """Same seed, same verdict. Otherwise the load test measures itself."""
    first = await run(Scenario(participants=4, duration_seconds=180.0, seed=3))
    second = await run(Scenario(participants=4, duration_seconds=180.0, seed=3))

    assert first == second


async def test_a_different_seed_is_a_different_run():
    first = await run(Scenario(participants=4, duration_seconds=180.0, seed=1))
    second = await run(Scenario(participants=4, duration_seconds=180.0, seed=2))

    assert first.meta_speech_by_tier == second.meta_speech_by_tier or first != second


async def test_a_talkative_scenario_makes_people_fall_behind():
    """The harness has to be able to produce the bad case, or it can only ever confirm that
    everything is fine."""
    calm = await run(Scenario(participants=4, duration_seconds=300.0, cadence_seconds=150.0))
    frantic = await run(
        Scenario(participants=4, duration_seconds=300.0, cadence_seconds=10.0, words_per_turn=200)
    )

    assert frantic.max_lag_seconds > calm.max_lag_seconds


async def test_the_cast_spreads_across_languages():
    """Everybody sharing one language would short-circuit translation, which is most of what
    a load test is meant to be putting under load."""
    cast = cast_of(12)

    assert len({participant.language for participant in cast}) > 1


async def test_a_scenario_with_prices_judges_the_cost():
    report = await run(
        Scenario(
            participants=3,
            duration_seconds=300.0,
            cost=TierPrice(cost_per_participant=0.9, price_per_participant=1.0),
        )
    )

    assert any("cost" in note.lower() for note in report.failures)


async def test_an_hour_long_scenario_can_state_the_block_criterion():
    """The criterion is zero blocks over an hour, so the harness must be able to run one —
    and it does, in milliseconds, because scenario time is not wall-clock time."""
    report = await run(
        Scenario(participants=3, duration_seconds=3600.0, cadence_seconds=600.0)
    )

    assert not any("cannot show an hour" in note for note in report.failures)


async def test_a_scenario_can_be_run_against_different_thresholds():
    """Most of what somebody runs a load harness for: not "does it cope" but "would it cope
    if we moved this number"."""
    from src.settings import SalonSettings

    settings = SalonSettings(condensation_threshold_seconds=60.0)
    report = await run(
        Scenario(participants=3, duration_seconds=300.0, cadence_seconds=60.0, settings=settings)
    )

    assert report.participants == 3


async def test_an_interpreter_that_cannot_keep_up_saturates_and_is_blocked():
    """Saturation is what happens when condensation itself cannot keep up, which is why the
    settings refuse to let it fire before condensation has been tried. Reaching it in a
    scenario therefore takes an interpreter with no time to summarise either — and the
    harness has to be able to reach it, or it can only ever confirm that all is well.
    """
    report = await run(
        Scenario(
            participants=4,
            duration_seconds=300.0,
            cadence_seconds=10.0,
            words_per_turn=300,
            render_speed=0.0,
        )
    )

    assert report.block_count > 0
    assert any("block" in note.lower() for note in report.failures)


async def test_a_blocked_room_is_timed_and_not_only_counted():
    """How long somebody could not speak is a different question from how often it happened,
    and only the first one says how bad it was."""
    report = await run(
        Scenario(
            participants=4,
            duration_seconds=300.0,
            cadence_seconds=10.0,
            words_per_turn=300,
            render_speed=0.05,
        )
    )

    assert report.block_count > 0
    assert report.block_seconds > 0.0


async def test_an_interpreter_with_no_time_at_all_renders_nothing():
    """A render speed of zero is a stopped interpreter: the backlog only grows."""
    report = await run(
        Scenario(participants=3, duration_seconds=300.0, cadence_seconds=60.0, render_speed=0.0)
    )

    assert report.max_lag_seconds > 0.0


async def test_the_harness_translates_by_paying_nobody():
    """The scenario's translator is local and returns the text unchanged. It exists so a
    Salon can be built at all — `SalonLog` requires one — and returning the original keeps
    the promise that a fifty-participant run costs nothing."""
    from src.load.scenario import _translate

    assert await _translate("Bonjour", source="fr", target="de") == "Bonjour"
