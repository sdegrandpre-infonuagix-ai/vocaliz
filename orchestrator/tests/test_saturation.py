"""Saturation: a room that cannot keep up says so, and stops taking words (FR55).

The alarm, not the first resort. Condensation (Story 7.2) runs continuously and by room; if a
room saturates *despite* it, what that means is that this room's regulation has run out — the
lag survived being summarised. That ordering is enforced in `SalonSettings`, where
`condensation_threshold_seconds` must sit strictly below `saturation_threshold_seconds`, and
it is why this signal is worth listening to when it arrives.

Everything here is a state of one room and never of the Salon. One participant's interpreter
falling five minutes behind says nothing about anybody else's, so a Salon is expected to run
in a mixed state — one room blocked, the others entirely unaffected. Two thresholds rather
than one, for the reason driving mode has two: unblocking at the blocking point is a system
that flaps.

What blocking stops is *ingestion*. A blocked participant keeps hearing everybody, which
matters — they are behind, so cutting delivery would be taking away the thing they are
short of.
"""
import pytest

from src.interprete import InterpreteFake, Participant, ProviderUnavailable
from src.journal import CHARACTERS_PER_SECOND, InMemoryJournalStore, SalonLog
from src.salon import InMemoryRoomProvisioner, Salon
from src.salon.notices import vocaliz_is_busy

MARIE = Participant(id="marie", language="fr", name="Marie")
HANS = Participant(id="hans", language="de", name="Hans")
SOFIA = Participant(id="sofia", language="es", name="Sofia")

SATURATION = 300.0
UNBLOCK = 240.0
# Above saturation, so condensation never fires and the lag is purely a saturation story.
CONDENSATION = 10_000.0


def long_text(seconds: float) -> str:
    return "a" * int(seconds * CHARACTERS_PER_SECOND)


async def translate(text, *, source, target):
    return f"{text} [{target}]"


@pytest.fixture
def salon():
    log = SalonLog(salon_id="salon-1", store=InMemoryJournalStore(), translate=translate)
    return Salon(
        log=log,
        rooms=InMemoryRoomProvisioner(),
        condensation_threshold_seconds=CONDENSATION,
        saturation_threshold_seconds=SATURATION,
        unblock_threshold_seconds=UNBLOCK,
        max_message_characters=100_000,
    )


async def _join(salon, participant):
    return await salon.join(participant, InterpreteFake(participant=participant))


def _spoken(salon, participant_id):
    return salon.interpreter_of(participant_id).spoken


def _busy_signals(salon, participant_id):
    return [line for line in _spoken(salon, participant_id) if "Vocaliz is busy" in line.text]


async def _push_over(salon, speaker, seconds=SATURATION + 30):
    await salon.ingest(speaker.id, long_text(seconds), language=speaker.language)


# ── The signal ────────────────────────────────────────────────────────────────


async def test_a_lag_over_the_threshold_saturates_the_room(salon):
    await _join(salon, MARIE)
    await _join(salon, HANS)

    await _push_over(salon, MARIE)

    assert salon.is_saturated(HANS.id) is True


async def test_the_participant_is_told(salon):
    await _join(salon, MARIE)
    await _join(salon, HANS)

    await _push_over(salon, MARIE)

    assert _busy_signals(salon, HANS.id) != []


async def test_the_brand_stays_in_english(salon):
    """"Vocaliz is busy" is the product saying its own name. Translating a brand into six
    languages gives somebody six things to search for when they want to report it."""
    for language in ("fr", "en", "es", "de", "pt", "it"):
        assert "Vocaliz is busy" in vocaliz_is_busy(told_in=language)


async def test_the_rest_of_the_sentence_is_in_their_language(salon):
    """The brand is not the message. Somebody who reads only German has been told nothing at
    all by three English words."""
    assert vocaliz_is_busy(told_in="de") != vocaliz_is_busy(told_in="fr")
    assert vocaliz_is_busy(told_in="de").replace("Vocaliz is busy", "").strip() != ""


def test_an_unknown_language_still_gets_the_signal():
    assert "Vocaliz is busy" in vocaliz_is_busy(told_in="cy")


async def test_the_signal_is_spoken_in_the_participants_language(salon):
    await _join(salon, MARIE)
    await _join(salon, HANS)

    await _push_over(salon, MARIE)

    assert _busy_signals(salon, HANS.id)[0].language == "de"


