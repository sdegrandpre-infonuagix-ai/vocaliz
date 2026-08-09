"""Build for N, configure at 3 (Story 10.2, replacing FR2).

Three is a starting value and never a fact about the product. One room and one interpreter per
participant means a fourth person costs one more interpreter — a price question, not an
architectural one — so nothing in the orchestrator may count to three, or to any number.

The ceiling is a persisted parameter for the same reason every other operational number is:
somebody will want to raise it for one customer, on a Tuesday, and a knob behind a deployment
is a knob that in practice never gets turned. The API reads it out of this same table.

The last test here is the acceptance criterion as an absence, and it is the one worth keeping
honest. A hard-coded participant count would not fail anything — it would simply refuse the
fourth person somewhere nobody thought to look.
"""
import pytest

from src.interprete import InterpreteFake, Participant
from src.journal import InMemoryJournalStore, SalonLog
from src.salon import InMemoryRoomProvisioner, Salon
from src.settings import DEFAULTS, InvalidSettings, SalonSettings


async def translate(text, *, source, target):
    return f"{text} [{target}]"


def test_the_ceiling_starts_at_three():
    assert DEFAULTS["participant_ceiling"] == 3
    assert SalonSettings().participant_ceiling == 3


def test_it_is_a_whole_number_of_people():
    """The settings table has one numeric column, so it comes back as a float. Half a
    participant is not something to provision a room for."""
    settings = SalonSettings(participant_ceiling=6.0)

    assert settings.participant_ceiling == 6
    assert isinstance(settings.participant_ceiling, int)


def test_it_can_be_raised_without_touching_code():
    """FR54's whole point, applied to this number: a new ceiling is a stored value, not a
    release."""
    assert SalonSettings().replace(participant_ceiling=25).participant_ceiling == 25


def test_a_salon_for_one_is_refused():
    """One participant and their interpreter is somebody talking to a translation of
    themselves. Refused where it is set rather than absorbed downstream, where silence would
    be some other module deciding what the operator meant."""
    with pytest.raises(InvalidSettings) as raised:
        SalonSettings(participant_ceiling=1)

    assert "participant_ceiling" in str(raised.value)


def test_the_ceiling_stands_apart_from_every_other_parameter():
    """No ordering rule ties it to the thresholds it sits beside. They answer unrelated
    questions, and a rule between them would only refuse configurations that work."""
    settings = SalonSettings(participant_ceiling=2)

    assert settings.participant_ceiling == 2
    assert settings.condensation_threshold_seconds == DEFAULTS["condensation_threshold_seconds"]


# ── Build for N ───────────────────────────────────────────────────────────────


async def test_a_salon_takes_as_many_people_as_it_is_given():
    """Nothing here counts. The ceiling is enforced where a Salon is created and a guest is
    let in — the API — because that is where somebody can be told why."""
    salon = Salon(
        log=SalonLog(salon_id="s", store=InMemoryJournalStore(), translate=translate),
        rooms=InMemoryRoomProvisioner(),
        max_message_characters=100_000,
    )
    cast = [
        Participant(id=f"p{index}", language="fr", name=f"P{index}") for index in range(12)
    ]
    for person in cast:
        await salon.join(person, InterpreteFake(participant=person))

    assert len(salon.participants) == 12


async def test_everybody_hears_everybody_however_many_there_are():
    """The property that would break first if something counted to three: the twelfth
    person's message reaching the other eleven."""
    salon = Salon(
        log=SalonLog(salon_id="s", store=InMemoryJournalStore(), translate=translate),
        rooms=InMemoryRoomProvisioner(),
        max_message_characters=100_000,
    )
    cast = [
        Participant(id=f"p{index}", language="fr", name=f"P{index}") for index in range(12)
    ]
    for person in cast:
        await salon.join(person, InterpreteFake(participant=person))

    await salon.ingest(cast[-1].id, "Bonjour à tous.", language="fr")
    await salon.deliver_all()

    heard = [
        person.id
        for person in cast[:-1]
        if any(
            line.kind == "tour" for line in salon.interpreter_of(person.id).spoken
        )
    ]
    assert len(heard) == 11


def test_no_module_assumes_how_many_people_are_in_a_salon():
    """The acceptance criterion as an absence, read off the source.

    A hard-coded count would fail nothing — it would refuse the fourth person somewhere
    nobody thought to look — so behaviour cannot catch it and this has to.

    What is looked for is a number compared against a count of people. Not every literal 3
    in the codebase: `range(3)` in a retry loop is nobody's participant limit, and a guard
    that flagged it would be worked around rather than obeyed.
    """
    import ast
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[1] / "src"
    counting = {"participants", "seats", "_seats", "cast", "room_count"}
    offenders = []

    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Compare):
                continue
            rendered = ast.unparse(node)
            names_a_count = any(word in rendered for word in counting)
            has_a_literal = any(
                isinstance(side, ast.Constant) and isinstance(side.value, int)
                for side in [node.left, *node.comparators]
            )
            # `len(x) > 0` and `== 0` are emptiness tests, not limits: "is anybody here" is
            # a question about existence rather than about how many fit.
            compares_to_zero = any(
                isinstance(side, ast.Constant) and side.value == 0
                for side in [node.left, *node.comparators]
            )
            if names_a_count and has_a_literal and not compares_to_zero:
                offenders.append(f"{path.relative_to(root).as_posix()}: {rendered}")

    assert offenders == []
