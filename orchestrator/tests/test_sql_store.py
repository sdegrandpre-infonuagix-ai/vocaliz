"""The durable store, exercised as SQL rather than as a mock.

Against SQLite, which SQLAlchemy speaks well enough that the statements under test are the
same ones Postgres will run — the upsert dialect being the single difference, and it is
chosen from the engine. What this buys is that the suite needs no database to run, which is
the condition Story 6.1 set for every story after it.

The behaviour these assert is the same behaviour `test_salon_log.py` asserts against the
in-memory store. That is the point of there being a port.
"""
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine

from src.journal import JournalEntry, SalonLog
from src.journal.sql_store import SqlJournalStore, async_url

T0 = datetime(2026, 8, 8, 12, 0, 0, tzinfo=timezone.utc)

MORNING = dict(participant_id="hans", text="Guten Morgen", language="de")
BONJOUR = dict(participant_id="marie", text="Bonjour", language="fr")


async def translate(text, *, source, target):
    return f"{text} [{target}]"


@pytest_asyncio.fixture
async def store():
    engine = create_async_engine("sqlite+aiosqlite://")
    store = SqlJournalStore(engine)
    await store.create_all()
    try:
        yield store
    finally:
        await engine.dispose()


def _entry(sequence=1, **overrides):
    return JournalEntry(
        **{
            "sequence": sequence,
            "participant_id": "hans",
            "text": "Guten Morgen",
            "language": "de",
            "arrived_at": T0,
            "duration_seconds": 2.0,
            **overrides,
        }
    )


# ── Reaching the database at all ──────────────────────────────────────────────


@pytest.mark.parametrize(
    ("configured", "expected"),
    [
        ("postgresql://salon:pw@aurora:5432/salon", "postgresql+asyncpg://salon:pw@aurora:5432/salon"),
        ("postgres://salon:pw@aurora:5432/salon", "postgresql+asyncpg://salon:pw@aurora:5432/salon"),
        # Already named, and naming it twice would be wrong.
        ("postgresql+asyncpg://salon@aurora/salon", "postgresql+asyncpg://salon@aurora/salon"),
        ("sqlite+aiosqlite://", "sqlite+aiosqlite://"),
    ],
)
def test_the_configured_url_is_given_its_async_driver(configured, expected):
    """`DATABASE_URL` is shared with the API, which reads it synchronously. Two settings for
    one database would eventually disagree with each other."""
    assert async_url(configured) == expected


# ── The port, against real SQL ────────────────────────────────────────────────


async def test_an_unknown_salon_reads_back_empty(store):
    state = await store.load("nobody-has-spoken-here")

    assert state.entries == ()
    assert state.cursors == {}
    assert state.translations == {}


async def test_a_message_survives_the_round_trip(store):
    await store.append_entry("salon-1", _entry())

    (entry,) = (await store.load("salon-1")).entries

    assert entry == _entry()


async def test_messages_come_back_in_order_whatever_order_they_went_in(store):
    await store.append_entry("salon-1", _entry(2, text="zwei"))
    await store.append_entry("salon-1", _entry(1, text="eins"))

    assert [entry.text for entry in (await store.load("salon-1")).entries] == ["eins", "zwei"]


async def test_a_position_cannot_be_written_twice_over(store):
    """The primary key is what makes a duplicated message an error the database catches
    rather than a second copy of somebody's sentence."""
    await store.append_entry("salon-1", _entry())

    with pytest.raises(IntegrityError):
        await store.append_entry("salon-1", _entry())


async def test_a_cursor_is_overwritten_rather_than_accumulated(store):
    """Where an interpreter used to be is of no interest, and keeping it would be keeping a
    record of how closely somebody was following a conversation."""
    await store.save_cursor("salon-1", "marie", 1)
    await store.save_cursor("salon-1", "marie", 4)

    assert (await store.load("salon-1")).cursors == {"marie": 4}


async def test_cursors_of_different_readers_are_different_rows(store):
    await store.save_cursor("salon-1", "marie", 1)
    await store.save_cursor("salon-1", "hans", 3)

    assert (await store.load("salon-1")).cursors == {"marie": 1, "hans": 3}


async def test_a_translation_written_twice_is_not_an_error(store):
    """Two instances racing to write the same pair are writing the same text."""
    await store.save_translation("salon-1", 1, "fr", "Bonjour")
    await store.save_translation("salon-1", 1, "fr", "Bonjour")

    assert (await store.load("salon-1")).translations == {(1, "fr"): "Bonjour"}


async def test_translations_of_different_languages_live_side_by_side(store):
    await store.save_translation("salon-1", 1, "fr", "Bonjour")
    await store.save_translation("salon-1", 1, "es", "Buenos días")

    assert (await store.load("salon-1")).translations == {
        (1, "fr"): "Bonjour",
        (1, "es"): "Buenos días",
    }


async def test_two_salons_never_read_each_other(store):
    await store.append_entry("salon-1", _entry(text="Guten Morgen"))
    await store.append_entry("salon-2", _entry(text="Bonjour"))
    await store.save_cursor("salon-1", "marie", 1)

    assert (await store.load("salon-2")).entries[0].text == "Bonjour"
    assert (await store.load("salon-2")).cursors == {}


# ── A Salon actually surviving its instance ───────────────────────────────────


async def test_a_salon_is_taken_over_from_the_database(store):
    """The acceptance criterion end to end, over SQL: the instance holding this Salon is
    gone, and another one picks it up without losing a message or repeating one."""
    log = SalonLog(salon_id="salon-1", store=store, translate=translate)
    log.attach("marie", from_start=True)
    await log.record(**MORNING)
    await log.record(**BONJOUR)
    await log.advance("marie", 1)

    resumed = await SalonLog.resume(salon_id="salon-1", store=store, translate=translate)

    assert [entry.text for entry in resumed.entries] == ["Guten Morgen", "Bonjour"]
    assert resumed.cursor("marie") == 1
    assert [entry.text for entry in resumed.pending("marie")] == ["Bonjour"]


async def test_a_taken_over_salon_carries_on_numbering(store):
    log = SalonLog(salon_id="salon-1", store=store, translate=translate)
    await log.record(**MORNING)

    resumed = await SalonLog.resume(salon_id="salon-1", store=store, translate=translate)

    assert (await resumed.record(**BONJOUR)).sequence == 2


async def test_a_taken_over_salon_does_not_pay_for_a_translation_twice(store):
    calls = []

    async def counted(text, *, source, target):
        calls.append(target)
        return f"{text} [{target}]"

    log = SalonLog(salon_id="salon-1", store=store, translate=counted)
    entry = await log.record(**MORNING)
    await log.render(entry, "fr")

    resumed = await SalonLog.resume(salon_id="salon-1", store=store, translate=counted)
    await resumed.render(resumed.entries[0], "fr")

    assert calls == ["fr"]


def test_only_the_scheme_is_rewritten():
    """A password or a database name containing the scheme must not be rewritten with it."""
    assert async_url("postgresql://u:postgresql://@host/db") == (
        "postgresql+asyncpg://u:postgresql://@host/db"
    )


async def test_an_arrival_time_keeps_its_timezone(store):
    """Ordering two Salons' messages against each other, and the one-year expiry of Story
    6.10, both read this column. A naive timestamp would put an hour of doubt in both."""
    await store.append_entry("salon-1", _entry())

    (entry,) = (await store.load("salon-1")).entries

    assert entry.arrived_at == T0
