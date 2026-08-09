"""A long intervention, once it is in the journal and on its way to the other rooms.

Three things have to hold. Every piece is under the maximum. The pieces occupy consecutive
positions, so no other participant's message can land between them. And nothing the system
has to say — an announcement — is spoken into the gap either.

The last one is the one that needs code. The first two fall out of assigning all the
positions at once.
"""
import pytest

from src.interprete import Annonce, InterpreteFake, Participant
from src.journal import InMemoryJournalStore, SalonLog
from src.salon import InMemoryRoomProvisioner, Salon

MARIE = Participant(id="marie", language="fr", name="Marie")
HANS = Participant(id="hans", language="de", name="Hans")

# Six sentences of about forty characters each — long enough to be cut several ways.
LONG = " ".join(f"Voici la phrase numéro {n} de mon intervention." for n in range(6))


async def translate(text, *, source, target):
    return f"{text} [{target}]"


@pytest.fixture
def store():
    return InMemoryJournalStore()


@pytest.fixture
def salon(store):
    log = SalonLog(salon_id="salon-1", store=store, translate=translate)
    return Salon(log=log, rooms=InMemoryRoomProvisioner(), max_message_characters=60)


async def _join(salon, participant, **kwargs):
    return await salon.join(participant, InterpreteFake(participant=participant), **kwargs)


# ── Into the journal ──────────────────────────────────────────────────────────


async def test_a_long_intervention_becomes_several_messages(salon):
    await _join(salon, MARIE)

    pieces = await salon.ingest(MARIE.id, LONG, language="fr")

    assert len(pieces) > 1
    assert all(len(entry.text) <= 60 for entry in pieces)


async def test_a_short_intervention_stays_one_message(salon):
    await _join(salon, MARIE)

    pieces = await salon.ingest(MARIE.id, "Bonjour.", language="fr")

    assert len(pieces) == 1
    assert pieces[0].parts == 1


async def test_nothing_at_all_becomes_no_message(salon):
    await _join(salon, MARIE)

    assert await salon.ingest(MARIE.id, "   ", language="fr") == ()


async def test_the_pieces_take_consecutive_positions(salon):
    """This is what stops another participant's message landing in the middle: the
    positions are handed out in one go, so there is no gap to land in."""
    await _join(salon, MARIE)

    pieces = await salon.ingest(MARIE.id, LONG, language="fr")

    sequences = [entry.sequence for entry in pieces]
    assert sequences == list(range(sequences[0], sequences[0] + len(sequences)))


async def test_each_piece_knows_where_it_sits_in_the_run(salon):
    await _join(salon, MARIE)

    pieces = await salon.ingest(MARIE.id, LONG, language="fr")

    assert [entry.part for entry in pieces] == list(range(1, len(pieces) + 1))
    assert {entry.parts for entry in pieces} == {len(pieces)}


async def test_only_the_last_piece_ends_the_run(salon):
    await _join(salon, MARIE)

    pieces = await salon.ingest(MARIE.id, LONG, language="fr")

    assert all(entry.mid_run for entry in pieces[:-1])
    assert pieces[-1].mid_run is False


async def test_every_piece_keeps_the_language_it_was_spoken_in(salon):
    await _join(salon, MARIE)

    pieces = await salon.ingest(MARIE.id, LONG, language="fr")

    assert {entry.language for entry in pieces} == {"fr"}


async def test_a_run_is_written_to_storage_piece_by_piece(salon, store):
    await _join(salon, MARIE)

    pieces = await salon.ingest(MARIE.id, LONG, language="fr")

    stored = (await store.load("salon-1")).entries
    assert len(stored) == len(pieces)
    assert [entry.parts for entry in stored] == [len(pieces)] * len(pieces)


async def test_another_participant_speaking_lands_after_the_whole_run(salon):
    await _join(salon, MARIE)
    await _join(salon, HANS)

    pieces = await salon.ingest(MARIE.id, LONG, language="fr")
    (interruption,) = await salon.ingest(HANS.id, "Kurz!", language="de")

    assert interruption.sequence == pieces[-1].sequence + 1


# ── Out to the other rooms ────────────────────────────────────────────────────