async def test_the_threshold_itself_is_not_over_it(salon):
    await _join(salon, MARIE)
    await _join(salon, HANS)

    await salon.ingest(MARIE.id, long_text(SATURATION), language="fr")

    assert salon.is_saturated(HANS.id) is False


async def test_it_is_said_once_rather_than_on_every_message(salon):
    """Crossing the threshold is the event. Repeating the alarm for each message afterwards
    would bury the conversation the participant is already struggling to follow."""
    await _join(salon, MARIE)
    await _join(salon, HANS)
    await _push_over(salon, MARIE)

    await salon.ingest(MARIE.id, long_text(60), language="fr")

    assert len(_busy_signals(salon, HANS.id)) == 1


# ── A state of one room, never of the Salon ───────────────────────────────────


async def _mixed_state(salon):
    """Hans falls behind while Sofia keeps up, which is the only honest way to test this.

    Two participants sitting through the same enormous message are both behind, and warning
    both of them would be correct rather than a bug. A real mixed state needs one room that
    has been keeping up — so Sofia delivers in between and Hans does not.
    """
    await _join(salon, MARIE)
    await _join(salon, HANS)
    await _join(salon, SOFIA)

    await salon.ingest(MARIE.id, long_text(200), language="fr")
    await salon.deliver(SOFIA.id)
    await salon.ingest(MARIE.id, long_text(150), language="fr")


async def test_nobody_else_is_warned(salon):
    await _mixed_state(salon)

    assert _busy_signals(salon, SOFIA.id) == []
    assert _busy_signals(salon, HANS.id) != []


async def test_a_salon_runs_in_a_mixed_state(salon):
    """One room saturated and the others not is the expected condition, not a degraded one."""
    await _mixed_state(salon)

    assert salon.is_saturated(HANS.id) is True
    assert salon.is_saturated(SOFIA.id) is False


async def test_the_speaker_does_not_saturate_themselves(salon):
    """They are behind by exactly what they just said, and they already know what it was."""
    await _join(salon, MARIE)
    await _join(salon, HANS)

    await _push_over(salon, MARIE)

    assert salon.is_saturated(MARIE.id) is False


# ── What blocking stops, and what it does not ─────────────────────────────────


async def test_a_blocked_participant_adds_nothing_to_the_journal(salon):
    await _join(salon, MARIE)
    await _join(salon, HANS)
    await _push_over(salon, MARIE)
    before = salon.log.entries

    recorded = await salon.ingest(HANS.id, "Ich rede trotzdem", language="de")

    assert recorded == ()
    assert salon.log.entries == before


async def test_a_blocked_participant_is_told_immediately_rather_than_left_talking(salon):
    """The whole point. Silently dropping what somebody says leaves them speaking into
    nothing and finding out much later, if at all."""
    await _join(salon, MARIE)
    await _join(salon, HANS)
    await _push_over(salon, MARIE)

    await salon.ingest(HANS.id, "Ich rede trotzdem", language="de")

    assert len(_busy_signals(salon, HANS.id)) == 2


async def test_the_others_keep_adding_to_the_journal_normally(salon):
    await _mixed_state(salon)

    recorded = await salon.ingest(SOFIA.id, "Sigo hablando", language="es")

    assert [entry.text for entry in recorded] == ["Sigo hablando"]
    assert salon.is_saturated(HANS.id) is True


async def test_a_blocked_participant_still_receives_everything(salon):
    """They are behind, so cutting delivery would take away the very thing they are short
    of. Blocking is about what goes in, never about what comes out."""
    await _join(salon, MARIE)
    await _join(salon, HANS)
    await _push_over(salon, MARIE)

    await salon.deliver_all()

    assert [line.text for line in _spoken(salon, HANS.id) if line.kind == "tour"] != []


# ── A thought is never cut in half ────────────────────────────────────────────


async def test_an_intervention_that_causes_the_saturation_is_still_recorded_whole(salon):
    """An intervention is cut into consecutive messages (Story 6.6) and lands in one go. One
    long enough to saturate the room must not have its tail refused by the block it caused —
    that would cut a sentence out of the middle of somebody's thought."""
    await _join(salon, MARIE)
    await _join(salon, HANS)
    salon_max = 500

    recorded = await salon.log.record_intervention(
        participant_id=MARIE.id,
        text=long_text(SATURATION + 60),
        language="fr",
        max_characters=salon_max,
    )

    assert len(recorded) > 1
    assert "".join(entry.text for entry in recorded).replace(" ", "") == long_text(
        SATURATION + 60
    ).replace(" ", "")


