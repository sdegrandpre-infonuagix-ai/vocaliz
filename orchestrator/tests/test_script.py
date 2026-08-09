"""Serving a script instead of speaking it.

The orchestrator holds no audio, so it can no longer call an interpreter: the interpreter
now sits in the agent, beside the microphone. What it does instead is answer the question
*what do I owe my human?* with an ordered list, which the agent says with its own voice.

The load-bearing assertion in this file is `test_a_played_script_says_exactly_what_delivery_would_have_said`.
Everything else here is detail. If that one holds, then no rule about what to say — the
advertising slots, the introductions, the condensation threshold, the held announcements —
has a served version and a spoken version that could drift apart, because there is only one
of each and this proves it.
"""
import pytest

from src.interprete import Annonce, InterpreteFake, Participant, Tour
from src.journal import InMemoryJournalStore, SalonLog
from src.salon import InMemoryRoomProvisioner, Salon
from src.salon.script import (
    ANNONCE,
    CONDENSATION,
    TOUR,
    NothingToSpeakThrough,
    Script,
)

MARIE = Participant(id="marie", language="fr", name="Marie")
HANS = Participant(id="hans", language="de", name="Hans")


async def translate(text, *, source, target):
    return f"{text} [{target}]"


def _salon():
    log = SalonLog(salon_id="salon-1", store=InMemoryJournalStore(), translate=translate)
    return Salon(log=log, rooms=InMemoryRoomProvisioner())


async def _join(salon, participant, **kwargs):
    return await salon.join(participant, InterpreteFake(participant=participant), **kwargs)


@pytest.fixture
def salon():
    return _salon()


# ── The recorder on its own ───────────────────────────────────────────────────


async def test_a_script_writes_down_what_it_was_asked_to_say():
    script = Script(language="fr")

    await script.render(Tour(participant_id="hans", text="Guten Tag", language="de"))
    await script.insert_annonce(Annonce(text="Hans arrive", language="fr"))

    assert [line.kind for line in script.lines] == [TOUR, ANNONCE]
    assert script.lines[0].tour.text == "Guten Tag"
    assert script.lines[1].annonce.text == "Hans arrive"


async def test_a_turn_keeps_the_language_it_was_said_in():
    """Not flattened to a string. An adapter that translates and speaks in one movement must
    not be handed something somebody else already translated — that is what speech-to-speech
    is, and losing the original here would throw it away before the agent ever saw it."""
    script = Script(language="fr")

    await script.render(Tour(participant_id="hans", text="Guten Tag", language="de"))

    line = script.lines[0]
    assert line.tour.language == "de"  # what it is in
    assert line.language == "fr"  # what to say it in


async def test_condensing_nothing_produces_no_line():
    """An interpreter announcing the summary of nothing is worse than silence. The rule sits
    here rather than in each adapter that would otherwise have to remember it."""
    script = Script(language="fr")

    await script.condense([])

    assert script.lines == []


async def test_a_script_never_raises_where_an_interpreter_would():
    """`InterpreteError` means a provider did not answer, and there is no provider here. Under
    the served model that failure happens in the agent, a network away from the decision to
    say anything — so the conductor's `except InterpreteError` branches simply do not apply
    to writing a list down, and nothing may make them fire."""
    script = Script(language="fr")

    for _ in range(50):
        await script.render(Tour(participant_id="hans", text="x", language="de"))

    assert len(script.lines) == 50


# ── The two paths are one path ────────────────────────────────────────────────


