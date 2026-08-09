"""Three modes in one Salon, and a mode that survives being changed (FR36).

The topology already made most of this free. Every participant has their own room and their
own interpreter, and the conductor only ever talks to the port — so three people on three
different tiers are not a special case the Salon handles, they are the ordinary case it
cannot tell apart. Several tests below assert an absence: nothing anywhere branches on which
adapter a seat happens to hold.

What is not free is changing mode part-way. The adapter has to be replaced while everything
around it stays exactly where it was — the reading position above all. A swap that reset a
cursor would replay the conversation from the beginning, which is a considerably worse
outcome than the wrong voice.
"""
import pytest

from src.interprete import InterpreteFake, Participant, ProviderUnavailable
from src.journal import InMemoryJournalStore, SalonLog
from src.salon import InMemoryRoomProvisioner, Salon

MARIE = Participant(id="marie", language="fr", name="Marie")
HANS = Participant(id="hans", language="de", name="Hans")
SOFIA = Participant(id="sofia", language="es", name="Sofia")


async def translate(text, *, source, target):
    return f"{text} [{target}]"


@pytest.fixture
def salon():
    log = SalonLog(salon_id="s", store=InMemoryJournalStore(), translate=translate)
    return Salon(log=log, rooms=InMemoryRoomProvisioner())


class Premium(InterpreteFake):
    """Stands in for a dearer tier. Different class, identical contract — which is the point."""


async def _join(salon, participant, interpreter=None):
    return await salon.join(
        participant, interpreter or InterpreteFake(participant=participant)
    )


def _tours(salon, participant_id):
    return [
        line.text
        for line in salon.interpreter_of(participant_id).spoken
        if line.kind == "tour"
    ]


# ── Three modes, no distinction ───────────────────────────────────────────────


async def test_three_participants_can_hold_three_different_adapters(salon):
    await _join(salon, MARIE, InterpreteFake(participant=MARIE))
    await _join(salon, HANS, Premium(participant=HANS))
    await _join(salon, SOFIA, InterpreteFake(participant=SOFIA))

    assert isinstance(salon.interpreter_of(HANS.id), Premium)
    assert not isinstance(salon.interpreter_of(MARIE.id), Premium)


async def test_everybody_hears_everything_whatever_their_mode(salon):
    """The conductor talks to the port and to nothing else, so a dearer adapter is not a
    different code path — it is the same one holding a different object."""
    await _join(salon, MARIE, InterpreteFake(participant=MARIE))
    await _join(salon, HANS, Premium(participant=HANS))

    await salon.ingest(MARIE.id, "Bonjour", language="fr")
    await salon.deliver_all()

    assert _tours(salon, HANS.id) == ["Bonjour"]


async def test_the_salon_never_asks_what_mode_somebody_is_on(salon):
    """The static half of the claim: nothing in the conductor branches on an adapter's type,
    so no tier can acquire a special case by accident."""
    source = open("src/salon/conductor.py", encoding="utf-8").read()

    for smell in ("isinstance(", "InterpreteFake", "InterpreteS2S", "InterpreteBase"):
        assert smell not in source, f"the conductor should not know about {smell}"


async def test_one_persons_adapter_failing_leaves_the_others_alone(salon):
    """Already true since Story 6.4, and worth restating here: mixing tiers must not turn
    one room's trouble into everybody's."""

    class Broken(InterpreteFake):
        async def render(self, tour):
            raise ProviderUnavailable(HANS.id, "down")

    await _join(salon, MARIE)
    await salon.join(HANS, Broken(participant=HANS))
    await _join(salon, SOFIA)

    await salon.ingest(MARIE.id, "Bonjour", language="fr")
    await salon.deliver_all()

    assert _tours(salon, SOFIA.id) == ["Bonjour"]
    assert salon.pending_for(HANS.id) != ()


# ── A mode persists ───────────────────────────────────────────────────────────


async def test_a_mode_lasts_the_whole_salon(salon):
    """Nothing changes it but the participant. The test is that the same object is still
    there after the Salon has been thoroughly used."""
    chosen = Premium(participant=HANS)
    await _join(salon, MARIE)
    await _join(salon, HANS, chosen)

    for _ in range(3):
        await salon.ingest(MARIE.id, "Bonjour", language="fr")
        await salon.deliver_all()

    assert salon.interpreter_of(HANS.id) is chosen


