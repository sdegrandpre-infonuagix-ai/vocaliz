"""First arrived, first restituted — and nothing else deciding who speaks.

Most of this story was delivered by the journal of Story 6.3: positions are handed out
monotonically as messages arrive, so the order of the journal *is* the order of arrival and
there is no second structure to keep in step with it.

What is added here is the rule for the case the journal cannot settle on its own. Two
messages can arrive at the same instant — the clock has finite resolution, and the pieces of
one split intervention deliberately share a single timestamp. `arrival_key` states how that
tie is broken, so the answer is the same every time it is asked.

The other half of the story is a negative, and it is the more important one: nobody has to
ask for the floor, nobody is given it, and there is no code here that could.
"""
import inspect
from datetime import datetime, timedelta, timezone

import pytest

from src.interprete import InterpreteFake, Participant
from src.journal import InMemoryJournalStore, Journal, SalonLog, arrival_key
from src.salon import InMemoryRoomProvisioner, Salon

T0 = datetime(2026, 8, 8, 12, 0, 0, tzinfo=timezone.utc)

MARIE = Participant(id="marie", language="fr", name="Marie")
HANS = Participant(id="hans", language="de", name="Hans")
RHYS = Participant(id="rhys", language="cy", name="Rhys")


async def translate(text, *, source, target):
    return f"{text} [{target}]"


def _frozen_clock():
    """Every message arrives at the same instant — the case the tie-break is for."""
    return lambda: T0


def _ticking_clock(step_seconds=1):
    ticks = iter(range(1000))
    return lambda: T0 + timedelta(seconds=next(ticks) * step_seconds)


@pytest.fixture
def salon():
    log = SalonLog(
        salon_id="salon-1",
        store=InMemoryJournalStore(),
        translate=translate,
        now=_ticking_clock(),
    )
    return Salon(log=log, rooms=InMemoryRoomProvisioner())


def _turns(salon, participant_id):
    """What was said, without the introductions of Story 6.9 — which are said in front of
    a person's first message and are not themselves part of the conversation."""
    lines = salon.interpreter_of(participant_id).spoken
    return [line.text for line in lines if line.kind == "tour"]


async def _join(salon, participant, **kwargs):
    return await salon.join(participant, InterpreteFake(participant=participant), **kwargs)


# ── The order is the order of arrival ─────────────────────────────────────────


async def test_messages_are_restituted_in_the_order_they_arrived(salon):
    """Three people talking over each other, and everybody hears the same conversation in
    the same order — the journal's order, which is arrival order."""
    for participant in (MARIE, HANS, RHYS):
        await _join(salon, participant)

    await salon.ingest(MARIE.id, "un", language="fr")
    await salon.ingest(HANS.id, "zwei", language="de")
    await salon.ingest(RHYS.id, "tri", language="cy")
    await salon.deliver_all()

    for listener in (MARIE, HANS, RHYS):
        heard = [
            line.text
            for line in salon.interpreter_of(listener.id).spoken
            if line.kind == "tour"
        ]
        # Each listener is spared their own words, so the sequence they hear is the
        # conversation minus their contribution — in the order it arrived, either way.
        assert heard == [t for t in ["un", "zwei", "tri"] if t not in _own_words(listener)]


def _own_words(participant):
    return {"marie": {"un"}, "hans": {"zwei"}, "rhys": {"tri"}}[participant.id]


async def test_everybody_is_given_the_same_order(salon):
    for participant in (MARIE, HANS, RHYS):
        await _join(salon, participant)
    for speaker, text in ((MARIE, "un"), (HANS, "zwei"), (MARIE, "trois"), (RHYS, "tri")):
        await salon.ingest(speaker.id, text, language=speaker.language)

    await salon.deliver_all()

    hans_heard = [
        line.text for line in salon.interpreter_of(HANS.id).spoken if line.kind == "tour"
    ]
    rhys_heard = [
        line.text for line in salon.interpreter_of(RHYS.id).spoken if line.kind == "tour"
    ]
    assert hans_heard == ["un", "trois", "tri"]
    assert rhys_heard == ["un", "zwei", "trois"]


