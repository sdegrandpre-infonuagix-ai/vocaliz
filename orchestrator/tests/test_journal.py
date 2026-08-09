"""The journal of a Salon, and the reading position of each interpreter in it.

The journal is the only structure of messages there is. Not a queue — a message is rendered
once per participant, at a rhythm each interpreter sets for itself, so there is no moment
at which it has been "consumed" and could be dropped. Everything else here follows from
that: entries are appended and never touched again, and what moves is the positions.
"""
from datetime import datetime, timedelta, timezone

import pytest

from src.journal import Cursors, Journal, JournalEntry

T0 = datetime(2026, 8, 8, 12, 0, 0, tzinfo=timezone.utc)


def _clock(start=T0, step_seconds=1):
    """Arrival times that advance on their own, so tests never depend on a real clock."""
    ticks = iter(range(1000))

    def now():
        return start + timedelta(seconds=next(ticks) * step_seconds)

    return now


@pytest.fixture
def journal():
    return Journal(salon_id="salon-1", now=_clock())


# ── Appending ─────────────────────────────────────────────────────────────────


def test_a_new_journal_is_empty(journal):
    assert journal.entries == ()
    assert journal.head == 0


def test_a_message_is_kept_in_the_language_it_was_spoken_in(journal):
    entry = journal.append(participant_id="hans", text="Guten Morgen", language="de")

    assert entry.text == "Guten Morgen"
    assert entry.language == "de"
    assert entry.participant_id == "hans"


def test_a_message_is_stamped_when_it_arrives(journal):
    """The arrival at the orchestrator is the instant of record — Story 6.6 makes it what
    settles the order of two messages that were spoken at the same moment."""
    entry = journal.append(participant_id="hans", text="Guten Morgen", language="de")

    assert entry.arrived_at == T0


def test_sequences_are_monotonic_from_one(journal):
    first = journal.append(participant_id="hans", text="eins", language="de")
    second = journal.append(participant_id="marie", text="deux", language="fr")

    assert (first.sequence, second.sequence) == (1, 2)
    assert journal.head == 2


def test_the_order_of_the_journal_is_the_order_of_arrival(journal):
    journal.append(participant_id="hans", text="eins", language="de")
    journal.append(participant_id="marie", text="deux", language="fr")
    journal.append(participant_id="hans", text="drei", language="de")

    assert [entry.text for entry in journal.entries] == ["eins", "deux", "drei"]


def test_an_entry_cannot_be_altered_after_the_fact(journal):
    """The speaker makes the original. Nothing downstream — no translation, no cleaning,
    no summary — is allowed to write over what somebody actually said."""
    entry = journal.append(participant_id="hans", text="Guten Morgen", language="de")

    with pytest.raises(Exception):
        entry.text = "something else"


def test_reading_the_journal_does_not_empty_it(journal):
    """The thing that makes this a journal and not a queue: three participants read the
    same message three times, at three different rhythms."""
    journal.append(participant_id="hans", text="eins", language="de")

    assert journal.after(0) == journal.after(0)
    assert len(journal.entries) == 1


def test_an_empty_message_is_not_a_turn(journal):
    """Silence detected as speech, or a cleaning pass (Story 6.11) that removed everything
    there was. Either way there is nothing to render to anybody."""
    assert journal.append(participant_id="hans", text="   ", language="de") is None
    assert journal.entries == ()
    assert journal.head == 0


# ── Reading from a position ───────────────────────────────────────────────────


def test_after_returns_what_a_position_has_not_seen(journal):
    journal.append(participant_id="hans", text="eins", language="de")
    journal.append(participant_id="hans", text="zwei", language="de")
    journal.append(participant_id="hans", text="drei", language="de")

    assert [entry.text for entry in journal.after(1)] == ["zwei", "drei"]


def test_a_position_at_the_head_has_nothing_left_to_read(journal):
    journal.append(participant_id="hans", text="eins", language="de")

    assert journal.after(1) == ()


def test_a_position_at_zero_reads_the_whole_journal(journal):
    """Story 6.10 places a late arrival's position at zero to give them the history — no
    special mechanism, the ordinary rules do the rest."""
    journal.append(participant_id="hans", text="eins", language="de")
    journal.append(participant_id="hans", text="zwei", language="de")

    assert len(journal.after(0)) == 2


# ── Content, measured in seconds ──────────────────────────────────────────────


