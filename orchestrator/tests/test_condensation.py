"""An interpreter that has fallen behind says the backlog in substance (FR53).

The lag is `head − cursor_i`, measured in seconds of *content* rather than of clock, and it
belongs to one interpreter. That is the whole reason this can exist at all: the journal is
not a queue, reading consumes nothing, and one participant's interpreter racing through a
summary changes nothing whatsoever for anybody else.

The part that is not obvious is the announcement. A summary delivered silently is
indistinguishable from the conversation having been quiet — the listener has no way of
knowing that four people spoke and they are now hearing the gist. Saying so is what turns a
lossy delivery into an honest one, and it is the difference between being caught up and
being quietly given less than everybody else.
"""
import pytest

from src.interprete import InterpreteFake, Participant
from src.journal import CHARACTERS_PER_SECOND, InMemoryJournalStore, SalonLog
from src.salon import InMemoryRoomProvisioner, Salon
from src.salon.notices import condensed_while_listening

MARIE = Participant(id="marie", language="fr", name="Marie")
HANS = Participant(id="hans", language="de", name="Hans")
SOFIA = Participant(id="sofia", language="es", name="Sofia")

# One threshold's worth of text, so a single message can put somebody far behind.
THRESHOLD = 120.0


def long_text(seconds: float) -> str:
    """Text that counts as `seconds` of content, so a lag can be built exactly."""
    return "a" * int(seconds * CHARACTERS_PER_SECOND)


async def translate(text, *, source, target):
    return f"{text} [{target}]"


@pytest.fixture
def salon():
    log = SalonLog(salon_id="salon-1", store=InMemoryJournalStore(), translate=translate)
    return Salon(
        log=log,
        rooms=InMemoryRoomProvisioner(),
        condensation_threshold_seconds=THRESHOLD,
        max_message_characters=100_000,
    )


async def _join(salon, participant):
    return await salon.join(participant, InterpreteFake(participant=participant))


def _kinds(salon, participant_id):
    return [line.kind for line in salon.interpreter_of(participant_id).spoken]


def _condensations(salon, participant_id):
    return [line for line in salon.interpreter_of(participant_id).spoken if line.kind == "condense"]


# ── When it fires ─────────────────────────────────────────────────────────────


async def test_a_lag_over_the_threshold_is_condensed(salon):
    await _join(salon, MARIE)
    await _join(salon, HANS)
    await salon.ingest(MARIE.id, long_text(THRESHOLD + 30), language="fr")

    await salon.deliver(HANS.id)

    assert _condensations(salon, HANS.id) != []


async def test_a_lag_under_the_threshold_is_rendered_in_full(salon):
    await _join(salon, MARIE)
    await _join(salon, HANS)
    await salon.ingest(MARIE.id, long_text(THRESHOLD - 30), language="fr")

    await salon.deliver(HANS.id)

    assert _condensations(salon, HANS.id) == []
    assert "tour" in _kinds(salon, HANS.id)


async def test_the_threshold_itself_is_not_over_it(salon):
    await _join(salon, MARIE)
    await _join(salon, HANS)
    await salon.ingest(MARIE.id, long_text(THRESHOLD), language="fr")

    await salon.deliver(HANS.id)

    assert _condensations(salon, HANS.id) == []


async def test_the_backlog_is_condensed_whole_rather_than_message_by_message(salon):
    """One summary of the interval, not a summary of each thing in it — otherwise the lag
    is unchanged and the listener has simply been given a worse version of everything."""
    await _join(salon, MARIE)
    await _join(salon, HANS)
    for _ in range(4):
        await salon.ingest(MARIE.id, long_text(40), language="fr")

    await salon.deliver(HANS.id)

    assert len(_condensations(salon, HANS.id)) == 1


# ── The cursor moves faster than real time ────────────────────────────────────


async def test_the_cursor_advances_to_the_end_of_what_was_summarised(salon):
    await _join(salon, MARIE)
    await _join(salon, HANS)
    await salon.ingest(MARIE.id, long_text(THRESHOLD + 30), language="fr")

    await salon.deliver(HANS.id)

    assert salon.pending_for(HANS.id) == ()


async def test_the_lag_is_gone_afterwards(salon):
    """The point of the mechanism, stated as the number it exists to move."""
    await _join(salon, MARIE)
    await _join(salon, HANS)
    await salon.ingest(MARIE.id, long_text(THRESHOLD + 30), language="fr")
    assert salon.log.lag_seconds(HANS.id) > THRESHOLD

    await salon.deliver(HANS.id)

    assert salon.log.lag_seconds(HANS.id) == 0


async def test_full_delivery_resumes_once_the_lag_is_down(salon):
    """Condensation is a state of the lag, not a mode the interpreter enters and stays in.
    Nothing has to switch it off — the next delivery simply weighs the threshold again."""
    await _join(salon, MARIE)
    await _join(salon, HANS)
    await salon.ingest(MARIE.id, long_text(THRESHOLD + 30), language="fr")
    await salon.deliver(HANS.id)

    await salon.ingest(MARIE.id, "Et voilà", language="fr")
    await salon.deliver(HANS.id)

    assert len(_condensations(salon, HANS.id)) == 1
    assert [line.text for line in salon.interpreter_of(HANS.id).spoken][-1] == "Et voilà"


