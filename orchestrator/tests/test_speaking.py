"""Who is talking, when nobody can hear anybody.

The signal this replaces is the one the topology destroyed. Silence in your ear used to mean
nobody was speaking. Now it means your interpreter has nothing to render yet — which is a
completely different fact, and one you have no way of telling apart from the first.

So each pair gets two lights, not one. Marie speaking and Marie's interpreter rendering are
different things, and the second is what explains the delay in the first: seeing her light
green and her interpreter's still red is seeing exactly why you are still waiting.

Everybody sees every pair. LiveKit publishes speaking state natively, but only within a
room — and the humans share no room, so the orchestrator is what carries it between them,
over the same data channel as the turns.
"""
import json

import pytest

from src.interprete import InterpreteFake, Participant
from src.journal import InMemoryJournalStore, SalonLog
from src.salon import InMemoryRoomProvisioner, Salon, SpeakingBoard, Voice

MARIE = Participant(id="marie", language="fr", name="Marie")
HANS = Participant(id="hans", language="de", name="Hans")
CALLER = Participant(id="+15145550123", language="en", by_telephone=True)


async def translate(text, *, source, target):
    return f"{text} [{target}]"


@pytest.fixture
def rooms():
    return InMemoryRoomProvisioner()


@pytest.fixture
def salon(rooms):
    log = SalonLog(salon_id="salon-1", store=InMemoryJournalStore(), translate=translate)
    return Salon(log=log, rooms=rooms)


async def _join(salon, participant, **kwargs):
    return await salon.join(participant, InterpreteFake(participant=participant), **kwargs)


def _boards(rooms, room):
    """Every speaking board that reached one room, decoded."""
    out = []
    for payload in rooms.published(room):
        try:
            message = json.loads(payload.decode())
        except ValueError:
            continue
        if message.get("kind") == "speaking":
            out.append(message)
    return out


# ── Two lights per pair ───────────────────────────────────────────────────────


def test_a_pair_has_a_light_for_each_voice():
    """Marie speaking and Marie's interpreter rendering are two facts, and the second is
    what explains the delay in the first."""
    board = SpeakingBoard()

    board.set(MARIE.id, human=True, interpreter=False)

    (pair,) = board.pairs
    assert pair.human is Voice.ACTIVE
    assert pair.interpreter is Voice.QUIET


def test_both_voices_can_be_active_at_once():
    """Somebody talking while their interpreter is still rendering the last person. Common,
    and exactly the state a single light could not show."""
    board = SpeakingBoard()

    board.set(MARIE.id, human=True, interpreter=True)

    (pair,) = board.pairs
    assert (pair.human, pair.interpreter) == (Voice.ACTIVE, Voice.ACTIVE)


def test_a_pair_starts_quiet():
    board = SpeakingBoard()

    board.attach(MARIE.id)

    (pair,) = board.pairs
    assert (pair.human, pair.interpreter) == (Voice.QUIET, Voice.QUIET)


def test_a_pair_that_leaves_is_no_longer_shown():
    board = SpeakingBoard()
    board.attach(MARIE.id)

    board.detach(MARIE.id)

    assert board.pairs == ()


def test_setting_a_state_that_is_already_the_state_changes_nothing():
    """Silero reports continuously; the board only has news when something actually moved."""
    board = SpeakingBoard()
    board.set(MARIE.id, human=True, interpreter=False)

    assert board.set(MARIE.id, human=True, interpreter=False) is False


def test_a_real_change_is_news():
    board = SpeakingBoard()
    board.set(MARIE.id, human=True, interpreter=False)

    assert board.set(MARIE.id, human=False, interpreter=False) is True


# ── Colour is never the only carrier ──────────────────────────────────────────


def test_each_state_carries_a_shape_as_well_as_a_colour():
    """UX-DR7. A participant who cannot tell green from red must still be able to read the
    board, so the difference is in the form as well as the hue."""
    assert Voice.ACTIVE.colour != Voice.QUIET.colour
    assert Voice.ACTIVE.shape != Voice.QUIET.shape


def test_the_two_states_are_green_and_red():
    assert Voice.ACTIVE.colour == "green"
    assert Voice.QUIET.colour == "red"


def test_the_shapes_are_distinguishable_without_any_colour_at_all():
    """Printed in black and white, the board still reads."""
    shapes = {Voice.ACTIVE.shape, Voice.QUIET.shape}

    assert len(shapes) == 2
    assert "" not in shapes


# ── Everybody sees everybody ──────────────────────────────────────────────────


async def test_the_board_reaches_every_participant(salon, rooms):
    """The whole point of the indicator: you see the state of all the pairs, not your own."""
    await _join(salon, MARIE)
    await _join(salon, HANS)

    await salon.speaking(MARIE.id, human=True)

    for participant in (MARIE, HANS):
        assert _boards(rooms, await salon.room_of(participant.id)) != []


async def test_the_board_shows_every_pair(salon, rooms):
    await _join(salon, MARIE)
    await _join(salon, HANS)

    await salon.speaking(MARIE.id, human=True)

    (board,) = _boards(rooms, await salon.room_of(HANS.id))
    assert {pair["participant"] for pair in board["pairs"]} == {"marie", "hans"}


async def test_a_participant_sees_their_own_pair_too(salon, rooms):
    """Seeing your own interpreter still red is how you know your last sentence has not
    reached anybody yet."""
    await _join(salon, MARIE)

    await salon.speaking(MARIE.id, human=True)

    (board,) = _boards(rooms, await salon.room_of(MARIE.id))
    assert board["pairs"][0]["participant"] == "marie"


