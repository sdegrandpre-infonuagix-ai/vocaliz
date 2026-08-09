"""The host cutting somebody's microphone.

A blunt instrument, deliberately. It stops one participant being heard and does nothing
else: they stay in the Salon, they keep hearing everyone, and the moment it is lifted they
are back in the conversation on exactly the same terms as everybody else.

That last part is the one worth stating. A cut is not a punishment queue and not a
priority: when the microphone comes back, the next thing they say takes the next position
in the journal, behind whoever spoke while they were quiet.
"""
import pytest

from src.interprete import Annonce, InterpreteFake, Participant
from src.journal import InMemoryJournalStore, SalonLog
from src.salon import InMemoryRoomProvisioner, NotTheHost, Salon, microphone_cut

MARIE = Participant(id="marie", language="fr", name="Marie")
HANS = Participant(id="hans", language="de", name="Hans")
RHYS = Participant(id="rhys", language="cy", name="Rhys")


async def translate(text, *, source, target):
    return f"{text} [{target}]"


@pytest.fixture
def salon():
    log = SalonLog(salon_id="salon-1", store=InMemoryJournalStore(), translate=translate)
    return Salon(log=log, rooms=InMemoryRoomProvisioner(), host_id=MARIE.id)


async def _join(salon, participant, **kwargs):
    return await salon.join(participant, InterpreteFake(participant=participant), **kwargs)


def _annonces(salon, participant_id):
    return [line.text for line in salon.interpreter_of(participant_id).spoken if line.kind == "annonce"]


# ── Cutting ───────────────────────────────────────────────────────────────────


async def test_a_cut_stops_that_participant_being_heard(salon):
    await _join(salon, MARIE)
    await _join(salon, HANS)

    await salon.mute(HANS.id, by=MARIE.id)

    assert await salon.ingest(HANS.id, "Guten Tag", language="de") == ()
    assert salon.log.entries == ()


async def test_a_cut_participant_is_told_so_out_loud(salon):
    """Silence with no explanation is indistinguishable from a broken interpreter, and the
    person it happened to is the one who can least tell the difference."""
    await _join(salon, MARIE)
    await _join(salon, HANS)

    await salon.mute(HANS.id, by=MARIE.id)

    assert len(_annonces(salon, HANS.id)) == 1


async def test_the_notice_is_in_the_language_of_whoever_is_cut(salon):
    await _join(salon, MARIE)
    await _join(salon, HANS)

    await salon.mute(HANS.id, by=MARIE.id)

    spoken = salon.interpreter_of(HANS.id).spoken
    assert [line.language for line in spoken] == ["de"]


async def test_the_salon_knows_who_is_cut(salon):
    await _join(salon, MARIE)
    await _join(salon, HANS)

    await salon.mute(HANS.id, by=MARIE.id)

    assert salon.muted == ("hans",)


async def test_cutting_the_same_microphone_twice_says_it_once(salon):
    """A host tapping the control twice meant it once."""
    await _join(salon, MARIE)
    await _join(salon, HANS)

    await salon.mute(HANS.id, by=MARIE.id)
    await salon.mute(HANS.id, by=MARIE.id)

    assert len(_annonces(salon, HANS.id)) == 1


async def test_nobody_else_is_cut_or_told(salon):
    await _join(salon, MARIE)
    await _join(salon, HANS)
    await _join(salon, RHYS)

    await salon.mute(HANS.id, by=MARIE.id)

    assert salon.muted == ("hans",)
    assert _annonces(salon, RHYS.id) == []
    assert len(await salon.ingest(RHYS.id, "Bore da", language="cy")) == 1


async def test_a_cut_is_not_retroactive(salon):
    """What they said before it stays said. Cutting a microphone is not a way to unsay
    something, and the journal is the record of what happened."""
    await _join(salon, MARIE)
    await _join(salon, HANS)
    await salon.ingest(HANS.id, "Guten Tag", language="de")

    await salon.mute(HANS.id, by=MARIE.id)

    assert [entry.text for entry in salon.log.entries] == ["Guten Tag"]


