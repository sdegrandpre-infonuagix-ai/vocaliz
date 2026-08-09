"""Taking what the interpreters heard into the journal, and what happens when one fails.

`deliver` is the journal reaching a room; `collect` is a room reaching the journal. They
are separate calls because they must not wait on each other: an interpreter that has fallen
behind on its rendering cannot be allowed to hold up anybody else's words arriving.
"""
import pytest

from src.interprete import InterpreteFake, Participant
from src.journal import InMemoryJournalStore, SalonLog
from src.salon import InMemoryRoomProvisioner, Salon

MARIE = Participant(id="marie", language="fr", name="Marie")
HANS = Participant(id="hans", language="de", name="Hans")


async def translate(text, *, source, target):
    return f"{text} [{target}]"


@pytest.fixture
def rooms():
    return InMemoryRoomProvisioner()


@pytest.fixture
def salon(rooms):
    log = SalonLog(salon_id="salon-1", store=InMemoryJournalStore(), translate=translate)
    return Salon(log=log, rooms=rooms)


async def _join(salon, participant, **kwargs):
    interpreter = InterpreteFake(participant=participant)
    await salon.join(participant, interpreter, **kwargs)
    return interpreter


# ── A room reaching the journal ───────────────────────────────────────────────


async def test_what_an_interpreter_heard_reaches_the_journal(salon):
    hans = await _join(salon, HANS)
    hans.queue("Guten Morgen", language="de")

    recorded = await salon.collect()

    assert [entry.text for entry in recorded] == ["Guten Morgen"]
    assert [entry.text for entry in salon.log.entries] == ["Guten Morgen"]


async def test_a_message_enters_the_journal_in_the_language_it_was_spoken_in(salon):
    """The speaker makes the original. Somebody switching to English mid-Salon is recorded
    in English, whatever language their interpreter usually hears."""
    hans = await _join(salon, HANS)
    hans.queue("Actually, hold on", language="en")

    await salon.collect()

    assert salon.log.entries[0].language == "en"


async def test_a_silent_room_adds_nothing(salon):
    await _join(salon, HANS)

    assert await salon.collect() == ()
    assert salon.log.entries == ()


async def test_an_empty_utterance_never_becomes_a_position(salon):
    """Silence taken for speech, or Story 6.11's cleaning leaving nothing behind. A position
    holding it would render as silence to every listener."""
    hans = await _join(salon, HANS)
    hans.queue("   ", language="de")

    assert await salon.collect() == ()
    assert salon.log.entries == ()


async def test_every_room_is_collected_from(salon):
    marie = await _join(salon, MARIE)
    hans = await _join(salon, HANS)
    marie.queue("Bonjour", language="fr")
    hans.queue("Guten Morgen", language="de")

    recorded = await salon.collect()

    assert {entry.text for entry in recorded} == {"Bonjour", "Guten Morgen"}


async def test_collecting_from_a_salon_nobody_is_in_is_harmless(salon):
    assert await salon.collect() == ()


# ── When an interpreter cannot say it ─────────────────────────────────────────


async def test_a_failing_interpreter_keeps_its_place(salon):
    """NFR3 has already told that participant out loud. What matters here is that their
    position does not move: what they missed is still theirs to catch up on."""
    await _join(salon, MARIE)
    hans = await _join(salon, HANS)
    await salon.ingest(MARIE.id, "Bonjour", language="fr")
    hans.fail_with = ConnectionError("the model stopped answering")

    await salon.deliver(HANS.id)

    assert salon.log.cursor(HANS.id) == 0
    assert len(salon.pending_for(HANS.id)) == 1


async def test_one_broken_interpreter_does_not_silence_the_others(salon):
    """The acceptance criterion of this story, in its harshest form: one room in trouble,
    every other room carrying on."""
    marie = await _join(salon, MARIE)
    hans = await _join(salon, HANS)
    hans.fail_with = ConnectionError("the model stopped answering")

    await salon.ingest("rhys", "Bore da", language="cy")
    await salon.deliver_all()

    assert [line.text for line in marie.spoken] == ["Bore da"]
    assert salon.log.cursor(MARIE.id) == 1


async def test_a_recovered_interpreter_resumes_where_it_stopped(salon):
    """Nothing lost and nothing repeated — the same promise a takeover makes."""
    hans = await _join(salon, HANS)
    await salon.ingest(MARIE.id, "Bonjour", language="fr")
    hans.fail_with = ConnectionError("the model stopped answering")
    await salon.deliver(HANS.id)

    hans.fail_with = None
    await salon.deliver(HANS.id)

    assert [line.text for line in hans.spoken] == ["Bonjour"]
    assert salon.log.cursor(HANS.id) == 1


async def test_delivering_to_somebody_who_is_not_here_is_harmless(salon):
    """A message can be delivered to a participant in the instant between their connection
    dying and the Salon being told about it."""
    await salon.deliver("nobody")


async def test_delivering_to_somebody_who_just_left_is_harmless(salon):
    await _join(salon, MARIE)
    await salon.ingest(HANS.id, "Guten Morgen", language="de")

    await salon.leave(MARIE.id)
    await salon.deliver(MARIE.id)
