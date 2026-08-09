"""The agent's end of the text-only boundary.

What crosses is text: a sentence out, an ordered list of lines back. The interpreter that
turns those lines into speech sits in this process, beside the microphone, which is the whole
reason the boundary was drawn where it was.

Two properties carry most of this file. **A turn keeps the language it was said in** — a
realtime model translates and speaks in one movement, and handing it a string somebody else
already translated throws away the thing that makes speech-to-speech worth paying for. And
**nothing here raises into a conversation**: a Salon whose orchestrator has gone quiet is a
Salon where translation stops, not one that ends.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.orchestrator_link import Line, OrchestratorLink, _line_from_json

BASE = "http://orchestrator.vocaliz.internal:8080"


def _link(base=BASE, language="fr"):
    return OrchestratorLink(
        base_url=base, salon_id="salon-1", participant_id="marie", language=language
    )


def _answers(status=200, payload=None):
    """An aiohttp session whose one request answers with this, and records the call."""
    response = MagicMock()
    response.status = status
    response.json = AsyncMock(return_value=payload or {})
    response.__aenter__ = AsyncMock(return_value=response)
    response.__aexit__ = AsyncMock(return_value=False)

    session = MagicMock()
    session.request = MagicMock(return_value=response)
    session.delete = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    return session


# ── Reporting what a human said ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_what_the_human_said_reaches_the_journal():
    session = _answers(payload={"recorded": 1, "sequences": [7]})

    with patch("aiohttp.ClientSession", return_value=session):
        assert await _link().report("Bonjour à tous") == 1

    method, url = session.request.call_args.args
    assert method == "POST"
    assert url == f"{BASE}/salons/salon-1/participants/marie/utterances"
    assert session.request.call_args.kwargs["json"]["text"] == "Bonjour à tous"


@pytest.mark.asyncio
async def test_a_long_intervention_is_reported_as_the_several_messages_it_became():
    """Cut so that nobody waits for the end of it, which is why the count is the useful
    answer rather than an acknowledgement."""
    session = _answers(payload={"recorded": 3, "sequences": [7, 8, 9]})

    with patch("aiohttp.ClientSession", return_value=session):
        assert await _link().report("..." * 400) == 3


@pytest.mark.asyncio
async def test_nothing_recorded_is_an_ordinary_answer():
    """A cut microphone, or a room that has fallen too far behind. Not a failure — the
    orchestrator decided, and this agent goes on holding a room with a human in it."""
    session = _answers(payload={"recorded": 0, "sequences": []})

    with patch("aiohttp.ClientSession", return_value=session):
        assert await _link().report("Bonjour") == 0


@pytest.mark.asyncio
async def test_silence_is_never_reported():
    """Whitespace is what arrives when somebody clears their throat. A journal entry for it
    would burn a sequence number and make every other agent say nothing, out loud."""
    with patch("aiohttp.ClientSession") as session:
        assert await _link().report("   ") == 0

    session.assert_not_called()


# ── Asking what is owed ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_a_turn_arrives_with_both_languages():
    """The property the whole boundary rests on. `de` is what it is in; `fr` is what to say
    it in; the model does both in one movement."""
    session = _answers(
        payload={
            "lines": [
                {
                    "kind": "tour",
                    "language": "fr",
                    "tour": {
                        "participantId": "hans",
                        "text": "Guten Tag",
                        "language": "de",
                        "sequence": 4,
                    },
                }
            ]
        }
    )

    with patch("aiohttp.ClientSession", return_value=session):
        [line] = await _link().script()

    assert (line.text, line.source_language, line.language) == ("Guten Tag", "de", "fr")
    assert line.speaker_id == "hans"
    assert line.sequence == 4
    assert line.verbatim is False


@pytest.mark.asyncio
async def test_an_announcement_needs_no_translation():
    """Composed in the listener's language by the orchestrator, so there is nothing left to
    translate — and a verbatim line costs no model call at all, which is why the price of a
    Salon follows the number of languages in it rather than its length."""
    session = _answers(
        payload={"lines": [{"kind": "annonce", "language": "fr", "text": "Hans arrive"}]}
    )

    with patch("aiohttp.ClientSession", return_value=session):
        [line] = await _link().script()

    assert line.text == "Hans arrive"
    assert line.verbatim is True


@pytest.mark.asyncio
async def test_a_condensation_can_never_be_verbatim():
    """An interval spoken in several languages has no single one, so there is nothing for the
    listener's language to agree with."""
    session = _answers(
        payload={
            "lines": [
                {
                    "kind": "condensation",
                    "language": "fr",
                    "covers": [
                        {"text": "eins", "language": "de"},
                        {"text": "dau", "language": "cy"},
                    ],
                }
            ]
        }
    )

    with patch("aiohttp.ClientSession", return_value=session):
        [line] = await _link().script()

    assert line.text == "eins dau"
    assert line.verbatim is False


