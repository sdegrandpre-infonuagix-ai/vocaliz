"""The Salon's operational parameters, held somewhere they can be changed.

`src/config.py` already centralises the service's configuration, and this does not replace
it. The difference is what the two hold and what changing them costs. A credential belongs
in the environment: it is set once, it is secret, and changing it *should* mean a deploy.
A threshold does not. `condensation_threshold_seconds` is a number somebody will want to
move while a Salon is running badly, and an environment variable makes that a deploy — which
means in practice it never gets tuned at all.

So these live in a table, they are read at startup, and a change reaches a running instance
without a restart.

Two of the rules between them are worth more than the validation they look like. Both encode
an ordering that, if broken, does not produce an error anywhere — it produces a system that
quietly never does the thing it was built to do.
"""
import pytest

from src.settings import (
    DEFAULTS,
    InvalidSettings,
    InMemorySettingsStore,
    LiveSettings,
    SalonSettings,
)


class Clock:
    """A hand-wound clock, so the reload interval is testable without waiting for it."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


# ── The documented starting values ────────────────────────────────────────────


def test_every_parameter_has_a_documented_starting_value():
    settings = SalonSettings()

    assert settings.condensation_threshold_seconds == 120.0
    assert settings.saturation_threshold_seconds == 300.0
    assert settings.unblock_threshold_seconds == 240.0
    assert settings.max_message_characters == 500


def test_the_defaults_are_published_rather_than_hidden_in_the_constructor():
    """`DEFAULTS` is what the documentation and the tests both read, so a starting value
    cannot drift away from the number written down next to it."""
    assert DEFAULTS["condensation_threshold_seconds"] == 120.0
    assert SalonSettings(**DEFAULTS) == SalonSettings()


def test_the_pause_thresholds_are_here_too():
    """Deferred from Story 6.11, where they were module constants. Nothing about them is
    more permanent than the other numbers."""
    settings = SalonSettings()

    assert settings.significant_pause_ms == 2000
    assert settings.max_pause_ms == 5000


# ── The two orderings that matter ─────────────────────────────────────────────


def test_condensation_at_or_above_saturation_is_refused():
    """If condensation only began where the alarm already sounds, it would never once run
    before the alarm — the regulation would be dead code and nobody would see an error."""
    with pytest.raises(InvalidSettings) as raised:
        SalonSettings(condensation_threshold_seconds=300.0, saturation_threshold_seconds=300.0)

    assert "condensation_threshold_seconds" in str(raised.value)
    assert "saturation_threshold_seconds" in str(raised.value)


def test_condensation_above_saturation_is_refused_too():
    with pytest.raises(InvalidSettings):
        SalonSettings(condensation_threshold_seconds=400.0, saturation_threshold_seconds=300.0)


def test_the_refusal_says_what_the_numbers_were():
    """An error that names the fields but not the values sends somebody back to the table to
    find out what they just typed."""
    with pytest.raises(InvalidSettings) as raised:
        SalonSettings(condensation_threshold_seconds=400.0, saturation_threshold_seconds=300.0)

    assert "400" in str(raised.value)
    assert "300" in str(raised.value)


def test_the_refusal_says_why_rather_than_only_what():
    with pytest.raises(InvalidSettings) as raised:
        SalonSettings(condensation_threshold_seconds=400.0, saturation_threshold_seconds=300.0)

    assert "never" in str(raised.value).lower()


def test_unblocking_at_or_above_saturation_is_refused():
    """Blocking at 300 and unblocking at 300 is a system that unblocks into the condition
    that blocks it: it would sit there flapping between the two, several times a second."""
    with pytest.raises(InvalidSettings) as raised:
        SalonSettings(unblock_threshold_seconds=300.0, saturation_threshold_seconds=300.0)

    assert "unblock_threshold_seconds" in str(raised.value)


def test_the_oscillation_is_named_in_the_refusal():
    with pytest.raises(InvalidSettings) as raised:
        SalonSettings(unblock_threshold_seconds=350.0, saturation_threshold_seconds=300.0)

    assert "oscillat" in str(raised.value).lower()


def test_the_shipped_defaults_satisfy_their_own_rules():
    """The one test that would have caught a bad default before it reached a database."""
    settings = SalonSettings()

    assert settings.condensation_threshold_seconds < settings.saturation_threshold_seconds
    assert settings.unblock_threshold_seconds < settings.saturation_threshold_seconds


def test_unblocking_below_saturation_is_accepted():
    settings = SalonSettings(unblock_threshold_seconds=240.0, saturation_threshold_seconds=300.0)

    assert settings.unblock_threshold_seconds == 240.0


def test_a_threshold_of_zero_or_less_is_refused():
    with pytest.raises(InvalidSettings):
        SalonSettings(condensation_threshold_seconds=0.0)

    with pytest.raises(InvalidSettings):
        SalonSettings(max_message_characters=-1)


async def test_an_unknown_parameter_is_refused_rather_than_silently_ignored():
    """A typo in a settings table is otherwise a change that appears to have been saved and
    does nothing at all — the least debuggable outcome available. It comes in through the
    store rather than through Python, which is the path a real typo takes."""
    live = LiveSettings(store=InMemorySettingsStore({"condensation_threshold_secondss": 90.0}))

    with pytest.raises(InvalidSettings) as raised:
        await live.get()

    assert "condensation_threshold_secondss" in str(raised.value)


# ── Read at startup ───────────────────────────────────────────────────────────


async def test_a_fresh_installation_starts_on_the_documented_values():
    live = LiveSettings(store=InMemorySettingsStore())

    assert await live.get() == SalonSettings()


async def test_what_was_stored_is_what_is_read_at_startup():
    store = InMemorySettingsStore({"condensation_threshold_seconds": 90.0})

    live = LiveSettings(store=store)

    assert (await live.get()).condensation_threshold_seconds == 90.0


async def test_a_stored_value_does_not_disturb_the_others():
    store = InMemorySettingsStore({"condensation_threshold_seconds": 90.0})

    settings = await LiveSettings(store=store).get()

    assert settings.saturation_threshold_seconds == 300.0


async def test_a_stored_combination_that_breaks_a_rule_is_refused_at_startup():
    """Better to fail on the way up than to run for a week with regulation that cannot fire.
    The values got there somehow — the point is that nothing downstream has to wonder."""
    store = InMemorySettingsStore({"condensation_threshold_seconds": 999.0})

    with pytest.raises(InvalidSettings):
        await LiveSettings(store=store).get()


# ── Changed without a restart ─────────────────────────────────────────────────


async def test_a_saved_change_takes_effect_immediately_on_this_instance():
    live = LiveSettings(store=InMemorySettingsStore())

    await live.save(condensation_threshold_seconds=60.0)

    assert (await live.get()).condensation_threshold_seconds == 60.0


async def test_a_saved_change_is_written_down():
    store = InMemorySettingsStore()
    live = LiveSettings(store=store)

    await live.save(condensation_threshold_seconds=60.0)

    assert (await LiveSettings(store=store).get()).condensation_threshold_seconds == 60.0


async def test_a_change_saved_elsewhere_reaches_this_instance_without_a_restart():
    """The acceptance criterion, and the reason `get()` is not simply an attribute. Several
    instances serve one Salon; a change made against the database by any route has to arrive
    at all of them, and the only thing they share is the table."""
    clock = Clock()
    store = InMemorySettingsStore()
    live = LiveSettings(store=store, reload_seconds=30.0, now=clock)
    await live.get()

    await store.save({"condensation_threshold_seconds": 45.0})
    clock.advance(31)

    assert (await live.get()).condensation_threshold_seconds == 45.0


async def test_it_does_not_read_the_table_on_every_single_access():
    """This is consulted on every message of every Salon. A round trip per access would
    make the settings table the busiest thing in the system."""
    clock = Clock()
    store = InMemorySettingsStore()
    live = LiveSettings(store=store, reload_seconds=30.0, now=clock)

    for _ in range(50):
        await live.get()

    assert store.reads == 1


async def test_a_change_is_not_seen_before_the_interval_is_up():
    clock = Clock()
    store = InMemorySettingsStore()
    live = LiveSettings(store=store, reload_seconds=30.0, now=clock)
    await live.get()

    await store.save({"condensation_threshold_seconds": 45.0})
    clock.advance(29)

    assert (await live.get()).condensation_threshold_seconds == 120.0


async def test_a_refusal_leaves_the_running_values_alone():
    """A bad edit must not take a healthy instance down with it. It is refused, and what was
    already running carries on running."""
    live = LiveSettings(store=InMemorySettingsStore())
    before = await live.get()

    with pytest.raises(InvalidSettings):
        await live.save(condensation_threshold_seconds=999.0)

    assert await live.get() == before


async def test_a_refused_change_is_never_written_down():
    """Otherwise the next instance to start reads it and fails on the way up — a bad edit
    that was correctly refused here would still have taken the fleet down on the next
    deploy."""
    store = InMemorySettingsStore()
    live = LiveSettings(store=store)

    with pytest.raises(InvalidSettings):
        await live.save(condensation_threshold_seconds=999.0)

    assert store.saved == {}


async def test_a_change_is_validated_against_the_values_it_lands_beside():
    """Saving one field means validating the whole object. 250 is a perfectly good
    condensation threshold on its own, and wrong next to a saturation threshold of 200."""
    live = LiveSettings(store=InMemorySettingsStore({"saturation_threshold_seconds": 200.0}))

    with pytest.raises(InvalidSettings):
        await live.save(condensation_threshold_seconds=250.0)


async def test_a_whole_number_survives_the_round_trip_as_a_whole_number():
    """The table has one numeric column for every parameter, so an integer comes back as a
    float. `max_message_characters` is a length used to slice text — the dataclass is what
    decides it is an int, and it has to actually do it rather than merely say so."""
    live = LiveSettings(store=InMemorySettingsStore({"max_message_characters": 400.0}))

    value = (await live.get()).max_message_characters

    assert value == 400
    assert isinstance(value, int)


async def test_a_duration_is_left_alone_as_a_float():
    settings = await LiveSettings(
        store=InMemorySettingsStore({"condensation_threshold_seconds": 90.5})
    ).get()

    assert settings.condensation_threshold_seconds == 90.5


async def test_two_fields_that_are_only_valid_together_can_be_saved_together():
    """Raising saturation past the others has to be possible in one move, or the ordering
    rules would make some perfectly good configurations unreachable."""
    live = LiveSettings(store=InMemorySettingsStore())

    await live.save(saturation_threshold_seconds=600.0, unblock_threshold_seconds=500.0)

    settings = await live.get()
    assert (settings.saturation_threshold_seconds, settings.unblock_threshold_seconds) == (
        600.0,
        500.0,
    )