async def test_a_played_script_says_exactly_what_delivery_would_have_said():
    """The assertion this whole design rests on.

    Two Salons, driven identically. One delivers in process, as everything did before the
    boundary was drawn. The other is served a script and plays it into an interpreter, as the
    agent does. What the two interpreters end up saying must be indistinguishable — same
    lines, same order, same languages, introductions and all.
    """
    spoken_salon, served_salon = _salon(), _salon()
    for salon in (spoken_salon, served_salon):
        await _join(salon, MARIE)
        await _join(salon, HANS)
        await salon.ingest("hans", "Guten Tag, wie geht es Ihnen?", language="de")
        await salon.ingest("hans", "Ich freue mich auf das Gespräch.", language="de")

    await spoken_salon.deliver("marie")

    script = await served_salon.script_for("marie")
    played = InterpreteFake(participant=MARIE)
    await script.play(played)

    was_spoken = spoken_salon.interpreter_of("marie").spoken
    assert [u.text for u in played.spoken] == [u.text for u in was_spoken]
    assert [u.language for u in played.spoken] == [u.language for u in was_spoken]
    assert [u.kind for u in played.spoken] == [u.kind for u in was_spoken]
    assert len(played.spoken) > 1  # the turns and the introduction, not an empty agreement


async def test_serving_a_script_says_nothing_through_the_interpreter(salon):
    """The boundary itself. While a script is being written the seat's own interpreter must
    stay entirely silent — otherwise the orchestrator would still be speaking, which is the
    thing that cannot cross a process."""
    await _join(salon, MARIE)
    await _join(salon, HANS)
    await salon.ingest("hans", "Guten Tag", language="de")

    script = await salon.script_for("marie")

    assert script.lines != []
    assert salon.interpreter_of("marie").spoken == []


async def test_the_reading_position_advances_when_the_script_is_handed_over(salon):
    """Handed over, not confirmed. In this topology a room holds one human and their agent,
    so an agent that dies takes the room with it and there is nobody left to have missed
    anything — where delivering twice is a failure a listener can actually notice."""
    await _join(salon, MARIE)
    await _join(salon, HANS)
    await salon.ingest("hans", "Guten Tag", language="de")

    await salon.script_for("marie")

    assert await salon.script_for("marie") == Script(language="fr")


async def test_nobody_is_served_their_own_words(salon):
    """The same rule delivery follows, and for the same reason: it is the one thing they
    certainly already know."""
    await _join(salon, MARIE)
    await _join(salon, HANS)
    await salon.ingest("marie", "Bonjour à tous", language="fr")

    script = await salon.script_for("marie")

    assert [line for line in script.lines if line.kind == TOUR] == []


async def test_an_unknown_participant_is_served_an_empty_script(salon):
    """Somebody who has left, or never arrived. An empty script rather than an error: a
    disconnection is often reported twice and neither report may fail a request."""
    assert (await salon.script_for("nobody")).lines == []


# ── A seat with no interpreter at all ─────────────────────────────────────────
#
# The production case. The agent in this participant's room holds their interpreter, beside
# the audio, so between two scripts there is nothing here to speak through. What these tests
# establish is that nothing is *lost* in that gap — an announcement with nowhere to go waits
# rather than disappearing.


async def _served(salon, participant, **kwargs):
    """Join without an interpreter, which is what the API does in production."""
    return await salon.join(participant, **kwargs)


async def test_a_served_seat_is_still_handed_everything_it_is_owed(salon):
    await _served(salon, MARIE)
    await _served(salon, HANS)
    await salon.ingest("hans", "Guten Tag", language="de")

    script = await salon.script_for("marie")

    assert [line.tour.text for line in script.lines if line.kind == TOUR] == ["Guten Tag"]


async def test_delivering_to_a_served_seat_in_process_does_nothing_at_all(salon):
    """And in particular does not move the reading position. Rendering against a voice that
    is not here is how a listener loses turns that were counted as said."""
    await _served(salon, MARIE)
    await _served(salon, HANS)
    await salon.ingest("hans", "Guten Tag", language="de")

    await salon.deliver("marie")

    assert [line.tour.text for line in (await salon.script_for("marie")).lines
            if line.kind == TOUR] == ["Guten Tag"]


async def test_an_announcement_with_nowhere_to_go_waits_rather_than_vanishing(salon):
    """The failure this guards against is silent: `_say_held` draining into a void would
    lose the arrival notices, the microphone changes and the balance alerts, with the whole
    suite still green."""
    await _served(salon, MARIE)

    await salon.announce("marie", Annonce(text="Votre solde est bas", language="fr"))
    script = await salon.script_for("marie")

    assert [line.annonce.text for line in script.lines] == ["Votre solde est bas"]


