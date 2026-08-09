"""`SqlSettingsStore` against a real database engine.

SQLite, so the suite still needs no server; Postgres is what it runs on. The same trade the
journal's store makes, and it has already earned its keep once — the timezone bug in Story
6.3 was only visible because these tests hit an actual database rather than a fake.
"""
import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from src.settings import (
    InvalidSettings,
    LiveSettings,
    SalonSettings,
    SqlSettingsStore,
)


@pytest.fixture
async def store():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    store = SqlSettingsStore(engine)
    await store.create_all()
    yield store
    await engine.dispose()


async def test_a_new_installation_has_an_empty_table():
    """No seeding. What is in the table is what somebody decided to change, which is what
    makes it readable — the rest is the documented starting value."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    store = SqlSettingsStore(engine)
    await store.create_all()

    assert await store.load() == {}

    await engine.dispose()


async def test_a_saved_parameter_comes_back(store):
    await store.save({"condensation_threshold_seconds": 90.0})

    assert await store.load() == {"condensation_threshold_seconds": 90.0}


async def test_saving_the_same_parameter_twice_replaces_it(store):
    await store.save({"condensation_threshold_seconds": 90.0})

    await store.save({"condensation_threshold_seconds": 60.0})

    assert await store.load() == {"condensation_threshold_seconds": 60.0}


async def test_saving_one_parameter_leaves_the_others_standing(store):
    await store.save({"condensation_threshold_seconds": 90.0})

    await store.save({"max_message_characters": 400})

    assert await store.load() == {
        "condensation_threshold_seconds": 90.0,
        "max_message_characters": 400.0,
    }


async def test_saving_nothing_is_not_an_error(store):
    await store.save({})

    assert await store.load() == {}


async def test_a_change_survives_a_restart(store):
    """The whole reason this is not an environment variable."""
    await LiveSettings(store=store).save(condensation_threshold_seconds=45.0)

    after_restart = await LiveSettings(store=store).get()

    assert after_restart.condensation_threshold_seconds == 45.0


async def test_an_integer_parameter_survives_the_column_it_was_stored_in(store):
    """One numeric column holds every parameter, so this goes in an int and comes back a
    float. It has to arrive as an int: it is a length that slices text."""
    await LiveSettings(store=store).save(max_message_characters=400)

    value = (await LiveSettings(store=store).get()).max_message_characters

    assert value == 400
    assert isinstance(value, int)


async def test_a_stored_row_still_obeys_the_orderings(store):
    """The rules are not a property of the API that writes the table. Somebody with a psql
    prompt can put anything in it, and the instance that reads it has to be the one that
    refuses — which it does by not starting."""
    await store.save({"condensation_threshold_seconds": 999.0})

    with pytest.raises(InvalidSettings):
        await LiveSettings(store=store).get()


async def test_a_row_for_a_parameter_that_no_longer_exists_is_loud(store):
    """A parameter removed from the code leaves its row behind. Dropping it silently would
    make the table quietly disagree with the system for as long as nobody looked."""
    await store.save({"a_knob_that_was_removed": 12.0})

    with pytest.raises(InvalidSettings) as raised:
        await LiveSettings(store=store).get()

    assert "a_knob_that_was_removed" in str(raised.value)


async def test_the_defaults_are_what_an_untouched_installation_runs(store):
    assert await LiveSettings(store=store).get() == SalonSettings()
