"""The opening delay is a maximum, not a promise of silence.

Reported from a real session: speaking before the fifteen seconds elapsed got a reply, while
the counter on screen carried on down to zero — so the wait was visibly a fiction. The fix is
not to make the agent ignore whoever spoke; it is to stop pretending anyone is still waiting.
"""
import asyncio

import pytest

from src.opening import OpeningGate


class Spoken:
    """Records openings instead of calling a realtime session."""

    def __init__(self, fail: bool = False) -> None:
        self.count = 0
        self._fail = fail

    def __call__(self) -> None:
        self.count += 1
        if self._fail:
            raise RuntimeError("the session refused")


async def _settle(seconds: float = 0.05) -> None:
    """Let the timer fire. Real delays are seconds; the tests use fractions of one."""
    await asyncio.sleep(seconds)


# ─── The opening itself ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_an_invitation_opens_the_conversation():
    speak = Spoken()
    gate = OpeningGate(speak)
    gate.schedule(0.01)
    assert speak.count == 0, "not before the delay"
    await _settle()
    assert speak.count == 1
    assert gate.spoken


@pytest.mark.asyncio
async def test_inviting_two_people_greets_once():
    """A host inviting a second guest should not be welcomed all over again."""
    speak = Spoken()
    gate = OpeningGate(speak)
    assert gate.schedule(0.01) is True
    assert gate.schedule(0.01) is False, "the second invitation is not a second opening"
    await _settle()
    assert speak.count == 1


@pytest.mark.asyncio
async def test_a_refused_opening_does_not_break_the_session():
    """A session that is otherwise working must survive an opening that fails."""
    speak = Spoken(fail=True)
    gate = OpeningGate(speak)
    gate.schedule(0.01)
    await _settle()
    assert speak.count == 1
    assert gate.spoken, "not retried: an opening is only an opening once"


# ─── Speaking during the wait ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_speaking_first_cancels_the_opening():
    """The bug. Somebody who talks has already broken the silence the wait protected."""
    speak = Spoken()
    gate = OpeningGate(speak)
    gate.schedule(0.05)
    assert gate.stand_down() is True
    await _settle(0.1)
    assert speak.count == 0, "the reply to them is the opening"
    assert gate.spoken


@pytest.mark.asyncio
async def test_no_reply_is_generated_when_standing_down():
    """Deliberate, and the reason the fix is a cancellation rather than a reschedule.

    The session answers speech on its own, and that answer is the first turn — which the
    standing instructions already order as welcome, announcement, then source. Generating a
    second reply on top would have the agent talking over itself.
    """
    speak = Spoken()
    gate = OpeningGate(speak)
    gate.schedule(0.05)
    gate.stand_down()
    await _settle(0.1)
    assert speak.count == 0


@pytest.mark.asyncio
async def test_still_talking_later_does_not_trigger_a_late_greeting():
    """The other half of the report: being greeted after a conversation is under way."""
    speak = Spoken()
    gate = OpeningGate(speak)
    gate.schedule(0.01)
    await _settle()
    assert speak.count == 1
    assert gate.stand_down() is False, "already opened, nothing to stand down"
    await _settle()
    assert speak.count == 1


@pytest.mark.asyncio
async def test_standing_down_twice_settles_it_once():
    """Every finalised transcript calls this; only the first one changes anything."""
    gate = OpeningGate(Spoken())
    gate.schedule(0.05)
    assert gate.stand_down() is True
    assert gate.stand_down() is False


@pytest.mark.asyncio
async def test_speech_with_no_invitation_pending_is_harmless():
    """The ordinary case: a host who talks without having invited anybody."""
    speak = Spoken()
    gate = OpeningGate(speak)
    assert gate.stand_down() is False
    assert not gate.spoken, "nothing was waiting, so nothing was settled"
    # And an invitation afterwards still opens normally.
    gate.schedule(0.01)
    await _settle()
    assert speak.count == 1


@pytest.mark.asyncio
async def test_an_invitation_after_speech_still_opens():
    """Standing down settles the pending wait, not every future one.

    A host who says something, then invites a guest, is back in exactly the situation the
    delay was built for — nothing said, and someone on the way.
    """
    speak = Spoken()
    gate = OpeningGate(speak)
    gate.schedule(0.05)
    gate.stand_down()
    await _settle(0.1)
    assert speak.count == 0
    # A second invitation is refused, because the gate has been spoken for. This is the
    # deliberate trade: at most one automatic opening per session.
    assert gate.schedule(0.01) is False
    await _settle()
    assert speak.count == 0


# ─── Shutdown ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_a_room_that_empties_mid_wait_greets_nobody():
    speak = Spoken()
    gate = OpeningGate(speak)
    gate.schedule(0.05)
    gate.cancel()
    await _settle(0.1)
    assert speak.count == 0
    assert not gate.spoken, "cancelled, not delivered"


@pytest.mark.asyncio
async def test_cancelling_when_nothing_waits_is_not_an_error():
    OpeningGate(Spoken()).cancel()