async def test_a_listener_receives_every_piece(salon):
    await _join(salon, MARIE)
    await _join(salon, HANS)
    await salon.ingest(MARIE.id, LONG, language="fr")

    await salon.deliver(HANS.id)

    spoken = salon.interpreter_of(HANS.id).spoken
    assert " ".join(line.text for line in spoken) == LONG


async def test_an_announcement_waits_for_the_end_of_a_run(salon):
    """The acceptance criterion. An announcement dropped between two halves of somebody's
    sentence is worse than the same announcement a second later."""
    await _join(salon, MARIE)
    await _join(salon, HANS)
    pieces = await salon.ingest(MARIE.id, LONG, language="fr")
    hans = salon.interpreter_of(HANS.id)

    await salon.deliver_upto(HANS.id, pieces[0].sequence)
    await salon.announce(HANS.id, Annonce(text="Rhys est arrivé", language="de"))

    assert [line.kind for line in hans.spoken] == ["tour"]


async def test_the_announcement_is_spoken_once_the_run_is_over(salon):
    await _join(salon, MARIE)
    await _join(salon, HANS)
    pieces = await salon.ingest(MARIE.id, LONG, language="fr")
    hans = salon.interpreter_of(HANS.id)

    await salon.deliver_upto(HANS.id, pieces[0].sequence)
    await salon.announce(HANS.id, Annonce(text="Rhys est arrivé", language="de"))
    await salon.deliver(HANS.id)

    assert [line.kind for line in hans.spoken][-1] == "annonce"
    assert [line.text for line in hans.spoken][-1] == "Rhys est arrivé"


async def test_an_announcement_outside_a_run_is_spoken_at_once(salon):
    await _join(salon, MARIE)
    await _join(salon, HANS)
    hans = salon.interpreter_of(HANS.id)

    await salon.announce(HANS.id, Annonce(text="Rhys est arrivé", language="de"))

    assert [line.kind for line in hans.spoken] == ["annonce"]


async def test_announcements_held_back_keep_their_order(salon):
    await _join(salon, MARIE)
    await _join(salon, HANS)
    pieces = await salon.ingest(MARIE.id, LONG, language="fr")
    hans = salon.interpreter_of(HANS.id)

    await salon.deliver_upto(HANS.id, pieces[0].sequence)
    await salon.announce(HANS.id, Annonce(text="premier", language="de"))
    await salon.announce(HANS.id, Annonce(text="second", language="de"))
    await salon.deliver(HANS.id)

    held = [line.text for line in hans.spoken if line.kind == "annonce"]
    assert held == ["premier", "second"]


async def test_a_participant_who_left_is_not_announced_to(salon):
    await _join(salon, MARIE)

    await salon.leave(MARIE.id)

    await salon.announce(MARIE.id, Annonce(text="trop tard", language="fr"))


async def test_the_speaker_is_not_held_up_by_their_own_run(salon):
    """Marie is not rendered her own words, so she is never mid-run — an announcement for
    her has nothing to wait for."""
    await _join(salon, MARIE)
    await salon.ingest(MARIE.id, LONG, language="fr")
    await salon.deliver(MARIE.id)

    await salon.announce(MARIE.id, Annonce(text="pour Marie", language="fr"))

    assert [line.kind for line in salon.interpreter_of(MARIE.id).spoken] == ["annonce"]


async def test_delivering_upto_for_somebody_who_is_not_here_does_nothing(salon):
    await salon.deliver_upto("nobody", 1)

    assert salon.participants == ()


async def test_an_announcement_that_cannot_be_spoken_is_not_replayed_forever(salon):
    """Their adapter has already told them out loud (NFR3). Putting the announcement back
    would have every later delivery try it again, and an announcement is not worth that."""
    await _join(salon, MARIE)
    await _join(salon, HANS)
    hans = salon.interpreter_of(HANS.id)
    hans.fail_with = ConnectionError("model gone")

    await salon.announce(HANS.id, Annonce(text="Rhys est arrivé", language="de"))

    hans.fail_with = None
    await salon.ingest(MARIE.id, "Bonjour.", language="fr")
    await salon.deliver(HANS.id)

    assert [line.kind for line in hans.spoken] == ["tour"]
