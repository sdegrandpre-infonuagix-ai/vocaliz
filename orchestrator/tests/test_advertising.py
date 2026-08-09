"""Where an advertisement goes, and what happens after it (FR39 / FR33).

The broadcast itself is inherited: the exchange reserves, the delivery is confirmed, and
`ad_broadcasts.delivered_at` keeps reserved apart from actually heard. What was missing is the
**placement** — an advertisement goes between two messages from two different people, never
inside one person's cut-up intervention — and the catching up afterwards.

Between two *distinct* speakers rather than merely at a seam. A seam is where an intervention
ends, and somebody may well carry straight on with a second message; dropping an advertisement
between two of their sentences is only marginally better than dropping it into the middle of
one. A change of speaker is a place a listener already expects to be interrupted.

The listener's own words are not one side of that boundary. They never hear them, so from
where they sit two messages of theirs either side of the advertisement are not two messages
at all.

Nothing here is synchronised between rooms. Each interpreter draws for its own participant,
in their language, at whatever moment its own rendering reaches a boundary. Two people in one
Salon hear different advertisements at different times, and that is the topology working
rather than a defect in it.
"""
import pytest

from src.interprete import Annonce, InterpreteError, InterpreteFake, Participant
from src.journal import CHARACTERS_PER_SECOND, InMemoryJournalStore, SalonLog
from src.salon import InMemoryRoomProvisioner, Salon
from src.salon.advertising import Diffusion, RegieFake

MARIE = Participant(id="marie", language="fr", name="Marie")
HANS = Participant(id="hans", language="de", name="Hans")
SOFIA = Participant(id="sofia", language="es", name="Sofia")

CEILING = 300.0
THRESHOLD = 120.0
# One piece of a cut intervention, small enough that several fit under the ceiling.
PIECE_CHARACTERS = 500

# Distinct words of more than three letters: the stammer rule from Story 6.11 collapses a
# repeated short one, and the intervention would arrive as a single message with no inside.
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
        piece = word + ("." if index % 12 == 0 else "")
        out.append(piece)
        length += len(piece) + 1
    return " ".join(out) + "."


async def translate(text, *, source, target):
    return f"{text} [{target}]"


@pytest.fixture
def regie():
    return RegieFake(pitch="Chez Rivard, le café est torréfié sur place.")


@pytest.fixture
def salon(regie):
    log = SalonLog(salon_id="salon-1", store=InMemoryJournalStore(), translate=translate)
    return Salon(
        log=log,
        rooms=InMemoryRoomProvisioner(),
        regie=regie,
        # Out of the way unless a test is about them.
        condensation_threshold_seconds=100_000.0,
        saturation_threshold_seconds=100_000.0,
        unblock_threshold_seconds=99_000.0,
        monologue_ceiling_seconds=CEILING,
        max_message_characters=100_000,
    )


async def _join(salon, participant):
    return await salon.join(participant, InterpreteFake(participant=participant))


async def _room_of_three(salon):
    await _join(salon, MARIE)
    await _join(salon, HANS)
    await _join(salon, SOFIA)


def _kinds(salon, participant_id):
    return [line.kind for line in salon.interpreter_of(participant_id).spoken]


def _said(salon, participant_id):
    return [line.text for line in salon.interpreter_of(participant_id).spoken]


def _heard_the_advertisement(salon, participant_id, regie) -> bool:
    """By text rather than by kind: introductions and notices are announcements too, and
    matching on `kind == "annonce"` would pass whatever this code did."""
    return any(regie.pitch in text for text in _said(salon, participant_id))


# ── Between two messages, from two different people ───────────────────────────


async def test_an_advertisement_goes_between_two_people(salon, regie):
    await _room_of_three(salon)
    await salon.ingest(MARIE.id, "Bonjour à tous.", language="fr")
    await salon.ingest(SOFIA.id, "Buenas tardes.", language="es")
    salon.advertising_due(HANS.id)

    await salon.deliver(HANS.id)

    said = _said(salon, HANS.id)
    positions = [i for i, text in enumerate(said) if regie.pitch in text]
    tours = [i for i, line in enumerate(salon.interpreter_of(HANS.id).spoken)
             if line.kind == "tour"]
    assert positions and tours[0] < positions[0] < tours[1]