async def test_blocking_is_decided_per_intervention_not_per_piece(salon):
    """The decision is taken once, before the intervention starts. A block that fell due
    between two pieces of one sentence would be the same as cutting the sentence."""
    await _join(salon, MARIE)
    await _join(salon, HANS)

    recorded = await salon.ingest(MARIE.id, long_text(SATURATION + 60), language="fr")

    assert len(recorded) >= 1
    assert salon.is_saturated(MARIE.id) is False


# ── Coming back ───────────────────────────────────────────────────────────────


async def test_the_room_is_reopened_once_the_lag_is_down(salon):
    await _join(salon, MARIE)
    await _join(salon, HANS)
    await _push_over(salon, MARIE)

    await salon.deliver(HANS.id)

    assert salon.is_saturated(HANS.id) is False


async def test_and_the_participant_can_speak_again(salon):
    await _join(salon, MARIE)
    await _join(salon, HANS)
    await _push_over(salon, MARIE)
    await salon.deliver(HANS.id)

    recorded = await salon.ingest(HANS.id, "Jetzt wieder", language="de")

    assert [entry.text for entry in recorded] == ["Jetzt wieder"]


async def test_it_does_not_reopen_between_the_two_thresholds(salon):
    """The whole reason there are two numbers. Reopening the moment the lag dips below the
    blocking point would put the room straight back over it, several times a second."""
    await _join(salon, MARIE)
    await _join(salon, HANS)
    await _push_over(salon, MARIE)

    # Down to between the two thresholds: below saturation, still above unblocking.
    await salon.deliver_upto(HANS.id, salon.log.head - 1)
    await salon.ingest(MARIE.id, long_text(UNBLOCK + 30), language="fr")

    assert salon.is_saturated(HANS.id) is True


async def test_reopening_is_not_announced(salon):
    """Being able to speak again is discovered by speaking. An announcement for it would
    interrupt the conversation to report that nothing is wrong."""
    await _join(salon, MARIE)
    await _join(salon, HANS)
    await _push_over(salon, MARIE)

    await salon.deliver(HANS.id)

    assert len(_busy_signals(salon, HANS.id)) == 1


async def test_saturating_a_second_time_is_signalled_again(salon):
    """It is said once per crossing, not once per Salon: the second time is news again."""
    await _join(salon, MARIE)
    await _join(salon, HANS)
    await _push_over(salon, MARIE)
    await salon.deliver(HANS.id)

    await _push_over(salon, MARIE)

    assert len(_busy_signals(salon, HANS.id)) == 2


# ── Leaving, and the settings ─────────────────────────────────────────────────


async def test_the_thresholds_come_from_the_settings():
    """Story 7.1 holds them, and their ordering rule is what makes this signal meaningful:
    condensation must have been tried and failed before the alarm can sound."""
    log = SalonLog(salon_id="s", store=InMemoryJournalStore(), translate=translate)
    salon = Salon(log=log, rooms=InMemoryRoomProvisioner())

    assert salon.saturation_threshold_seconds == 300.0
    assert salon.unblock_threshold_seconds == 240.0


async def test_somebody_who_is_not_here_is_not_saturated(salon):
    assert salon.is_saturated("nobody") is False


async def test_leaving_while_blocked_is_ordinary(salon):
    await _join(salon, MARIE)
    await _join(salon, HANS)
    await _push_over(salon, MARIE)

    await salon.leave(HANS.id)

    assert salon.is_saturated(HANS.id) is False


async def test_a_room_that_cannot_hear_the_alarm_is_blocked_all_the_same(salon):
    """The block is about the lag, not about whether the sentence was delivered.

    An adapter that is down has already told the participant so out loud (NFR3). Leaving
    the room open because the alarm could not be spoken would let somebody keep talking
    into a room that is provably not keeping up — the worst of both.
    """

    class Mute(InterpreteFake):
        async def insert_annonce(self, annonce):
            raise ProviderUnavailable(HANS.id, "adapter down")

    await _join(salon, MARIE)
    await salon.join(HANS, Mute(participant=HANS))

    await _push_over(salon, MARIE)

    assert salon.is_saturated(HANS.id) is True