async def test_a_served_salon_hands_over_the_arrival_notices_it_could_not_say(salon):
    """Nobody has spoken, so there is no seam to drain the queue at. Without the flush at
    the end of a script, somebody arriving into a conversation would be told who is here
    only once somebody happened to say something."""
    await _served(salon, MARIE)
    await salon.ingest("marie", "Bonjour", language="fr")
    await _served(salon, HANS)

    script = await salon.script_for("hans")

    assert any("Marie" in line.annonce.text for line in script.lines if line.annonce)


async def test_a_served_seat_is_never_asked_what_it_heard(salon):
    """`collect` pulls transcriptions out of interpreters, which is the orchestrator holding
    a microphone. A served seat is skipped: its agent reports instead."""
    await _served(salon, MARIE)

    assert await salon.collect() == ()


async def test_speaking_to_a_served_seat_between_two_scripts_is_an_error(salon):
    """Loud rather than silent, deliberately. Every path that could reach this holds what it
    was going to say instead — so if one ever stops, it must break something visible rather
    than leave one participant hearing nothing."""
    await _served(salon, MARIE)
    seat = salon._seats["marie"]

    with pytest.raises(NothingToSpeakThrough):
        seat.voice


async def test_a_seat_with_an_interpreter_is_not_served(salon):
    """The in-process Salon the load simulator and the tests run, unchanged."""
    await _join(salon, MARIE)

    assert salon._seats["marie"].served is False


# ── The wire form ─────────────────────────────────────────────────────────────


async def test_the_wire_form_carries_what_is_needed_to_say_a_turn():
    script = Script(language="fr")
    await script.render(
        Tour(participant_id="hans", text="Guten Tag", language="de", sequence=7)
    )

    [line] = script.as_json()

    assert line == {
        "kind": TOUR,
        "language": "fr",
        "tour": {
            "participantId": "hans",
            "text": "Guten Tag",
            "language": "de",
            "sequence": 7,
        },
    }


async def test_the_wire_form_of_a_condensation_carries_the_whole_interval():
    script = Script(language="fr")
    await script.condense(
        [
            Tour(participant_id="hans", text="eins", language="de"),
            Tour(participant_id="rhys", text="dau", language="cy"),
        ]
    )

    [line] = script.as_json()

    assert line["kind"] == CONDENSATION
    assert [covered["text"] for covered in line["covers"]] == ["eins", "dau"]


async def test_the_conductor_never_speaks_through_an_interpreter_directly():
    """The inversion, stated as the thing that cannot come back.

    Every rule about what to say goes through `seat.voice`, which is the script when one is
    being written and the interpreter otherwise. A rule that reached for `seat.interpreter`
    instead would work perfectly in process and say nothing at all over the wire — silence
    for that participant, and a test suite still green, which is exactly the failure a guard
    is for. `aclose` and `ingest` are the two exemptions: neither is speaking.
    """
    from pathlib import Path

    source = Path(__file__).resolve().parents[1] / "src" / "salon" / "conductor.py"
    speaking = ("render", "insert_annonce", "condense")

    offenders = [
        line.strip()
        for line in source.read_text(encoding="utf-8").splitlines()
        if any(f"seat.interpreter.{verb}(" in line for verb in speaking)
    ]

    assert offenders == []


async def test_a_served_script_survives_the_wire_and_still_says_the_same_thing(salon):
    """Serialised, and nothing that decides what is said is lost on the way out. This is the
    form the agent actually receives, so a field missing here is a line it cannot speak."""
    await _join(salon, MARIE)
    await _join(salon, HANS)
    await salon.ingest("hans", "Guten Tag", language="de")

    payload = (await salon.script_for("marie")).as_json()

    assert all(line["language"] == "fr" for line in payload)
    assert all(line["kind"] in {TOUR, ANNONCE, CONDENSATION} for line in payload)
    spoken = [line.get("text") or line["tour"]["text"] for line in payload]
    assert "Guten Tag" in spoken
