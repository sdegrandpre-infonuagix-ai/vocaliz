"""A Salon's journal, its readers' positions and its translations, kept durable.

This is the object an orchestrator instance holds one of per Salon, and the reason
Story 6.1 could say that affinity is a preference rather than a condition of survival:
everything here is written as it happens, so another instance re-reads it and carries on.

What "carries on" has to mean, exactly: no loss and no duplication. A message rendered
before the crash is not rendered again — hearing the same sentence twice is worse than
hearing it late, because the listener cannot tell a repeat from somebody saying the same
thing again — and a message that had not been reached yet is still waiting.
"""
import pytest

from src.journal import SalonLog
from src.journal.store import InMemoryJournalStore

MORNING = dict(participant_id="hans", text="Guten Morgen", language="de")
BONJOUR = dict(participant_id="marie", text="Bonjour", language="fr")
CAVA = dict(participant_id="marie", text="Ça va ?", language="fr")


async def translate(text, *, source, target):
    return f"{text} [{target}]"


@pytest.fixture
def store():
    return InMemoryJournalStore()


@pytest.fixture
def log(store):
    return SalonLog(salon_id="salon-1", store=store, translate=translate)


# ── One structure, many readers ───────────────────────────────────────────────


async def test_a_message_recorded_is_a_message_every_reader_can_still_get(log):
    log.attach("hans")
    log.attach("marie")

    await log.record(**MORNING)

    assert len(log.pending("hans")) == 1
    assert len(log.pending("marie")) == 1


async def test_a_reader_advancing_leaves_the_others_where_they_were(log):
    log.attach("hans")
    log.attach("marie")
    entry = await log.record(**MORNING)

    await log.advance("hans", entry.sequence)

    assert log.pending("hans") == ()
    assert len(log.pending("marie")) == 1


async def test_a_reader_joining_later_starts_at_the_head(log):
    await log.record(**MORNING)

    log.attach("late")

    assert log.pending("late") == ()


async def test_a_reader_given_the_history_starts_at_the_beginning(log):
    """Story 6.10 grants or refuses the history by placing this position, and nothing else
    is required of it — the ordinary rules do the rest."""
    await log.record(**MORNING)

    log.attach("late", from_start=True)

    assert len(log.pending("late")) == 1


async def test_a_reader_that_leaves_is_no_longer_waited_for(log):
    log.attach("marie")
    await log.record(**MORNING)

    log.detach("marie")

    assert "marie" not in log.readers


async def test_the_lag_of_a_reader_is_the_content_still_ahead_of_it(log):
    log.attach("marie", from_start=True)
    await log.record(**MORNING, duration_seconds=30.0)
    await log.record(**BONJOUR, duration_seconds=12.0)

    assert log.lag_seconds("marie") == pytest.approx(42.0)

    await log.advance("marie", 1)

    assert log.lag_seconds("marie") == pytest.approx(12.0)


# ── Rendering, in each reader's own language ──────────────────────────────────


async def test_a_reader_is_given_the_message_in_its_own_language(log):
    entry = await log.record(**MORNING)

    assert await log.render(entry, "fr") == "Guten Morgen [fr]"


async def test_a_message_already_in_the_reader_s_language_is_given_as_spoken(log, store):
    entry = await log.record(**BONJOUR)

    assert await log.render(entry, "fr") == "Bonjour"

    state = await store.load("salon-1")
    assert state.translations == {}


# ── Durability ────────────────────────────────────────────────────────────────


async def test_every_message_is_written_as_it_arrives(log, store):
    await log.record(**MORNING)
    await log.record(**BONJOUR)

    state = await store.load("salon-1")

    assert [entry.text for entry in state.entries] == ["Guten Morgen", "Bonjour"]


async def test_every_position_is_written_when_it_moves(log, store):
    log.attach("marie", from_start=True)
    await log.record(**MORNING)

    await log.advance("marie", 1)

    assert (await store.load("salon-1")).cursors == {"marie": 1}


async def test_a_position_is_written_the_moment_a_reader_attaches(log, store):
    """Otherwise a reader that joined and crashed before rendering anything would come back
    at the head of a journal it had been given the history of."""
    await log.record(**MORNING)

    log.attach("late", from_start=True)
    await log.checkpoint()

    assert (await store.load("salon-1")).cursors == {"late": 0}


async def test_a_translation_is_written_once_produced(log, store):
    entry = await log.record(**MORNING)

    await log.render(entry, "fr")

    assert (await store.load("salon-1")).translations == {(1, "fr"): "Guten Morgen [fr]"}


# ── Resuming ──────────────────────────────────────────────────────────────────


async def test_a_resumed_salon_has_the_whole_journal(store):
    log = SalonLog(salon_id="salon-1", store=store, translate=translate)
    await log.record(**MORNING)
    await log.record(**BONJOUR)

    resumed = await SalonLog.resume(salon_id="salon-1", store=store, translate=translate)

    assert [entry.text for entry in resumed.entries] == ["Guten Morgen", "Bonjour"]
    assert resumed.head == 2


async def test_a_resumed_salon_keeps_numbering_where_it_left_off(store):
    log = SalonLog(salon_id="salon-1", store=store, translate=translate)
    await log.record(**MORNING)

    resumed = await SalonLog.resume(salon_id="salon-1", store=store, translate=translate)
    entry = await resumed.record(**BONJOUR)

    assert entry.sequence == 2


async def test_a_resumed_reader_starts_exactly_where_it_stopped(store):
    """No loss and no duplication, which is the whole of the acceptance criterion."""
    log = SalonLog(salon_id="salon-1", store=store, translate=translate)
    log.attach("marie", from_start=True)
    await log.record(**MORNING)
    await log.record(**BONJOUR)
    await log.advance("marie", 1)
    await log.record(**CAVA)

    resumed = await SalonLog.resume(salon_id="salon-1", store=store, translate=translate)

    assert resumed.cursor("marie") == 1
    assert [entry.text for entry in resumed.pending("marie")] == ["Bonjour", "Ça va ?"]


async def test_a_resumed_salon_does_not_pay_twice_for_a_translation(store):
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


async def test_resuming_a_salon_nobody_has_written_gives_an_empty_one(store):
    resumed = await SalonLog.resume(salon_id="unknown", store=store, translate=translate)

    assert resumed.entries == ()
    assert resumed.head == 0
    assert resumed.readers == ()


async def test_two_salons_do_not_see_each_other(store):
    one = SalonLog(salon_id="salon-1", store=store, translate=translate)
    other = SalonLog(salon_id="salon-2", store=store, translate=translate)

    await one.record(**MORNING)
    await other.record(**BONJOUR)

    assert (await store.load("salon-1")).entries[0].text == "Guten Morgen"
    assert (await store.load("salon-2")).entries[0].text == "Bonjour"
    assert one.head == 1 and other.head == 1


async def test_a_reader_cannot_be_advanced_past_the_head(log):
    log.attach("marie", from_start=True)
    await log.record(**MORNING)

    with pytest.raises(ValueError):
        await log.advance("marie", 9)


async def test_an_empty_message_is_neither_recorded_nor_written(log, store):
    assert await log.record(participant_id="hans", text="  ", language="de") is None
    assert (await store.load("salon-1")).entries == ()