async def test_the_board_carries_both_voices_of_each_pair(salon, rooms):
    await _join(salon, MARIE)

    await salon.speaking(MARIE.id, human=True, interpreter=False)

    (board,) = _boards(rooms, await salon.room_of(MARIE.id))
    (pair,) = board["pairs"]
    assert pair["human"]["colour"] == "green"
    assert pair["interpreter"]["colour"] == "red"
    assert pair["human"]["shape"] != pair["interpreter"]["shape"]


async def test_joining_puts_somebody_on_the_board(salon, rooms):
    await _join(salon, MARIE)

    await _join(salon, HANS)

    await salon.speaking(MARIE.id, human=True)
    (board,) = _boards(rooms, await salon.room_of(MARIE.id))
    assert len(board["pairs"]) == 2


async def test_leaving_takes_somebody_off_it(salon, rooms):
    await _join(salon, MARIE)
    await _join(salon, HANS)

    await salon.leave(HANS.id)
    await salon.speaking(MARIE.id, human=True)

    (board,) = _boards(rooms, await salon.room_of(MARIE.id))
    assert {pair["participant"] for pair in board["pairs"]} == {"marie"}


async def test_nothing_is_sent_when_nothing_changed(salon, rooms):
    """Silero reports continuously. Rebroadcasting an unchanged board to everybody, many
    times a second, would be the most expensive way to say nothing."""
    await _join(salon, MARIE)
    await salon.speaking(MARIE.id, human=True)

    await salon.speaking(MARIE.id, human=True)

    assert len(_boards(rooms, await salon.room_of(MARIE.id))) == 1


async def test_a_state_for_somebody_who_is_not_here_is_ignored(salon, rooms):
    await _join(salon, MARIE)

    await salon.speaking("nobody", human=True)

    assert _boards(rooms, await salon.room_of(MARIE.id)) == []


# ── Who does not get it ───────────────────────────────────────────────────────


async def test_nothing_is_sent_to_somebody_driving(salon, rooms):
    """FR75. The screen is black — there is nothing to look at, which is the whole point of
    the mode. Sending a board to it would be paying to update what nobody can see."""
    await _join(salon, MARIE)
    await _join(salon, HANS)
    await salon.start_driving(HANS.id)

    await salon.speaking(MARIE.id, human=True)

    assert _boards(rooms, await salon.room_of(HANS.id)) == []
    assert _boards(rooms, await salon.room_of(MARIE.id)) != []


async def test_somebody_who_stops_driving_gets_the_board_again(salon, rooms):
    await _join(salon, MARIE)
    await _join(salon, HANS)
    await salon.start_driving(HANS.id)

    await salon.stop_driving(HANS.id)
    await salon.speaking(MARIE.id, human=True)

    assert _boards(rooms, await salon.room_of(HANS.id)) != []


# ── A telephone participant ───────────────────────────────────────────────────


async def test_a_telephone_pair_has_the_same_two_lights(salon, rooms):
    """FR57. No video, so this is the only visual information about them there is — which
    makes leaving them off the board the one thing that would actually hurt."""
    await _join(salon, MARIE)
    await _join(salon, CALLER)

    await salon.speaking(CALLER.id, human=True)

    (board,) = _boards(rooms, await salon.room_of(MARIE.id))
    caller = [p for p in board["pairs"] if p["participant"] == CALLER.id][0]
    assert caller["human"]["colour"] == "green"
    assert caller["interpreter"]["colour"] == "red"


async def test_a_telephone_participant_is_sent_the_board_like_anybody_else(salon, rooms):
    await _join(salon, MARIE)
    await _join(salon, CALLER)

    await salon.speaking(MARIE.id, human=True)

    assert _boards(rooms, await salon.room_of(CALLER.id)) != []


# ── The same channel as everything else ───────────────────────────────────────


async def test_the_board_travels_the_data_channel_not_the_voice(salon):
    """It is something to look at. Saying it out loud would be absurd, and saying it many
    times a second would be unbearable."""
    await _join(salon, MARIE)
    await _join(salon, HANS)

    await salon.speaking(MARIE.id, human=True)

    assert salon.interpreter_of(HANS.id).spoken == []


async def test_a_board_is_distinguishable_from_a_caption(salon, rooms):
    """Both travel the same channel, so a client has to be able to tell them apart without
    guessing: a board is JSON with a `kind`, a caption is the text itself."""
    await _join(salon, MARIE)
    await _join(salon, HANS)
    await salon.set_captions(HANS.id, language="de")

    await salon.ingest(MARIE.id, "Bonjour", language="fr")
    await salon.deliver_all()
    await salon.speaking(MARIE.id, human=True)

    payloads = [p.decode() for p in rooms.published(await salon.room_of(HANS.id))]
    assert "Bonjour [de]" in payloads
    assert len(_boards(rooms, await salon.room_of(HANS.id))) == 1


async def test_the_board_can_be_read_without_waiting_for_a_broadcast(salon):
    """A client reconnecting needs the current state, not the next change to it — otherwise
    it shows an empty board until somebody happens to speak."""
    await _join(salon, MARIE)
    await _join(salon, HANS)
    await salon.speaking(MARIE.id, human=True)

    board = salon.speaking_board

    assert {pair.participant_id for pair in board.pairs} == {"marie", "hans"}
    assert board.as_message()["kind"] == "speaking"
