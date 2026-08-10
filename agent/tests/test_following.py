"""Saying what the orchestrator says is owed.

The assertion this file exists for is the cost one: **a line already in the listener's
language never reaches the model.** Handing it over would pay for a translation into the
language it is already in, on every turn of every conversation, and it is the same reason a
Salon's price follows the number of languages in it rather than its length.

The rest is about survival. This loop holds a live room, so nothing in it may raise: a
delivery that fails costs the rest of one batch, never the conversation.
"""
import asyncio
from dataclasses import dataclass, field

import pytest

from src.following import deliver, deliver_script, follow
from src.orchestrator_link import Line


@dataclass
class FakeVoice:
    """An interpreter that writes down which of the two paths it was sent down."""

    spoken: list[str] = field(default_factory=list)
    rendered: list[Line] = field(default_factory=list)
    fail_with: Exception | None = None

    async def say(self, text: str) -> None:
        if self.fail_with:
            raise self.fail_with
        self.spoken.append(text)

    async def render(self, line: Line) -> None:
        if self.fail_with:
            raise self.fail_with
        self.rendered.append(line)


@dataclass
class FakeLink:
    scripts: list[list[Line]] = field(default_factory=list)
    configured: bool = True
    asks: int = 0

    async def script(self) -> list[Line]:
        self.asks += 1
        return self.scripts.pop(0) if self.scripts else []


def _tour(text="Guten Tag", source="de", target="fr"):
    return Line(kind="tour", text=text, language=target, source_language=source)


def _annonce(text="Hans arrive", language="fr"):
    return Line(kind="annonce", text=text, language=language, source_language=language)


# ── Which path a line takes, and what it costs ────────────────────────────────


@pytest.mark.asyncio
async def test_a_line_in_the_listeners_own_language_never_reaches_the_model():
    """The cost assertion. A verbatim line is spoken as it stands: no model call, no
    translation, no latency — and no bill for translating French into French."""
    voice = FakeVoice()

    await deliver(_annonce(), voice)

    assert voice.spoken == ["Hans arrive"]
    assert voice.rendered == []


@pytest.mark.asyncio
async def test_a_line_in_somebody_elses_language_goes_to_the_model():
    """Translated and spoken in one movement, never a translation followed by a separate
    reading — which would double the latency and lose the prosody of the original."""
    voice = FakeVoice()

    await deliver(_tour(), voice)

    assert voice.rendered == [_tour()]
    assert voice.spoken == []


@pytest.mark.asyncio
async def test_a_condensation_goes_to_the_model_whatever_it_covers():
    """An interval spoken in several languages has no single one, so it can never be
    verbatim."""
    voice = FakeVoice()

    await deliver(Line(kind="condensation", text="eins dau", language="fr"), voice)

    assert len(voice.rendered) == 1


# ── One delivery ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_everything_in_a_script_is_said_in_order():
    voice = FakeVoice()
    link = FakeLink(scripts=[[_annonce("Hans arrive"), _tour("Guten Tag")]])

    assert await deliver_script(link, voice) == 2
    assert voice.spoken == ["Hans arrive"]
    assert voice.rendered[0].text == "Guten Tag"


@pytest.mark.asyncio
async def test_a_line_that_cannot_be_said_costs_the_rest_of_that_batch_and_no_more():
    """The reading position has already moved — the orchestrator advanced it when it handed
    the script over — so what is lost is what was left in this batch. Raising instead would
    take down the loop, and with it every later line as well."""
    voice = FakeVoice(fail_with=RuntimeError("the model hung up"))
    link = FakeLink(scripts=[[_annonce(), _tour()]])

    assert await deliver_script(link, voice) == 0  # nothing said, nothing raised


