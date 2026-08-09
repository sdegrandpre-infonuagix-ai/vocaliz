"""Driving mode, from the orchestrator's side.

The screen, the wake lock and the touch targets are the client's business and are built in
`mobile/src/components/DrivingMode.tsx`. What belongs here is the consequence of the screen
being black: three things that exist only to be looked at are suspended, and one of them
costs money.

That one is the captions. Nobody is reading, so nothing should be translated — and a
translation is paid for per turn. Emptying the caption language for the duration is not
tidiness, it is the difference between paying and not paying for turns this participant
will never see. The previous choice comes back on the way out, because they did not choose
to stop reading; they chose to start driving.
"""
import json

import pytest

from src.interprete import InterpreteFake, Participant
from src.journal import InMemoryJournalStore, SalonLog
from src.salon import AS_SPOKEN, InMemoryRoomProvisioner, InMemoryVideoPath, Salon

MARIE = Participant(id="marie", language="fr", name="Marie")
HANS = Participant(id="hans", language="de", name="Hans")


async def translate(text, *, source, target):
    return f"{text} [{target}]"


@pytest.fixture
def rooms():
    return InMemoryRoomProvisioner()


@pytest.fixture
def salon(rooms):
    log = SalonLog(salon_id="salon-1", store=InMemoryJournalStore(), translate=translate)
    return Salon(log=log, rooms=rooms, video=InMemoryVideoPath())


async def _join(salon, participant, **kwargs):
    return await salon.join(participant, InterpreteFake(participant=participant), **kwargs)


def _payloads(rooms, room):
    return [p.decode() for p in rooms.published(room)]


def _boards(rooms, room):
    out = []
    for payload in _payloads(rooms, room):
        try:
            message = json.loads(payload)
        except ValueError:
            continue
        if message.get("kind") == "speaking":
            out.append(message)
    return out


# ── The three visual things stop ──────────────────────────────────────────────


async def test_driving_suspends_the_video(salon):
    await _join(salon, MARIE)
    await salon.enable_video(MARIE.id)

    await salon.start_driving(MARIE.id)

    assert salon.video_on(MARIE.id) is False
    assert salon.receives_video(MARIE.id) is False


async def test_driving_suspends_the_captions(salon, rooms):
    """The one with a price on it. Nobody is reading, so nothing is translated — and a
    translation is billed per turn."""
    await _join(salon, MARIE)
    await _join(salon, HANS)
    await salon.set_captions(HANS.id, language="de")

    await salon.start_driving(HANS.id)
    await salon.ingest(MARIE.id, "Bonjour", language="fr")
    await salon.deliver_all()

    assert salon.caption_language(HANS.id) is None
    assert _payloads(rooms, await salon.room_of(HANS.id)) == []


async def test_driving_suspends_the_speaking_indicators(salon, rooms):
    await _join(salon, MARIE)
    await _join(salon, HANS)

    await salon.start_driving(HANS.id)
    await salon.speaking(MARIE.id, human=True)

    assert _boards(rooms, await salon.room_of(HANS.id)) == []


async def test_nothing_is_translated_for_somebody_who_is_driving(salon):
    """The billing consequence, asserted directly: the translator is never asked."""
    calls = []

    async def counted(text, *, source, target):
        calls.append(target)
        return f"{text} [{target}]"

    log = SalonLog(salon_id="s", store=InMemoryJournalStore(), translate=counted)
    driving = Salon(log=log, rooms=InMemoryRoomProvisioner())
    await driving.join(MARIE, InterpreteFake(participant=MARIE))
    await driving.join(HANS, InterpreteFake(participant=HANS))
    await driving.set_captions(HANS.id, language="es")

    await driving.start_driving(HANS.id)
    await driving.ingest(MARIE.id, "Bonjour", language="fr")
    await driving.deliver_all()

    assert "es" not in calls


# ── The voice carries on underneath ───────────────────────────────────────────


