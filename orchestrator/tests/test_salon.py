"""A Salon running: one room and one interpreter per participant, over one journal.

This is where the three pieces of the epic meet. Story 6.3 gave the journal and the reading
positions, 6.2 gave the interpreters, and this is the thing that provisions a room for each
participant and moves messages from the journal into every interpreter but the one that
produced them.

The property under test throughout is the one the topology exists for: nobody ever receives
another participant's audio. What crosses between participants is text in the journal, and
it comes back out of each listener's own interpreter, in that listener's own language.
"""
import pytest

from src.interprete import InterpreteFake, Participant
from src.journal import InMemoryJournalStore, SalonLog
from src.salon import InMemoryRoomProvisioner, Salon

MARIE = Participant(id="marie", language="fr", name="Marie")
HANS = Participant(id="hans", language="de", name="Hans")
RHYS = Participant(id="rhys", language="cy", name="Rhys")


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
    return await salon.join(participant, InterpreteFake(participant=participant), **kwargs)


def _tours(salon, participant_id):
    """What was rendered to somebody, leaving out the introductions of Story 6.9 — these
    assertions are about turns delivered, and were written before introductions existed."""
    return [line.text for line in salon.interpreter_of(participant_id).spoken if line.kind == "tour"]


def _tour_languages(salon, participant_id):
    return [
        line.language for line in salon.interpreter_of(participant_id).spoken
        if line.kind == "tour"
    ]


# ── Joining ───────────────────────────────────────────────────────────────────


async def test_joining_provisions_a_room_for_that_participant(salon):
    room = await _join(salon, MARIE)

    assert room.participant_id == "marie"
    assert room.occupants == ("interprete-marie", "marie")
    assert room.closed is False


async def test_three_participants_share_no_room_and_no_occupant(salon, rooms):
    """The acceptance criterion, stated as the thing that cannot happen: there is no room
    with two humans in it, so there is no audio to share and no echo to cancel."""
    for participant in (MARIE, HANS, RHYS):
        await _join(salon, participant)

    assert len(rooms.open_rooms) == 3
    occupants = [set((await salon.room_of(p.id)).occupants) for p in (MARIE, HANS, RHYS)]
    assert occupants[0] & occupants[1] == set()
    assert occupants[1] & occupants[2] == set()
    assert occupants[0] & occupants[2] == set()


async def test_a_participant_joining_is_known_to_the_salon(salon):
    await _join(salon, MARIE)

    assert salon.participants == ("marie",)


async def test_joining_twice_does_not_make_a_second_room(salon, rooms):
    """A reconnection after a dropped signal is the same participant, not a new one."""
    await _join(salon, MARIE)
    await _join(salon, MARIE)

    assert rooms.open_rooms == ("salon-1--marie",)
    assert salon.participants == ("marie",)


async def test_a_host_who_refuses_the_history_starts_somebody_at_the_head(salon):
    """Story 6.10 turned the default the other way round — saying nothing now grants the
    history — so keeping somebody out of it is a decision the host has to make."""
    from src.salon import HistoryAccess

    await _join(salon, MARIE)
    await salon.ingest(MARIE.id, "Bonjour", language="fr")

    await _join(salon, HANS, history=HistoryAccess.REFUSED)

    assert salon.pending_for(HANS.id) == ()


async def test_somebody_joined_from_the_start_is_given_the_history(salon):
    await _join(salon, MARIE)
    await salon.ingest(MARIE.id, "Bonjour", language="fr")

    await _join(salon, HANS, from_start=True)

    assert len(salon.pending_for(HANS.id)) == 1


# ── Talking ───────────────────────────────────────────────────────────────────


async def test_what_one_says_reaches_the_others(salon):
    await _join(salon, MARIE)
    await _join(salon, HANS)

    await salon.ingest(MARIE.id, "Bonjour tout le monde", language="fr")
    await salon.deliver(HANS.id)

    assert _tours(salon, HANS.id) == ["Bonjour tout le monde"]


async def test_each_listener_is_spoken_to_in_their_own_language(salon):
    await _join(salon, MARIE)
    await _join(salon, HANS)
    await _join(salon, RHYS)

    await salon.ingest(MARIE.id, "Bonjour", language="fr")
    await salon.deliver_all()

    assert _tour_languages(salon, HANS.id) == ["de"]
    assert _tour_languages(salon, RHYS.id) == ["cy"]


async def test_nobody_is_told_what_they_themselves_said(salon):
    """An interpreter renders the conversation to its human. Saying their own sentence back
    to them would be the one thing they certainly already know."""
    await _join(salon, MARIE)
    await _join(salon, HANS)

    await salon.ingest(MARIE.id, "Bonjour", language="fr")
    await salon.deliver_all()

    assert _tours(salon, MARIE.id) == []
    assert _tours(salon, HANS.id) == ["Bonjour"]