async def test_nothing_goes_between_two_messages_from_the_same_person(salon, regie):
    """A seam is not a boundary. Two of somebody's own sentences with an advertisement
    wedged between them is barely better than one sentence cut in half."""
    await _room_of_three(salon)
    await salon.ingest(MARIE.id, "Bonjour à tous.", language="fr")
    await salon.ingest(MARIE.id, "Je voulais vous dire une chose.", language="fr")
    salon.advertising_due(HANS.id)

    await salon.deliver(HANS.id)

    assert _heard_the_advertisement(salon, HANS.id, regie) is False


async def test_it_waits_for_a_boundary_rather_than_being_dropped(salon, regie):
    """The slot is owed until a placement turns up. Silence would have been the exchange's
    money spent on nothing."""
    await _room_of_three(salon)
    await salon.ingest(MARIE.id, "Bonjour à tous.", language="fr")
    await salon.ingest(MARIE.id, "Je voulais vous dire une chose.", language="fr")
    salon.advertising_due(HANS.id)
    await salon.deliver(HANS.id)

    await salon.ingest(SOFIA.id, "Buenas tardes.", language="es")
    await salon.deliver(HANS.id)

    assert _heard_the_advertisement(salon, HANS.id, regie) is True


async def test_nothing_goes_before_the_first_message_anybody_hears(salon, regie):
    """There is only one message, so there is no *between*. An advertisement as the first
    thing a listener hears is an advertisement before the conversation."""
    await _room_of_three(salon)
    await salon.ingest(MARIE.id, "Bonjour à tous.", language="fr")
    salon.advertising_due(HANS.id)

    await salon.deliver(HANS.id)

    assert _heard_the_advertisement(salon, HANS.id, regie) is False


async def test_the_listener_own_message_is_not_one_side_of_the_boundary(salon, regie):
    """They never hear their own words, so from where they sit these are two messages from
    one person with nothing between them."""
    await _room_of_three(salon)
    await salon.ingest(MARIE.id, "Bonjour à tous.", language="fr")
    await salon.ingest(HANS.id, "Guten Tag.", language="de")
    await salon.ingest(MARIE.id, "Je disais donc.", language="fr")
    salon.advertising_due(HANS.id)

    await salon.deliver(HANS.id)

    assert _heard_the_advertisement(salon, HANS.id, regie) is False


# ── A cut intervention is left alone ──────────────────────────────────────────


async def test_nothing_goes_inside_a_cut_intervention(regie):
    """Story 6.5's rule, and an advertisement is the least defensible thing to break it
    for: it serves somebody who is not in the room."""
    small = Salon(
        log=SalonLog(salon_id="s", store=InMemoryJournalStore(), translate=translate),
        rooms=InMemoryRoomProvisioner(),
        regie=regie,
        condensation_threshold_seconds=100_000.0,
        saturation_threshold_seconds=100_000.0,
        unblock_threshold_seconds=99_000.0,
        monologue_ceiling_seconds=CEILING,
        max_message_characters=PIECE_CHARACTERS,
    )
    await _join(small, MARIE)
    await _join(small, HANS)
    recorded = await small.ingest(MARIE.id, long_text(60), language="fr")
    assert len(recorded) > 1
    small.advertising_due(HANS.id)

    await small.deliver(HANS.id)

    assert _heard_the_advertisement(small, HANS.id, regie) is False


async def test_past_the_monologue_ceiling_it_goes_in_anyway(regie):
    """Held with no limit, the courtesy becomes the means by which one speaker makes the
    room unreachable — including to the tier the listener is paying nothing for."""
    small = Salon(
        log=SalonLog(salon_id="s", store=InMemoryJournalStore(), translate=translate),
        rooms=InMemoryRoomProvisioner(),
        regie=regie,
        condensation_threshold_seconds=100_000.0,
        saturation_threshold_seconds=100_000.0,
        unblock_threshold_seconds=99_000.0,
        monologue_ceiling_seconds=CEILING,
        max_message_characters=PIECE_CHARACTERS,
    )
    await _join(small, MARIE)
    await _join(small, HANS)
    await small.ingest(MARIE.id, long_text(CEILING * 2), language="fr")
    small.advertising_due(HANS.id)

    await small.deliver(HANS.id)

    assert _heard_the_advertisement(small, HANS.id, regie) is True


