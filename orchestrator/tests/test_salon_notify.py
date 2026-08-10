"""Waking a served participant's agent the moment something is ready for them.

The fast path alongside the poll `serving.py`'s `GET .../script` already guarantees — see
`src/salon/notify.py`. These tests are about *when* a Salon reaches for the notifier and
*who* it reaches for, never about what it says: the notifier carries no content, only an
invitation to ask.
"""
import pytest

from src.interprete import InterpreteFake, Participant
from src.journal import InMemoryJournalStore, SalonLog
from src.salon import FailingNotifier, InMemoryRoomProvisioner, RecordingNotifier, Salon

MARIE = Participant(id="marie", language="fr", name="Marie")
HANS = Participant(id="hans", language="de", name="Hans")


async def translate(text, *, source, target):
    return f"{text} [{target}]"


def _log(salon_id="salon-1"):
    return SalonLog(salon_id=salon_id, store=InMemoryJournalStore(), translate=translate)


@pytest.fixture
def notifier():
    return RecordingNotifier()


@pytest.fixture
def salon(notifier):
    return Salon(log=_log(), rooms=InMemoryRoomProvisioner(), notifier=notifier)


# ── Who gets woken ──────────────────────────────────────────────────────────────


async def test_a_served_listener_is_woken_when_somebody_else_speaks(salon, notifier):
    await salon.join(MARIE, InterpreteFake(participant=MARIE))  # the speaker, in-process
    await salon.join(HANS)  # served — no interpreter, the production case

    await salon.ingest(MARIE.id, "Bonjour", language="fr")

    assert notifier.notified == [("salon-1", HANS.id)]


async def test_nobody_is_woken_for_their_own_words(salon, notifier):
    """The one thing `_render` never says back to a listener, and the one listener a wake
    for their own words would be for."""
    await salon.join(HANS)  # served, speaking for itself

    await salon.ingest(HANS.id, "Hallo", language="de")

    assert notifier.notified == []


async def test_an_in_process_listener_is_never_woken(salon, notifier):
    """It has no agent polling anything to wake — `deliver` reaches it directly, in the same
    process, which is what makes it in-process."""
    await salon.join(MARIE, InterpreteFake(participant=MARIE))
    await salon.join(HANS, InterpreteFake(participant=HANS))

    await salon.ingest(MARIE.id, "Bonjour", language="fr")

    assert notifier.notified == []


async def test_a_muted_microphone_records_nothing_so_wakes_nobody():
    """`ingest` returns before it ever records a word from a cut microphone — see its own
    first check — so there is nothing here for the notifier to be reached about."""
    notifier = RecordingNotifier()
    salon = Salon(
        log=_log("salon-muted"),
        rooms=InMemoryRoomProvisioner(),
        notifier=notifier,
        host_id="marie",
    )
    await salon.join(MARIE, InterpreteFake(participant=MARIE))
    await salon.join(HANS)
    await salon.mute(HANS.id, by="marie")
    notifier.notified.clear()  # the mute notice itself is an announcement, not an ingest

    recorded = await salon.ingest(HANS.id, "Hallo", language="de")

    assert recorded == ()
    assert notifier.notified == []


# ── Resilience ───────────────────────────────────────────────────────────────────


async def test_a_failing_notifier_does_not_lose_the_message(notifier):
    """A Salon must not lose what was said, or the seat that spoke it, over a notifier that
    could not be reached — the poll still finds it."""
    salon = Salon(log=_log("salon-2"), rooms=InMemoryRoomProvisioner(), notifier=FailingNotifier())
    await salon.join(MARIE, InterpreteFake(participant=MARIE))
    await salon.join(HANS)

    recorded = await salon.ingest(MARIE.id, "Bonjour", language="fr")

    assert len(recorded) == 1
    assert salon.pending_for(HANS.id)


async def test_no_notifier_configured_is_the_ordinary_default():
    """A deployment that never passes one behaves exactly as it did before this existed."""
    salon = Salon(log=_log("salon-3"), rooms=InMemoryRoomProvisioner())
    await salon.join(MARIE, InterpreteFake(participant=MARIE))
    await salon.join(HANS)

    recorded = await salon.ingest(MARIE.id, "Bonjour", language="fr")

    assert len(recorded) == 1