async def test_a_cut_interpreter_is_not_even_asked_what_it_heard(salon):
    """Ingestion stops rather than being discarded downstream. Transcription costs money,
    and a participant who has been cut should not go on paying for it."""
    await _join(salon, MARIE)
    await _join(salon, HANS)
    salon.interpreter_of(HANS.id).queue("Guten Tag", language="de")

    await salon.mute(HANS.id, by=MARIE.id)
    recorded = await salon.collect()

    assert recorded == ()
    assert salon.interpreter_of(HANS.id).heard == [("Guten Tag", "de")]


# ── Still listening ───────────────────────────────────────────────────────────


async def test_a_cut_participant_still_hears_everybody(salon):
    """The acceptance criterion, and the whole difference between this and removing them:
    they are still in the conversation, they just cannot be heard in it."""
    await _join(salon, MARIE)
    await _join(salon, HANS)
    await salon.mute(HANS.id, by=MARIE.id)

    await salon.ingest(MARIE.id, "Bonjour", language="fr")
    await salon.deliver_all()

    tours = [line.text for line in salon.interpreter_of(HANS.id).spoken if line.kind == "tour"]
    assert tours == ["Bonjour"]


async def test_a_cut_participant_keeps_their_place_in_the_journal(salon):
    await _join(salon, MARIE)
    await _join(salon, HANS)
    await salon.mute(HANS.id, by=MARIE.id)

    await salon.ingest(MARIE.id, "Bonjour", language="fr")

    assert len(salon.pending_for(HANS.id)) == 1


async def test_a_cut_participant_is_still_in_the_salon(salon):
    await _join(salon, MARIE)
    await _join(salon, HANS)

    await salon.mute(HANS.id, by=MARIE.id)

    assert HANS.id in salon.participants
    assert (await salon.room_of(HANS.id)).closed is False


# ── Restoring ─────────────────────────────────────────────────────────────────


async def test_restoring_lets_them_be_heard_again(salon):
    await _join(salon, MARIE)
    await _join(salon, HANS)
    await salon.mute(HANS.id, by=MARIE.id)

    await salon.unmute(HANS.id, by=MARIE.id)

    assert salon.muted == ()
    assert len(await salon.ingest(HANS.id, "Guten Tag", language="de")) == 1


async def test_restoring_is_said_out_loud_too(salon):
    """Somebody who has been silent for a minute needs to know they are back before they
    try — otherwise the first thing they say is lost to a test of the microphone."""
    await _join(salon, MARIE)
    await _join(salon, HANS)
    await salon.mute(HANS.id, by=MARIE.id)

    await salon.unmute(HANS.id, by=MARIE.id)

    assert len(_annonces(salon, HANS.id)) == 2


async def test_restoring_a_microphone_nobody_cut_says_nothing(salon):
    await _join(salon, MARIE)
    await _join(salon, HANS)

    await salon.unmute(HANS.id, by=MARIE.id)

    assert _annonces(salon, HANS.id) == []


async def test_what_they_say_next_takes_the_next_position_and_no_other(salon):
    """The acceptance criterion in one line: no priority. Somebody who spoke while the
    microphone was down is ahead of them, and stays ahead."""
    await _join(salon, MARIE)
    await _join(salon, HANS)
    await salon.mute(HANS.id, by=MARIE.id)

    await salon.ingest(MARIE.id, "pendant", language="fr")
    await salon.unmute(HANS.id, by=MARIE.id)
    (back,) = await salon.ingest(HANS.id, "wieder da", language="de")

    assert [entry.text for entry in salon.log.entries] == ["pendant", "wieder da"]
    assert back.sequence == 2


async def test_a_restored_participant_is_heard_by_the_others(salon):
    await _join(salon, MARIE)
    await _join(salon, HANS)
    await salon.mute(HANS.id, by=MARIE.id)
    await salon.unmute(HANS.id, by=MARIE.id)

    await salon.ingest(HANS.id, "wieder da", language="de")
    await salon.deliver(MARIE.id)

    tours = [line.text for line in salon.interpreter_of(MARIE.id).spoken if line.kind == "tour"]
    assert tours == ["wieder da"]


