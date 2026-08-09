"""The monologue ceiling: how long one person may hold the floor uninterrupted (FR56).

Story 6.5 established that nothing third-party is spoken inside somebody's intervention. A
long intervention is cut into consecutive messages, and slipping an announcement between two
of them would cut a thought in half — the listener hears half a sentence, an unrelated
notice, then the other half, and has to reassemble it themselves.

That rule is right and it has a limit. Held indefinitely, it becomes the mechanism by which
one person makes everybody else unreachable: nothing can be said to anybody for as long as
they keep talking. So past `monologue_ceiling_seconds` the protection is withdrawn and
insertion is allowed inside the run.

Which is a choice between two costs, and the ceiling is where they cross. Under it, cutting
a thought costs more than a delayed announcement. Over it, the delay has become a silence
imposed on everybody by one speaker, and a clipped sentence costs less than that.
"""
import pytest

from src.interprete import Annonce, InterpreteFake, Participant
from src.journal import CHARACTERS_PER_SECOND, InMemoryJournalStore, SalonLog
from src.salon import InMemoryRoomProvisioner, Salon
from src.settings import DEFAULTS, SalonSettings

MARIE = Participant(id="marie", language="fr", name="Marie")
HANS = Participant(id="hans", language="de", name="Hans")

CEILING = 300.0
# One piece of a cut intervention, small enough that several fit under the ceiling.
PIECE_CHARACTERS = 500


# Distinct words of more than three letters. Repeating a short one would be collapsed by
# the stammer rule from Story 6.11 before it ever reached the splitter, and the intervention
# would arrive as a single message with nothing to insert inside.
_WORDS = (
    "alors", "parce", "quand", "toute", "chose", "avant", "depuis", "encore", "pendant",
    "surtout", "ensuite", "presque", "toujours", "souvent", "certain", "plutot", "vraiment",
)


def long_text(seconds: float) -> str:
    """An intervention of the given length, in words the cleaner will not eat."""
    needed = int(seconds * CHARACTERS_PER_SECOND)
    out: list[str] = []
    length = 0
    index = 0
    while length < needed:
        word = _WORDS[index % len(_WORDS)]
        index += 1
        # A sentence boundary every so often, so the splitter has somewhere to cut.
        piece = word + ("." if index % 12 == 0 else "")
        out.append(piece)
        length += len(piece) + 1
    return " ".join(out) + "."


async def translate(text, *, source, target):
    return f"{text} [{target}]"


@pytest.fixture
def salon():
    log = SalonLog(salon_id="salon-1", store=InMemoryJournalStore(), translate=translate)
    return Salon(
        log=log,
        rooms=InMemoryRoomProvisioner(),
        # Out of the way: this story is about the run, not about the lag.
        condensation_threshold_seconds=100_000.0,
        saturation_threshold_seconds=100_000.0,
        unblock_threshold_seconds=99_000.0,
        monologue_ceiling_seconds=CEILING,
        max_message_characters=PIECE_CHARACTERS,
    )


async def _join(salon, participant):
    return await salon.join(participant, InterpreteFake(participant=participant))


def _kinds(salon, participant_id):
    return [line.kind for line in salon.interpreter_of(participant_id).spoken]


ARRIVAL = "Sofia est arrivée"


def _heard_the_arrival(salon, participant_id) -> bool:
    """Whether the inserted announcement specifically has been said.

    By text and not by kind: introductions (Story 6.9) are announcements too, and one is
    spoken before the first message of anybody new. Checking for `kind == "annonce"` would
    match that instead and pass whatever this code did.
    """
    return any(ARRIVAL in line.text for line in salon.interpreter_of(participant_id).spoken)


async def _announce_arrival(salon, participant_id):
    await salon.announce(participant_id, Annonce(text=ARRIVAL, language="de"))


async def _speak_for(salon, seconds):
    """One intervention of the given length, cut into consecutive messages."""
    return await salon.ingest(MARIE.id, long_text(seconds), language="fr")


# ── Under the ceiling, a thought is not cut ───────────────────────────────────


async def test_a_short_intervention_is_cut_into_several_messages(salon):
    """The premise of the whole story. Without a run there is nothing to insert inside."""
    recorded = await _speak_for(salon, 60)

    assert len(recorded) > 1


async def test_nothing_is_inserted_inside_a_short_intervention(salon):
    """Story 6.5, unchanged. Half a sentence, an unrelated notice, then the other half is a
    thought the listener has to reassemble themselves."""
    await _join(salon, MARIE)
    await _join(salon, HANS)
    await _speak_for(salon, 60)
    await salon.deliver_upto(HANS.id, salon.log.head - 1)

    await _announce_arrival(salon, HANS.id)

    assert _heard_the_arrival(salon, HANS.id) is False