async def test_the_conversation_is_unchanged(salon):
    """The screen replaces the room; it does not replace the Salon. Somebody driving is
    still fully in the conversation — that is the entire point of the mode."""
    await _join(salon, MARIE)
    await _join(salon, HANS)
    await salon.start_driving(HANS.id)

    await salon.ingest(MARIE.id, "Bonjour", language="fr")
    await salon.deliver_all()

    tours = [line for line in salon.interpreter_of(HANS.id).spoken if line.kind == "tour"]
    assert [line.text for line in tours] == ["Bonjour"]


async def test_somebody_driving_can_still_speak(salon):
    await _join(salon, MARIE)
    await _join(salon, HANS)
    await salon.start_driving(HANS.id)

    recorded = await salon.ingest(HANS.id, "Ich fahre", language="de")

    assert [entry.text for entry in recorded] == ["Ich fahre"]


async def test_somebody_driving_is_still_announced_to(salon):
    """Announcements are spoken, not shown. A black screen is not a reason to stop being
    told that somebody has joined."""
    from src.interprete import Annonce

    await _join(salon, MARIE)
    await salon.start_driving(MARIE.id)

    await salon.announce(MARIE.id, Annonce(text="Hans a rejoint", language="fr"))

    assert [line.kind for line in salon.interpreter_of(MARIE.id).spoken] == ["annonce"]


# ── Coming back out ───────────────────────────────────────────────────────────


async def test_the_caption_choice_comes_back(salon):
    """They did not choose to stop reading; they chose to start driving."""
    await _join(salon, MARIE)
    await salon.set_captions(MARIE.id, language="de", scale=1.5)

    await salon.start_driving(MARIE.id)
    await salon.stop_driving(MARIE.id)

    assert salon.caption_language(MARIE.id) == "de"
    assert salon.caption_scale(MARIE.id) == 1.5


async def test_as_spoken_comes_back_as_as_spoken(salon):
    """`""` is a choice, and restoring it as `None` would quietly turn captions off for
    somebody who had asked to read the original."""
    await _join(salon, MARIE)
    await salon.set_captions(MARIE.id, language=AS_SPOKEN)

    await salon.start_driving(MARIE.id)
    await salon.stop_driving(MARIE.id)

    assert salon.caption_language(MARIE.id) == AS_SPOKEN


async def test_somebody_who_never_read_captions_does_not_start(salon):
    await _join(salon, MARIE)

    await salon.start_driving(MARIE.id)
    await salon.stop_driving(MARIE.id)

    assert salon.caption_language(MARIE.id) is None


async def test_a_choice_made_while_driving_is_the_one_that_survives(salon):
    """Somebody who reaches for the setting during a red light meant it. Restoring what was
    there before would overwrite a decision with an older one."""
    await _join(salon, MARIE)
    await salon.set_captions(MARIE.id, language="de")
    await salon.start_driving(MARIE.id)

    await salon.set_captions(MARIE.id, language="es")
    await salon.stop_driving(MARIE.id)

    assert salon.caption_language(MARIE.id) == "es"


async def test_the_video_comes_back_and_the_indicators_with_it(salon, rooms):
    await _join(salon, MARIE)
    await _join(salon, HANS)
    await salon.enable_video(HANS.id)
    await salon.start_driving(HANS.id)

    await salon.stop_driving(HANS.id)
    await salon.speaking(MARIE.id, human=True)

    assert salon.video_on(HANS.id) is True
    assert _boards(rooms, await salon.room_of(HANS.id)) != []


async def test_driving_twice_does_not_lose_the_choice(salon):
    """A mode that is entered twice — a stop and a start — must not save the emptied state
    over the real one."""
    await _join(salon, MARIE)
    await salon.set_captions(MARIE.id, language="de")

    await salon.start_driving(MARIE.id)
    await salon.start_driving(MARIE.id)
    await salon.stop_driving(MARIE.id)

    assert salon.caption_language(MARIE.id) == "de"


async def test_leaving_while_driving_is_ordinary(salon):
    await _join(salon, MARIE)
    await salon.start_driving(MARIE.id)

    await salon.leave(MARIE.id)

    assert salon.participants == ()