# ── Who may do it ─────────────────────────────────────────────────────────────


async def test_only_the_host_may_cut_a_microphone(salon):
    """A participant who could silence another participant is a different product."""
    await _join(salon, MARIE)
    await _join(salon, HANS)
    await _join(salon, RHYS)

    with pytest.raises(NotTheHost):
        await salon.mute(RHYS.id, by=HANS.id)

    assert salon.muted == ()
    assert _annonces(salon, RHYS.id) == []


async def test_only_the_host_may_restore_one(salon):
    """Otherwise the cut is not a cut — whoever it was applied to could lift it."""
    await _join(salon, MARIE)
    await _join(salon, HANS)
    await salon.mute(HANS.id, by=MARIE.id)

    with pytest.raises(NotTheHost):
        await salon.unmute(HANS.id, by=HANS.id)

    assert salon.muted == ("hans",)


async def test_a_salon_with_no_host_lets_nobody_cut_anybody(salon):
    """A Salon whose host has left is not a free-for-all."""
    log = SalonLog(salon_id="salon-2", store=InMemoryJournalStore(), translate=translate)
    hostless = Salon(log=log, rooms=InMemoryRoomProvisioner())
    await hostless.join(HANS, InterpreteFake(participant=HANS))

    with pytest.raises(NotTheHost):
        await hostless.mute(HANS.id, by=MARIE.id)


async def test_the_host_cutting_their_own_microphone_is_allowed(salon):
    """Not a special case worth code: a host who wants to stop being heard is entitled to,
    and they are the one person who can lift it again."""
    await _join(salon, MARIE)

    await salon.mute(MARIE.id, by=MARIE.id)

    assert salon.muted == ("marie",)


# ── Edges ─────────────────────────────────────────────────────────────────────


async def test_cutting_somebody_who_is_not_here_does_nothing(salon):
    await _join(salon, MARIE)

    await salon.mute("nobody", by=MARIE.id)

    assert salon.muted == ()


async def test_leaving_takes_the_cut_with_it(salon):
    """A participant who was cut and then left, and later rejoins, comes back able to
    speak. The cut applied to a conversation they are no longer in."""
    await _join(salon, MARIE)
    await _join(salon, HANS)
    await salon.mute(HANS.id, by=MARIE.id)

    await salon.leave(HANS.id)
    await _join(salon, HANS)

    assert salon.muted == ()
    assert len(await salon.ingest(HANS.id, "Guten Tag", language="de")) == 1


async def test_the_notice_waits_for_the_end_of_an_intervention(salon):
    """Story 6.5's rule holds for this announcement like any other: not into the seam
    between two halves of somebody's sentence."""
    log = SalonLog(salon_id="salon-3", store=InMemoryJournalStore(), translate=translate)
    tight = Salon(
        log=log,
        rooms=InMemoryRoomProvisioner(),
        host_id=MARIE.id,
        max_message_characters=30,
    )
    await tight.join(MARIE, InterpreteFake(participant=MARIE))
    await tight.join(HANS, InterpreteFake(participant=HANS))
    pieces = await tight.ingest(MARIE.id, "Une phrase. Une deuxième. Une troisième.", language="fr")
    assert len(pieces) > 1

    await tight.deliver_upto(HANS.id, pieces[0].sequence)
    await tight.mute(HANS.id, by=MARIE.id)

    # Marie's introduction, then her first piece — and the microphone notice held back
    # behind the rest of the run rather than dropped into the seam.
    assert [line.kind for line in tight.interpreter_of(HANS.id).spoken] == ["annonce", "tour"]


async def test_a_cut_participant_whose_interpreter_is_down_is_still_cut(salon):
    """The notice is a courtesy; the cut is not. A provider that cannot say it must not
    leave the microphone open."""
    await _join(salon, MARIE)
    await _join(salon, HANS)
    salon.interpreter_of(HANS.id).fail_with = ConnectionError("model gone")

    await salon.mute(HANS.id, by=MARIE.id)

    assert salon.muted == ("hans",)
    assert await salon.ingest(HANS.id, "Guten Tag", language="de") == ()