async def test_the_journal_needs_no_second_structure_to_be_ordered(salon):
    """The positions are the order. Nothing has to be kept in step with anything."""
    await _join(salon, MARIE)
    await _join(salon, HANS)

    await salon.ingest(MARIE.id, "un", language="fr")
    await salon.ingest(HANS.id, "zwei", language="de")

    entries = salon.log.entries
    assert [entry.sequence for entry in entries] == sorted(e.sequence for e in entries)
    assert list(entries) == sorted(entries, key=arrival_key)


# ── Breaking a tie ────────────────────────────────────────────────────────────


def test_two_messages_at_the_same_instant_are_still_ordered():
    """The clock has finite resolution, and two rooms can hand over a message inside the
    same microsecond. The position assigned on arrival breaks the tie."""
    journal = Journal(salon_id="salon-1", now=_frozen_clock())

    first = journal.append(participant_id="marie", text="un", language="fr")
    second = journal.append(participant_id="hans", text="zwei", language="de")

    assert first.arrived_at == second.arrived_at
    assert arrival_key(first) < arrival_key(second)


def test_the_tie_break_gives_the_same_answer_every_time():
    """Deterministic and reproducible, which is what the acceptance criterion asks. Sorting
    the same messages twice, in any starting order, gives one answer."""
    journal = Journal(salon_id="salon-1", now=_frozen_clock())
    for text in ("un", "deux", "trois", "quatre"):
        journal.append(participant_id="marie", text=text, language="fr")

    entries = journal.entries
    assert sorted(entries, key=arrival_key) == sorted(reversed(entries), key=arrival_key)
    assert list(entries) == sorted(entries, key=arrival_key)


def test_an_earlier_arrival_comes_first_whatever_its_position():
    """The timestamp is what decides; the position only settles a tie."""
    early = Journal(salon_id="s", now=lambda: T0).append(
        participant_id="marie", text="un", language="fr"
    )
    late = Journal(salon_id="s", now=lambda: T0 + timedelta(seconds=5)).append(
        participant_id="hans", text="zwei", language="de"
    )

    assert arrival_key(early) < arrival_key(late)


def test_the_pieces_of_one_intervention_share_an_instant_and_stay_in_order():
    """A split intervention is stamped once — it was said in one breath. The pieces are
    therefore the tie-break's most common customer, and they must not shuffle."""
    journal = Journal(salon_id="salon-1", now=_frozen_clock())

    pieces = journal.append_run(
        participant_id="marie", texts=["un.", "deux.", "trois."], language="fr"
    )

    assert len({entry.arrived_at for entry in pieces}) == 1
    assert list(pieces) == sorted(pieces, key=arrival_key)


def test_a_clock_that_goes_backwards_does_not_reorder_the_journal():
    """NTP corrects a drifting clock by moving it, sometimes backwards. What was already
    said cannot become something said later — the positions are the monotone spine, and the
    journal is read by position."""
    moments = iter([T0, T0 - timedelta(seconds=30), T0 + timedelta(seconds=1)])
    journal = Journal(salon_id="salon-1", now=lambda: next(moments))

    for text in ("un", "deux", "trois"):
        journal.append(participant_id="marie", text=text, language="fr")

    assert [entry.text for entry in journal.entries] == ["un", "deux", "trois"]
    assert [entry.sequence for entry in journal.entries] == [1, 2, 3]


def test_a_takeover_reconstructs_the_order_from_the_positions():
    """Storage may hand the rows back in any order at all."""
    journal = Journal(salon_id="salon-1", now=_frozen_clock())
    for text in ("un", "deux", "trois"):
        journal.append(participant_id="marie", text=text, language="fr")
    shuffled = tuple(reversed(journal.entries))

    resumed = Journal(salon_id="salon-1")
    resumed.restore(shuffled)

    assert [entry.text for entry in resumed.entries] == ["un", "deux", "trois"]


# ── Nobody is given the floor ─────────────────────────────────────────────────