async def test_it_is_said_once_the_intervention_finishes(salon):
    """Held, not dropped. The announcement still arrives — it waits for a seam."""
    await _join(salon, MARIE)
    await _join(salon, HANS)
    await _speak_for(salon, 60)
    await salon.deliver_upto(HANS.id, salon.log.head - 1)
    await _announce_arrival(salon, HANS.id)

    await salon.deliver(HANS.id)

    assert _heard_the_arrival(salon, HANS.id) is True


# ── Over the ceiling, the protection is withdrawn ─────────────────────────────


async def test_an_insertion_is_allowed_inside_a_long_monologue(salon):
    """Held indefinitely, the mid-run rule becomes the mechanism by which one person makes
    everybody else unreachable."""
    await _join(salon, MARIE)
    await _join(salon, HANS)
    await _speak_for(salon, CEILING + 120)
    await salon.deliver_upto(HANS.id, salon.log.head - 1)

    await _announce_arrival(salon, HANS.id)

    assert _heard_the_arrival(salon, HANS.id) is True


async def test_the_insertion_lands_inside_the_run_rather_than_after_it(salon):
    """If it were only said at the end it would be the old behaviour with extra steps."""
    await _join(salon, MARIE)
    await _join(salon, HANS)
    await _speak_for(salon, CEILING + 120)
    await salon.deliver_upto(HANS.id, salon.log.head - 1)

    await _announce_arrival(salon, HANS.id)
    await salon.deliver(HANS.id)

    # The announcement is followed by more of the same intervention, which is what "inside"
    # means: said at the end it would be the old behaviour with extra steps.
    spoken = salon.interpreter_of(HANS.id).spoken
    at = next(i for i, line in enumerate(spoken) if ARRIVAL in line.text)
    assert [line.kind for line in spoken[at:]].count("tour") > 0


async def test_the_monologue_continues_afterwards(salon):
    """An insertion interrupts the intervention; it does not end it. What is left of what
    they said still reaches the listener."""
    await _join(salon, MARIE)
    await _join(salon, HANS)
    recorded = await _speak_for(salon, CEILING + 120)
    await salon.deliver_upto(HANS.id, salon.log.head - 1)
    await _announce_arrival(salon, HANS.id)

    await salon.deliver(HANS.id)

    tours = [line for line in salon.interpreter_of(HANS.id).spoken if line.kind == "tour"]
    assert len(tours) == len(recorded)


async def test_the_ceiling_is_measured_in_content_not_in_messages(salon):
    """Many short pieces and one long one are the same amount of somebody talking. Counting
    messages would make the ceiling depend on where the splitter happened to cut."""
    await _join(salon, MARIE)
    await _join(salon, HANS)
    await _speak_for(salon, CEILING - 120)
    await salon.deliver_upto(HANS.id, salon.log.head - 1)

    await _announce_arrival(salon, HANS.id)

    assert _heard_the_arrival(salon, HANS.id) is False


async def test_a_new_intervention_starts_the_count_again(salon):
    """The ceiling is on one continuous run. Somebody who said a great deal, stopped, and
    started again has yielded the floor in between — and the protection is theirs again."""
    await _join(salon, MARIE)
    await _join(salon, HANS)
    await _speak_for(salon, CEILING + 120)
    await salon.deliver(HANS.id)

    await _speak_for(salon, 60)
    await salon.deliver_upto(HANS.id, salon.log.head - 1)
    await _announce_arrival(salon, HANS.id)

    assert _heard_the_arrival(salon, HANS.id) is False


# ── The setting is its own ────────────────────────────────────────────────────


def test_it_starts_at_the_same_value_as_saturation():
    settings = SalonSettings()

    assert settings.monologue_ceiling_seconds == 300.0
    assert settings.monologue_ceiling_seconds == settings.saturation_threshold_seconds


def test_it_is_published_with_the_rest():
    assert DEFAULTS["monologue_ceiling_seconds"] == 300.0


def test_the_two_move_independently():
    """Sharing a starting value is a coincidence of judgement, not a relationship. They
    answer different questions — how long one person may hold the floor, and how far behind
    a room may fall — and tying them together would make one untunable."""
    settings = SalonSettings(monologue_ceiling_seconds=600.0)

    assert settings.saturation_threshold_seconds == 300.0


def test_the_other_moves_independently_too():
    settings = SalonSettings(
        saturation_threshold_seconds=900.0, unblock_threshold_seconds=800.0
    )

    assert settings.monologue_ceiling_seconds == 300.0


def test_there_is_no_ordering_rule_between_them():
    """Unlike condensation and saturation, neither of these silently disables the other, so
    inventing a rule between them would refuse configurations that work perfectly well."""
    settings = SalonSettings(monologue_ceiling_seconds=1200.0)

    assert settings.monologue_ceiling_seconds == 1200.0


async def test_the_salon_takes_it_from_the_settings():
    log = SalonLog(salon_id="s", store=InMemoryJournalStore(), translate=translate)
    salon = Salon(log=log, rooms=InMemoryRoomProvisioner())

    assert salon.monologue_ceiling_seconds == 300.0