# ── It is announced ───────────────────────────────────────────────────────────


async def test_the_listener_is_told_a_summary_is_coming(salon):
    """Otherwise a summary is indistinguishable from the conversation having been quiet, and
    the listener never learns they were given less than everybody else."""
    await _join(salon, MARIE)
    await _join(salon, HANS)
    await salon.ingest(MARIE.id, long_text(THRESHOLD + 30), language="fr")

    await salon.deliver(HANS.id)

    assert "annonce" in _kinds(salon, HANS.id)


async def test_the_announcement_comes_before_the_summary(salon):
    """After it, it would be an explanation of something the listener has already had to
    make sense of on their own."""
    await _join(salon, MARIE)
    await _join(salon, HANS)
    await salon.ingest(MARIE.id, long_text(THRESHOLD + 30), language="fr")

    await salon.deliver(HANS.id)

    kinds = _kinds(salon, HANS.id)
    assert kinds.index("annonce") < kinds.index("condense")


async def test_the_announcement_is_in_the_listeners_language(salon):
    await _join(salon, MARIE)
    await _join(salon, HANS)
    await salon.ingest(MARIE.id, long_text(THRESHOLD + 30), language="fr")

    await salon.deliver(HANS.id)

    announcement = [line for line in salon.interpreter_of(HANS.id).spoken if line.kind == "annonce"]
    assert announcement[0].language == "de"


async def test_the_announcement_says_how_many_people_spoke(salon):
    """"Three people said this, in substance" — the number is what tells the listener how
    much they are being given the gist of."""
    await _join(salon, MARIE)
    await _join(salon, HANS)
    await _join(salon, SOFIA)
    await salon.ingest(MARIE.id, long_text(80), language="fr")
    await salon.ingest(SOFIA.id, long_text(80), language="es")

    await salon.deliver(HANS.id)

    announcement = [line for line in salon.interpreter_of(HANS.id).spoken if line.kind == "annonce"]
    assert "2" in announcement[0].text


async def test_one_person_is_announced_as_one_person(salon):
    """A sentence that says "1 people" in any language is a sentence nobody wrote."""
    assert condensed_while_listening(1, told_in="en") != condensed_while_listening(2, told_in="en")
    assert "1" not in condensed_while_listening(1, told_in="en")


async def test_the_same_person_twice_is_still_one_person(salon):
    """The count is of people, not of messages: somebody who spoke four times is one person
    to be caught up on."""
    await _join(salon, MARIE)
    await _join(salon, HANS)
    for _ in range(4):
        await salon.ingest(MARIE.id, long_text(40), language="fr")

    await salon.deliver(HANS.id)

    announcement = [line for line in salon.interpreter_of(HANS.id).spoken if line.kind == "annonce"]
    assert "4" not in announcement[0].text


def test_an_unknown_language_still_gets_an_announcement():
    """A notice in the wrong language still says something happened. Silence says nothing."""
    assert condensed_while_listening(3, told_in="cy") != ""


def test_every_offered_language_has_the_sentence():
    for language in ("fr", "en", "es", "de", "pt", "it"):
        assert "3" in condensed_while_listening(3, told_in=language)


# ── Nobody else is touched ────────────────────────────────────────────────────


async def test_another_participants_cursor_is_untouched(salon):
    """Each interpreter condenses on its own account. The journal is not a queue, so one
    reader racing ahead through a summary takes nothing away from anybody."""
    await _join(salon, MARIE)
    await _join(salon, HANS)
    await _join(salon, SOFIA)
    await salon.ingest(MARIE.id, long_text(THRESHOLD + 30), language="fr")

    await salon.deliver(HANS.id)

    assert salon.pending_for(SOFIA.id) != ()
    assert salon.log.lag_seconds(SOFIA.id) > THRESHOLD


async def test_the_journal_itself_is_unchanged(salon):
    """A summary is something said to one person, never an edit to what was said."""
    await _join(salon, MARIE)
    await _join(salon, HANS)
    await salon.ingest(MARIE.id, long_text(THRESHOLD + 30), language="fr")
    before = salon.log.entries

    await salon.deliver(HANS.id)

    assert salon.log.entries == before


async def test_the_other_participant_still_hears_everything_in_full(salon):
    await _join(salon, MARIE)
    await _join(salon, HANS)
    await _join(salon, SOFIA)
    await salon.ingest(MARIE.id, long_text(THRESHOLD + 30), language="fr")

    await salon.deliver(HANS.id)
    await salon.deliver(SOFIA.id)

    assert _condensations(salon, SOFIA.id) != []
    # Sofia was equally far behind, so she is condensed too — on her own account, from her
    # own cursor, and only because of her own lag.
    assert salon.pending_for(SOFIA.id) == ()


async def test_the_speaker_is_never_condensed_about_their_own_words(salon):
    await _join(salon, MARIE)
    await _join(salon, HANS)
    await salon.ingest(MARIE.id, long_text(THRESHOLD + 30), language="fr")

    await salon.deliver(MARIE.id)

    assert _condensations(salon, MARIE.id) == []