# ── A pull, one room at a time ────────────────────────────────────────────────


async def test_the_inventory_is_drawn_from_at_the_placement_and_not_before(salon):
    """A pull. Drawing when the moment arrives rather than when the slot is used would pick
    against a stale record of what this listener has already heard."""
    await _room_of_three(salon)
    await salon.ingest(MARIE.id, "Bonjour à tous.", language="fr")
    await salon.ingest(SOFIA.id, "Buenas tardes.", language="es")
    salon.advertising_due(HANS.id)
    assert salon.regie.draws == []

    await salon.deliver(HANS.id)

    assert salon.regie.draws == [(HANS.id, "de")]


async def test_each_room_draws_for_itself(salon):
    """No synchronisation between rooms: each interpreter draws for its own participant, in
    their language, when its own rendering reaches a boundary."""
    await _room_of_three(salon)
    # Three speakers, so that two different listeners each reach a change of speaker: Marie
    # never hears herself, and a boundary she is not part of is the only kind she has.
    await salon.ingest(MARIE.id, "Bonjour à tous.", language="fr")
    await salon.ingest(SOFIA.id, "Buenas tardes.", language="es")
    await salon.ingest(HANS.id, "Guten Tag.", language="de")
    salon.advertising_due(HANS.id)
    salon.advertising_due(MARIE.id)

    await salon.deliver_all()

    assert sorted(salon.regie.draws) == [(HANS.id, "de"), (MARIE.id, "fr")]


async def test_one_room_reading_does_not_make_another_read(salon, regie):
    await _room_of_three(salon)
    await salon.ingest(MARIE.id, "Bonjour à tous.", language="fr")
    await salon.ingest(SOFIA.id, "Buenas tardes.", language="es")
    salon.advertising_due(HANS.id)

    await salon.deliver_all()

    assert _heard_the_advertisement(salon, HANS.id, regie) is True
    assert _heard_the_advertisement(salon, MARIE.id, regie) is False


async def test_a_slot_is_spent_once(salon, regie):
    """The frequency belongs to the tier (FR33). One moment of broadcast is one
    advertisement, not one per boundary until the end of the Salon."""
    await _room_of_three(salon)
    await salon.ingest(MARIE.id, "Bonjour à tous.", language="fr")
    await salon.ingest(SOFIA.id, "Buenas tardes.", language="es")
    await salon.ingest(MARIE.id, "Et donc voilà.", language="fr")
    salon.advertising_due(HANS.id)

    await salon.deliver(HANS.id)

    assert len(regie.draws) == 1


# ── Reserved, spoken, confirmed ───────────────────────────────────────────────


async def test_the_delivery_is_confirmed_once_it_has_been_spoken(salon, regie):
    await _room_of_three(salon)
    await salon.ingest(MARIE.id, "Bonjour à tous.", language="fr")
    await salon.ingest(SOFIA.id, "Buenas tardes.", language="es")
    salon.advertising_due(HANS.id)

    await salon.deliver(HANS.id)

    assert [d.id for d in regie.delivered_ones] == [regie.reserved[0].id]


async def test_a_broadcast_nobody_heard_is_never_confirmed(salon, regie):
    """The distinction `ad_broadcasts.delivered_at` exists for. Charging an advertiser for a
    sentence nobody heard is the one outcome this must not produce."""
    await _room_of_three(salon)
    salon.interpreter_of(HANS.id).fail_with = InterpreteError(HANS.id, "adapter down")
    await salon.ingest(MARIE.id, "Bonjour à tous.", language="fr")
    await salon.ingest(SOFIA.id, "Buenas tardes.", language="es")
    salon.advertising_due(HANS.id)

    await salon.deliver(HANS.id)

    assert regie.delivered_ones == []