async def test_anybody_may_speak_at_any_moment(salon):
    """No turn, no request, no attribution — FR9 is not implemented because it is removed.
    Three participants speak in immediate succession and all three are recorded."""
    for participant in (MARIE, HANS, RHYS):
        await _join(salon, participant)

    recorded = []
    for participant, text in ((RHYS, "tri"), (RHYS, "eto"), (MARIE, "un"), (HANS, "zwei")):
        recorded.extend(await salon.ingest(participant.id, text, language=participant.language))

    assert [entry.text for entry in recorded] == ["tri", "eto", "un", "zwei"]


async def test_speaking_needs_no_permission_from_anybody(salon):
    """Somebody who has not spoken yet, and has asked nothing of anybody, is recorded on
    their first word like everybody else."""
    await _join(salon, MARIE)

    (entry,) = await salon.ingest(MARIE.id, "je commence", language="fr")

    assert entry.sequence == 1


async def test_a_participant_who_has_not_joined_is_still_recorded(salon):
    """The journal takes what arrives. Who is entitled to be in a Salon is settled when
    they join it, not again on every sentence."""
    (entry,) = await salon.ingest("someone", "bonjour", language="fr")

    assert entry.participant_id == "someone"


def test_there_is_no_way_to_ask_for_or_grant_the_floor():
    """The acceptance criterion is a negative, so this is the shape it takes: no method
    exists that could hand somebody the right to speak. Story 6.8's microphone cut is a
    different thing — it takes a voice away, it does not hand one out."""
    surface = {name for name, _ in inspect.getmembers(Salon, callable)}
    forbidden = ("floor", "grant", "permission", "request_speak", "token", "turn_order")

    assert [name for name in surface if any(word in name.lower() for word in forbidden)] == []


# ── When two rooms hand over at once ──────────────────────────────────────────


async def test_concurrent_arrivals_never_share_a_position(salon):
    """Every room feeds the same journal, and `record_intervention` awaits its storage
    writes — so two arrivals really can be in flight together. Positions are assigned
    before the first await, which is what makes that safe."""
    import asyncio

    for participant in (MARIE, HANS, RHYS):
        await _join(salon, participant)

    results = await asyncio.gather(
        *(
            salon.ingest(participant.id, text, language=participant.language)
            for participant, text in (
                (MARIE, "un"),
                (HANS, "zwei"),
                (RHYS, "tri"),
                (MARIE, "quatre"),
            )
        )
    )

    sequences = [entry.sequence for pieces in results for entry in pieces]
    assert sorted(sequences) == [1, 2, 3, 4]
    assert len(set(sequences)) == 4


async def test_concurrent_split_interventions_do_not_interleave(salon):
    """The acceptance criterion of Story 6.5 under the conditions of this one: two long
    interventions arriving together still occupy two unbroken stretches of the journal."""
    import asyncio

    await _join(salon, MARIE)
    await _join(salon, HANS)
    long_fr = " ".join(f"Phrase française numéro {n} ici." for n in range(6))
    long_de = " ".join(f"Deutscher Satz Nummer {n} hier." for n in range(6))

    marie_pieces, hans_pieces = await asyncio.gather(
        salon.ingest(MARIE.id, long_fr, language="fr"),
        salon.ingest(HANS.id, long_de, language="de"),
    )

    for pieces in (marie_pieces, hans_pieces):
        sequences = [entry.sequence for entry in pieces]
        assert sequences == list(range(sequences[0], sequences[0] + len(sequences)))


async def test_the_journal_is_read_back_in_one_order_however_it_was_written(salon):
    """Reproducible, which is the word the acceptance criterion uses: the same messages
    give the same order every time they are read."""
    import asyncio

    for participant in (MARIE, HANS, RHYS):
        await _join(salon, participant)
    await asyncio.gather(
        salon.ingest(MARIE.id, "un", language="fr"),
        salon.ingest(HANS.id, "zwei", language="de"),
        salon.ingest(RHYS.id, "tri", language="cy"),
    )

    once = [entry.text for entry in salon.log.entries]
    twice = [entry.text for entry in salon.log.entries]

    assert once == twice
    assert once == [entry.text for entry in sorted(salon.log.entries, key=arrival_key)]