async def test_somebody_elses_change_does_not_move_my_mode(salon):
    mine = Premium(participant=HANS)
    await _join(salon, MARIE)
    await _join(salon, HANS, mine)
    await _join(salon, SOFIA)

    await salon.change_mode(SOFIA.id, InterpreteFake(participant=SOFIA))

    assert salon.interpreter_of(HANS.id) is mine


# ── Changing it, without breaking anything ────────────────────────────────────


async def test_changing_mode_replaces_the_adapter(salon):
    await _join(salon, MARIE)
    await _join(salon, HANS)
    replacement = Premium(participant=HANS)

    await salon.change_mode(HANS.id, replacement)

    assert salon.interpreter_of(HANS.id) is replacement


async def test_the_old_adapter_is_closed(salon):
    """It holds a session to a provider. Leaving it open keeps paying for a room nobody is
    listening to."""
    await _join(salon, MARIE)
    old = InterpreteFake(participant=HANS)
    await salon.join(HANS, old)

    await salon.change_mode(HANS.id, Premium(participant=HANS))

    assert old.closed is True


async def test_the_reading_position_does_not_move(salon):
    """The one that matters. A swap that reset the cursor would replay the whole
    conversation from the beginning — worse than the wrong voice by a long way."""
    await _join(salon, MARIE)
    await _join(salon, HANS)
    await salon.ingest(MARIE.id, "Bonjour", language="fr")
    await salon.deliver_all()
    assert salon.pending_for(HANS.id) == ()

    await salon.change_mode(HANS.id, Premium(participant=HANS))

    assert salon.pending_for(HANS.id) == ()


async def test_what_was_already_said_is_not_said_again(salon):
    await _join(salon, MARIE)
    await _join(salon, HANS)
    await salon.ingest(MARIE.id, "Bonjour", language="fr")
    await salon.deliver_all()

    await salon.change_mode(HANS.id, Premium(participant=HANS))
    await salon.deliver_all()

    assert _tours(salon, HANS.id) == []


async def test_the_conversation_carries_on_into_the_new_adapter(salon):
    await _join(salon, MARIE)
    await _join(salon, HANS)
    await salon.change_mode(HANS.id, Premium(participant=HANS))

    await salon.ingest(MARIE.id, "Encore un mot", language="fr")
    await salon.deliver_all()

    assert _tours(salon, HANS.id) == ["Encore un mot"]


async def test_the_room_is_the_same_room(salon):
    """Closing and reopening it would put the participant through a reconnection, which is
    precisely the rupture the story forbids."""
    await _join(salon, MARIE)
    await _join(salon, HANS)
    before = await salon.room_of(HANS.id)

    await salon.change_mode(HANS.id, Premium(participant=HANS))

    assert await salon.room_of(HANS.id) is before


async def test_nobody_is_introduced_all_over_again(salon):
    """Introductions belong to the listener, not to the adapter. Re-introducing everybody
    after a mode change would tell somebody about people they already know."""
    await _join(salon, MARIE)
    await _join(salon, HANS)
    await salon.ingest(MARIE.id, "Bonjour", language="fr")
    await salon.deliver_all()

    await salon.change_mode(HANS.id, Premium(participant=HANS))
    await salon.ingest(MARIE.id, "Encore", language="fr")
    await salon.deliver_all()

    assert [line.kind for line in salon.interpreter_of(HANS.id).spoken] == ["tour"]


async def test_the_others_are_untouched_by_a_change(salon):
    await _join(salon, MARIE)
    await _join(salon, HANS)
    await _join(salon, SOFIA)
    await salon.ingest(MARIE.id, "Bonjour", language="fr")

    await salon.change_mode(HANS.id, Premium(participant=HANS))

    assert salon.pending_for(SOFIA.id) != ()


async def test_changing_the_mode_of_somebody_who_is_not_here_does_nothing(salon):
    await _join(salon, MARIE)

    await salon.change_mode("nobody", InterpreteFake(participant=HANS))

    assert salon.participants == ("marie",)


async def test_the_salon_stays_up_through_a_change(salon):
    await _join(salon, MARIE)
    await _join(salon, HANS)

    await salon.change_mode(HANS.id, Premium(participant=HANS))

    assert set(salon.participants) == {"marie", "hans"}