async def test_an_empty_inventory_says_nothing(salon, regie):
    """Story 9.2 returns nothing only when the table is genuinely empty. Silence is the
    right outcome, and it costs the slot rather than being retried at every boundary."""
    regie.empty = True
    await _room_of_three(salon)
    await salon.ingest(MARIE.id, "Bonjour à tous.", language="fr")
    await salon.ingest(SOFIA.id, "Buenas tardes.", language="es")
    await salon.ingest(MARIE.id, "Et donc voilà.", language="fr")
    salon.advertising_due(HANS.id)

    await salon.deliver(HANS.id)

    # Drawn once and not again at the boundary after it: the slot is spent by being used.
    assert len(regie.draws) == 1
    assert _heard_the_advertisement(salon, HANS.id, regie) is False
    assert _kinds(salon, HANS.id).count("tour") == 3


async def test_an_exchange_that_cannot_be_reached_does_not_stop_the_conversation(
    salon, regie
):
    """A Salon must not go down because an advertising exchange did. The conversation is the
    product; the advertising is how one tier of it is paid for."""
    regie.fail_with = RuntimeError("exchange unreachable")
    await _room_of_three(salon)
    await salon.ingest(MARIE.id, "Bonjour à tous.", language="fr")
    await salon.ingest(SOFIA.id, "Buenas tardes.", language="es")
    salon.advertising_due(HANS.id)

    await salon.deliver(HANS.id)

    assert _kinds(salon, HANS.id).count("tour") == 2


async def test_a_salon_with_no_exchange_simply_hears_no_advertising():
    """A deployment without one loses the advertising and nothing else."""
    quiet = Salon(
        log=SalonLog(salon_id="s", store=InMemoryJournalStore(), translate=translate),
        rooms=InMemoryRoomProvisioner(),
        condensation_threshold_seconds=100_000.0,
        saturation_threshold_seconds=100_000.0,
        unblock_threshold_seconds=99_000.0,
        max_message_characters=100_000,
    )
    await _join(quiet, MARIE)
    await _join(quiet, HANS)
    await _join(quiet, SOFIA)
    await quiet.ingest(MARIE.id, "Bonjour à tous.", language="fr")
    await quiet.ingest(SOFIA.id, "Buenas tardes.", language="es")
    quiet.advertising_due(HANS.id)

    await quiet.deliver(HANS.id)

    assert _kinds(quiet, HANS.id).count("tour") == 2


# ── Catching up afterwards ────────────────────────────────────────────────────


def _catching_up_salon(regie):
    return Salon(
        log=SalonLog(salon_id="s", store=InMemoryJournalStore(), translate=translate),
        rooms=InMemoryRoomProvisioner(),
        regie=regie,
        condensation_threshold_seconds=THRESHOLD,
        saturation_threshold_seconds=100_000.0,
        unblock_threshold_seconds=99_000.0,
        max_message_characters=100_000,
    )


class TalkativeRegie(RegieFake):
    """An exchange whose advertisement takes real time to read.

    The conversation does not stop for it, so the journal grows while it is being spoken —
    which is the whole reason there is anything to catch up on afterwards.
    """

    def __init__(self, *, salon_of, seconds: float, **kwargs) -> None:
        super().__init__(**kwargs)
        self._salon_of = salon_of
        self._seconds = seconds

    async def delivered(self, diffusion: Diffusion) -> None:
        await super().delivered(diffusion)
        salon = self._salon_of()
        await salon.ingest(SOFIA.id, "a" * int(self._seconds * CHARACTERS_PER_SECOND),
                           language="es")