def test_an_entry_carries_how_long_it_takes_to_say():
    """Lag is expressed in seconds of content, so every entry has to know its own."""
    entry = JournalEntry(
        sequence=1,
        participant_id="hans",
        text="a" * 30,
        language="de",
        arrived_at=T0,
        duration_seconds=2.0,
    )

    assert entry.duration_seconds == 2.0


def test_a_duration_is_estimated_from_the_text_when_nobody_supplies_one(journal):
    """An interpreter that knows how long its human actually spoke should say so. When it
    does not, the length of what was said is the best available stand-in — and it is
    consistent, which is what matters for comparing one interpreter's lag to another's."""
    short = journal.append(participant_id="hans", text="Ja", language="de")
    long = journal.append(participant_id="hans", text="Ja, " * 50, language="de")

    assert 0 < short.duration_seconds < long.duration_seconds


def test_a_supplied_duration_is_kept_as_given(journal):
    entry = journal.append(
        participant_id="hans", text="Guten Morgen", language="de", duration_seconds=4.5
    )

    assert entry.duration_seconds == 4.5


# ── Cursors ───────────────────────────────────────────────────────────────────


def test_every_interpreter_starts_at_the_head_by_default(journal):
    """Somebody joining a Salon in progress hears what is said from now on. Story 6.10 is
    where the host may decide otherwise."""
    journal.append(participant_id="hans", text="eins", language="de")
    cursors = Cursors()

    assert cursors.position_of("marie", default=journal.head) == 1


def test_each_interpreter_advances_its_own_position(journal):
    journal.append(participant_id="hans", text="eins", language="de")
    journal.append(participant_id="hans", text="zwei", language="de")
    cursors = Cursors({"marie": 0, "luc": 0})

    cursors.advance("marie", 2)

    assert cursors.position_of("marie") == 2
    assert cursors.position_of("luc") == 0


def test_a_position_never_goes_backwards(journal):
    """Rendering the same message twice is worse than rendering it late, and a late
    acknowledgement arriving out of order is the ordinary way it would happen."""
    cursors = Cursors({"marie": 5})

    cursors.advance("marie", 3)

    assert cursors.position_of("marie") == 5


def test_a_position_cannot_run_past_the_head(journal):
    journal.append(participant_id="hans", text="eins", language="de")
    cursors = Cursors({"marie": 0})

    with pytest.raises(ValueError):
        cursors.advance("marie", 9, head=journal.head)


def test_the_lag_of_an_interpreter_is_the_content_it_has_not_rendered(journal):
    journal.append(participant_id="hans", text="eins", language="de", duration_seconds=3.0)
    journal.append(participant_id="hans", text="zwei", language="de", duration_seconds=4.0)
    cursors = Cursors({"marie": 0, "luc": 1})

    assert journal.lag_seconds(cursors.position_of("marie")) == 7.0
    assert journal.lag_seconds(cursors.position_of("luc")) == 4.0


def test_an_interpreter_at_the_head_is_not_behind(journal):
    journal.append(participant_id="hans", text="eins", language="de", duration_seconds=3.0)

    assert journal.lag_seconds(journal.head) == 0.0


def test_lag_is_measured_on_what_is_in_the_journal(journal):
    """Story 6.11 cleans at ingestion rather than at rendering, so what is measured here is
    already the cleaned content — which is why cleaning reduces every room's lag at once."""
    journal.append(participant_id="hans", text="euh", language="de", duration_seconds=0.0)

    assert journal.lag_seconds(0) == 0.0


def test_a_cursor_collection_says_who_is_in_it():
    cursors = Cursors({"marie": 3})

    assert "marie" in cursors
    assert "luc" not in cursors


def test_a_cursor_collection_hands_back_a_copy_to_be_written_down():
    """What a checkpoint writes. A copy rather than the live mapping, so a store that holds
    on to it cannot be surprised by the next message."""
    cursors = Cursors({"marie": 3})

    snapshot = cursors.as_dict()
    cursors.advance("marie", 4)

    assert snapshot == {"marie": 3}


def test_the_content_of_a_span_of_the_journal(journal):
    """What Story 7.2 condenses: the interval between where a reader is and where it is
    catching up to, measured the same way its lag is."""
    journal.append(participant_id="hans", text="eins", language="de", duration_seconds=4.0)
    journal.append(participant_id="hans", text="zwei", language="de", duration_seconds=2.0)
    journal.append(participant_id="hans", text="drei", language="de", duration_seconds=1.0)

    assert journal.content_seconds_between(1, 3) == pytest.approx(3.0)
    assert journal.content_seconds_between(0, 3) == pytest.approx(7.0)
    assert journal.content_seconds_between(3, 3) == 0