# ── The loop ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_the_loop_keeps_asking_until_it_is_told_to_stop():
    voice = FakeVoice()
    link = FakeLink(scripts=[[_tour()], [_annonce()]])
    stop = asyncio.Event()

    async def sleep(_seconds):
        # Stop after the second round, which is what makes this terminate at all.
        if link.asks >= 2:
            stop.set()

    await follow(link, voice, stop=stop, sleep=sleep)

    assert link.asks == 2
    assert len(voice.rendered) == 1 and len(voice.spoken) == 1


@pytest.mark.asyncio
async def test_a_stop_asked_for_during_the_wait_is_honoured_at_the_next_turn():
    """Rather than a full interval later, which matters at teardown — the room is going away
    underneath this loop."""
    link = FakeLink(scripts=[[]])
    stop = asyncio.Event()

    async def sleep(_seconds):
        stop.set()

    await follow(link, FakeVoice(), stop=stop, sleep=sleep)

    assert link.asks == 1


@pytest.mark.asyncio
async def test_an_agent_with_no_orchestrator_does_not_spin():
    """Inert rather than broken: it runs the conversation it can — one room, one human —
    instead of asking an address that does not exist, four times a second."""
    link = FakeLink(configured=False)

    await follow(link, FakeVoice(), stop=asyncio.Event())

    assert link.asks == 0


@pytest.mark.asyncio
async def test_a_wake_already_set_does_not_stop_the_ordinary_ask():
    """However the race between the interval and the wake resolves, the loop still asks
    again on its own — this is a fast path, never a second way to skip asking."""
    voice = FakeVoice()
    link = FakeLink(scripts=[[], [_tour()]])
    stop = asyncio.Event()
    wake = asyncio.Event()
    wake.set()  # already owed something before the loop ever waits

    async def sleep(_seconds):
        if link.asks >= 2:
            stop.set()

    await follow(link, voice, stop=stop, sleep=sleep, wake=wake)

    assert link.asks == 2


# ── The wake itself ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_an_already_set_wake_returns_without_waiting_out_the_interval():
    from src.following import _wait

    wake = asyncio.Event()
    wake.set()

    # A generous interval and a plain asyncio.sleep behind it: if the wake did not win the
    # race, this test would be the one left waiting five seconds for nothing.
    await asyncio.wait_for(_wait(5.0, asyncio.sleep, wake), timeout=1.0)


@pytest.mark.asyncio
async def test_the_wake_is_cleared_once_it_has_done_its_job():
    """Left set, it would short-circuit every later wait for no reason — a fast path is not
    a standing instruction to never wait again."""
    from src.following import _wait

    wake = asyncio.Event()
    wake.set()

    await _wait(5.0, asyncio.sleep, wake)

    assert not wake.is_set()


@pytest.mark.asyncio
async def test_no_wake_argument_is_a_plain_sleep():
    """Every caller from before this existed passes none, and must see no change at all."""
    from src.following import _wait

    calls = []

    async def sleep(seconds):
        calls.append(seconds)

    await _wait(2.5, sleep, None)

    assert calls == [2.5]


@pytest.mark.asyncio
async def test_a_wake_that_never_comes_still_falls_through_to_the_interval():
    from src.following import _wait

    wake = asyncio.Event()
    calls = []

    async def sleep(seconds):
        calls.append(seconds)

    await _wait(0.01, sleep, wake)

    assert calls == [0.01]
    assert not wake.is_set()


@pytest.mark.asyncio
async def test_the_loop_slows_down_rather_than_dying_when_something_goes_wrong():
    """This task holds a live room. An agent retrying at full speed against a service that is
    restarting is how one outage becomes two."""
    from src.following import BACKOFF_SECONDS

    voice = FakeVoice()
    stop = asyncio.Event()
    waits: list[float] = []

    class Broken(FakeLink):
        async def script(self):
            self.asks += 1
            raise RuntimeError("something the link did not catch")

    link = Broken()

    async def sleep(seconds):
        waits.append(seconds)
        stop.set()

    await follow(link, voice, stop=stop, sleep=sleep)

    assert waits == [BACKOFF_SECONDS]