async def test_what_piled_up_during_the_advertisement_is_condensed():
    """Past `condensation_threshold`, the backlog is said in substance. An advertisement
    that left a listener permanently further behind would be the tier charging them in lag
    for something sold to somebody else."""
    holder = {}
    regie = TalkativeRegie(salon_of=lambda: holder["salon"], seconds=THRESHOLD * 2,
                           pitch="Chez Rivard.")
    salon = holder["salon"] = _catching_up_salon(regie)
    await _join(salon, MARIE)
    await _join(salon, HANS)
    await _join(salon, SOFIA)
    await salon.ingest(MARIE.id, "Bonjour à tous.", language="fr")
    await salon.ingest(SOFIA.id, "Buenas tardes.", language="es")
    salon.advertising_due(HANS.id)

    await salon.deliver(HANS.id)

    assert "condense" in _kinds(salon, HANS.id)


async def test_a_small_backlog_is_replayed_rather_than_condensed():
    """Condensation is a loss. It is worth it past the threshold and not before, whatever
    put the listener behind."""
    holder = {}
    regie = TalkativeRegie(salon_of=lambda: holder["salon"], seconds=1.0,
                           pitch="Chez Rivard.")
    salon = holder["salon"] = _catching_up_salon(regie)
    await _join(salon, MARIE)
    await _join(salon, HANS)
    await _join(salon, SOFIA)
    await salon.ingest(MARIE.id, "Bonjour à tous.", language="fr")
    await salon.ingest(SOFIA.id, "Buenas tardes.", language="es")
    salon.advertising_due(HANS.id)

    await salon.deliver(HANS.id)
    await salon.deliver(HANS.id)

    assert "condense" not in _kinds(salon, HANS.id)
    assert _kinds(salon, HANS.id).count("tour") == 3


async def test_nothing_goes_immediately_after_a_summary():
    """A summary is not a message from a person, so nothing spans it. Being told the gist of
    what several people said and then hearing an advertisement is the tier taking the one
    moment a listener is furthest behind to sell them something."""
    regie = RegieFake(pitch="Chez Rivard.")
    salon = _catching_up_salon(regie)
    await _join(salon, MARIE)
    await _join(salon, HANS)
    await _join(salon, SOFIA)
    await salon.ingest(MARIE.id, "a" * int(THRESHOLD * 2 * CHARACTERS_PER_SECOND),
                       language="fr")
    salon.advertising_due(HANS.id)
    await salon.deliver(HANS.id)
    assert "condense" in _kinds(salon, HANS.id)

    await salon.ingest(SOFIA.id, "Buenas tardes.", language="es")
    await salon.deliver(HANS.id)

    assert _heard_the_advertisement(salon, HANS.id, regie) is False


# ── The port ──────────────────────────────────────────────────────────────────


async def test_an_advertisement_is_read_in_the_language_of_its_listener(salon, regie):
    """Not the language it was written in. Story 9.2 stores a creative and derives the rest,
    exactly as a turn of speech is."""
    await _room_of_three(salon)
    await salon.ingest(MARIE.id, "Bonjour à tous.", language="fr")
    await salon.ingest(SOFIA.id, "Buenas tardes.", language="es")
    salon.advertising_due(HANS.id)

    await salon.deliver(HANS.id)

    spoken = [line for line in salon.interpreter_of(HANS.id).spoken
              if regie.pitch in line.text]
    assert spoken and spoken[0].language == HANS.language


async def test_the_orchestrator_never_holds_a_location():
    """`draw` takes a participant and a language and nothing else. Which cell somebody is in
    is the exchange's business, so a location never enters the process that holds the
    conversation — which is a stronger guarantee than remembering not to log it."""
    import inspect

    from src.salon.advertising import Regie

    parameters = inspect.signature(Regie.draw).parameters

    assert set(parameters) == {"self", "participant_id", "language"}


async def test_a_diffusion_carries_its_reservation(salon, regie):
    """The identifier the confirmation refers to. Without it the exchange cannot tell which
    of two reservations was the one actually spoken."""
    await _room_of_three(salon)
    await salon.ingest(MARIE.id, "Bonjour à tous.", language="fr")
    await salon.ingest(SOFIA.id, "Buenas tardes.", language="es")
    salon.advertising_due(HANS.id)

    await salon.deliver(HANS.id)

    diffusion, = regie.reserved
    assert isinstance(diffusion, Diffusion)
    assert isinstance(diffusion.annonce, Annonce)
    assert diffusion.id