async def test_delivering_twice_says_nothing_twice(salon):
    """The position moves as it renders. Hearing a sentence twice is worse than hearing it
    late, because a listener cannot tell a repeat from somebody saying it again."""
    await _join(salon, MARIE)
    await _join(salon, HANS)
    await salon.ingest(MARIE.id, "Bonjour", language="fr")

    await salon.deliver(HANS.id)
    await salon.deliver(HANS.id)

    assert len(_tours(salon, HANS.id)) == 1


async def test_three_people_talking_at_once_share_no_audio(salon, rooms):
    """Everything anybody hears comes out of their own interpreter, in their own room."""
    for participant in (MARIE, HANS, RHYS):
        await _join(salon, participant)

    await salon.ingest(MARIE.id, "Bonjour", language="fr")
    await salon.ingest(HANS.id, "Guten Tag", language="de")
    await salon.ingest(RHYS.id, "Bore da", language="cy")
    await salon.deliver_all()

    for participant in (MARIE, HANS, RHYS):
        room = await salon.room_of(participant.id)
        # Nothing was ever put into anybody's room by anybody but their own interpreter.
        assert rooms.published(room) == ()
        assert len(_tours(salon, participant.id)) == 2


async def test_the_journal_holds_what_was_said_in_the_language_it_was_said_in(salon):
    await _join(salon, MARIE)
    await _join(salon, HANS)

    await salon.ingest(MARIE.id, "Bonjour", language="fr")
    await salon.ingest(HANS.id, "Guten Tag", language="de")

    assert [(e.text, e.language) for e in salon.log.entries] == [
        ("Bonjour", "fr"),
        ("Guten Tag", "de"),
    ]


async def test_an_empty_utterance_reaches_nobody(salon):
    await _join(salon, MARIE)
    await _join(salon, HANS)

    assert await salon.ingest(MARIE.id, "   ", language="fr") == ()

    await salon.deliver_all()
    assert salon.interpreter_of(HANS.id).spoken == []


# ── Leaving ───────────────────────────────────────────────────────────────────


async def test_leaving_closes_that_room_and_no_other(salon, rooms):
    await _join(salon, MARIE)
    await _join(salon, HANS)
    marie_room = await salon.room_of(MARIE.id)

    await salon.leave(MARIE.id)

    assert marie_room.closed is True
    assert rooms.open_rooms == ("salon-1--hans",)


async def test_the_conversation_carries_on_after_somebody_leaves(salon):
    """The acceptance criterion: one participant hanging up does not interrupt the others."""
    await _join(salon, MARIE)
    await _join(salon, HANS)
    await _join(salon, RHYS)

    await salon.leave(MARIE.id)
    await salon.ingest(HANS.id, "Guten Tag", language="de")
    await salon.deliver_all()

    assert len(_tours(salon, RHYS.id)) == 1


async def test_somebody_who_left_is_no_longer_spoken_to(salon):
    await _join(salon, MARIE)
    await _join(salon, HANS)
    marie = salon.interpreter_of(MARIE.id)

    await salon.leave(MARIE.id)
    await salon.ingest(HANS.id, "Guten Tag", language="de")
    await salon.deliver_all()

    assert marie.spoken == []
    assert salon.participants == ("hans",)


async def test_leaving_closes_the_interpreter_too(salon):
    """The room going away and the model session going away are two different costs, and
    both are billed by the minute."""
    await _join(salon, MARIE)
    interpreter = salon.interpreter_of(MARIE.id)

    await salon.leave(MARIE.id)

    assert interpreter.closed is True


async def test_leaving_twice_is_harmless(salon):
    """A participant who drops off and whose Salon then ends leaves twice."""
    await _join(salon, MARIE)

    await salon.leave(MARIE.id)
    await salon.leave(MARIE.id)

    assert salon.participants == ()


async def test_leaving_somebody_who_never_joined_is_harmless(salon):
    await salon.leave("someone-else")

    assert salon.participants == ()


async def test_a_departure_leaves_the_journal_intact(salon):
    """What somebody said stays said. Story 6.10 keeps the journal for a year, and a
    participant leaving is not a reason to lose their half of the conversation."""
    await _join(salon, MARIE)
    await salon.ingest(MARIE.id, "Bonjour", language="fr")

    await salon.leave(MARIE.id)

    assert [entry.text for entry in salon.log.entries] == ["Bonjour"]


async def test_closing_a_salon_closes_every_room(salon, rooms):
    for participant in (MARIE, HANS, RHYS):
        await _join(salon, participant)

    await salon.aclose()

    assert rooms.open_rooms == ()
    assert salon.participants == ()


# ── The story, end to end ─────────────────────────────────────────────────────


async def test_a_full_round_trip_between_two_languages(salon):
    """Marie speaks French in her room, Hans hears German in his, and neither room ever
    carried the other's audio. Everything else in this epic is a refinement of this."""
    await _join(salon, MARIE)
    await _join(salon, HANS)
    salon.interpreter_of(MARIE.id).queue("Bonjour tout le monde", language="fr")

    await salon.collect()
    await salon.deliver_all()

    assert _tours(salon, HANS.id) == ["Bonjour tout le monde"]
    assert _tour_languages(salon, HANS.id) == ["de"]
    assert _tours(salon, MARIE.id) == []