@pytest.mark.asyncio
async def test_a_line_this_version_cannot_say_is_skipped_and_the_rest_still_said():
    """One line missing from one delivery, rather than a whole script lost. An orchestrator
    that learns a new kind before this agent is redeployed is the ordinary shape of a rolling
    deploy, not an error."""
    session = _answers(
        payload={
            "lines": [
                {"kind": "hologram", "language": "fr"},
                {"kind": "annonce", "language": "fr", "text": "Hans arrive"},
            ]
        }
    )

    with patch("aiohttp.ClientSession", return_value=session):
        lines = await _link().script()

    assert [line.text for line in lines] == ["Hans arrive"]


@pytest.mark.asyncio
async def test_an_empty_script_is_the_ordinary_case():
    """Most of the time nobody has said anything since the last ask."""
    session = _answers(payload={"lines": []})

    with patch("aiohttp.ClientSession", return_value=session):
        assert await _link().script() == []


# ── When the orchestrator is not there ────────────────────────────────────────


@pytest.mark.asyncio
async def test_an_unreachable_orchestrator_stops_translation_and_not_the_salon():
    """The property that matters most in this file. A room with a human in it must survive a
    second service restarting."""
    session = _answers()
    session.request.side_effect = OSError("connection refused")

    with patch("aiohttp.ClientSession", return_value=session):
        assert await _link().script() == []
        assert await _link().report("Bonjour") == 0


@pytest.mark.asyncio
async def test_a_refusal_is_survived_like_any_other_failure():
    session = _answers(status=503)

    with patch("aiohttp.ClientSession", return_value=session):
        assert await _link().script() == []


@pytest.mark.asyncio
async def test_no_address_means_no_request_at_all():
    """Inert rather than broken: an agent given no orchestrator runs the conversation it can
    — one room, one human — instead of failing to start."""
    link = _link(base="")

    with patch("aiohttp.ClientSession") as session:
        assert link.configured is False
        assert await link.script() == []
        assert await link.report("Bonjour") == 0
        await link.leave()

    session.assert_not_called()


@pytest.mark.asyncio
async def test_leaving_never_raises_during_teardown():
    """This runs while the room is closing, where there is nothing left to handle an
    exception."""
    session = _answers()
    session.delete.side_effect = OSError("gone")

    with patch("aiohttp.ClientSession", return_value=session):
        await _link().leave()  # must not raise


# ── The wire form, read directly ──────────────────────────────────────────────


def test_a_missing_language_falls_back_to_the_listeners_own():
    line = _line_from_json({"kind": "annonce", "text": "Bonjour"}, "fr")

    assert line.language == "fr"


def test_a_verbatim_line_is_one_whose_two_languages_agree():
    assert Line(kind="tour", text="x", language="fr", source_language="fr").verbatim
    assert not Line(kind="tour", text="x", language="fr", source_language="de").verbatim
    # No source language at all is not verbatim: nothing is known about what it is in.
    assert not Line(kind="tour", text="x", language="fr").verbatim
