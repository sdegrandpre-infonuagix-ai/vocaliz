"""Tests for live captions — attribution, language collection, and the wire format."""
import json
import os
import sys
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from src import captions as cap  # noqa: E402


def _participant(identity, caption_lang=None):
    p = MagicMock()
    p.identity = identity
    p.attributes = {cap.CAPTION_LANGUAGE_ATTRIBUTE: caption_lang} if caption_lang else {}
    return p


def _room(*participants, local_identity="agent"):
    room = MagicMock()
    room.remote_participants = {p.identity: p for p in participants}
    room.local_participant.identity = local_identity
    room.local_participant.publish_data = AsyncMock()
    return room


# ─── Roles from identities ────────────────────────────────────────────────────

def test_guest_identity_yields_guest_role():
    assert cap.speaker_role("guest-3f2a1b4c-0000-0000-0000-000000000000") == "guest"


def test_a_user_id_yields_host_role():
    assert cap.speaker_role("7c9e6679-7425-40de-944b-e07fc1f90ae7") == "host"


def test_the_agent_is_its_own_role():
    assert cap.speaker_role(cap.AGENT_IDENTITY) == "agent"


# ─── Which languages to translate into ────────────────────────────────────────

def test_languages_come_from_participant_attributes():
    room = _room(_participant("a", "fr"), _participant("b", "es"))
    assert cap.requested_languages(room) == ["es", "fr"]


def test_duplicate_languages_are_asked_for_once():
    """Two viewers reading French must not cost two calls to the translator."""
    room = _room(_participant("a", "fr"), _participant("b", "fr"))
    assert cap.requested_languages(room) == ["fr"]


def test_participants_reading_nothing_ask_for_nothing():
    room = _room(_participant("a"), _participant("b", "   "))
    assert cap.requested_languages(room) == []


def test_languages_are_sorted_so_the_same_room_asks_the_same_way():
    room = _room(_participant("a", "pt"), _participant("b", "de"), _participant("c", "fr"))
    assert cap.requested_languages(room) == ["de", "fr", "pt"]


# ─── Attribution ──────────────────────────────────────────────────────────────

def _publisher(room):
    return cap.CaptionPublisher(room, "https://api.test", "sess-1", "token")


def test_a_lone_participant_is_the_speaker():
    """The common case, and the one where a guess cannot be wrong."""
    room = _room(_participant("guest-abc"))
    assert _publisher(room).attributed_speaker() == "guest-abc"


def test_the_last_active_speaker_is_used_when_several_are_present():
    """A finalised transcript arrives after the speaker stopped, so active_speakers is
    already empty by then — the last one heard has to be remembered."""
    room = _room(_participant("host-1"), _participant("guest-abc"))
    publisher = _publisher(room)
    publisher._last_speaker = "guest-abc"
    assert publisher.attributed_speaker() == "guest-abc"


def test_attribution_never_returns_nothing():
    """A caption attributed to nobody is still worth showing."""
    assert _publisher(_room()).attributed_speaker() == "unknown"


def test_the_agent_is_never_attributed_a_participant_turn():
    """The local participant speaking must not be recorded as someone in the room."""
    room = _room(_participant("guest-abc"), local_identity="agent")
    publisher = _publisher(room)
    handler = {}
    room.on.side_effect = lambda event, fn: handler.__setitem__(event, fn)
    publisher.track_active_speakers()

    agent_speaking = MagicMock()
    agent_speaking.identity = "agent"
    handler["active_speakers_changed"]([agent_speaking])
    assert publisher._last_speaker is None


# ─── What goes on the wire ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_a_caption_carries_the_spoken_text_and_its_translations(monkeypatch):
    room = _room(_participant("guest-abc", "fr"))
    publisher = _publisher(room)

    response = MagicMock()
    response.status_code = 201
    response.json.return_value = {
        "sequence": 4,
        "speaker": "Guest 3F2A",
        "role": "guest",
        "text": "Necesito el informe.",
        "language": "es",
        "translations": {"fr": "J'ai besoin du rapport."},
        "spokenAt": "2026-08-03T12:00:00+00:00",
    }
    client = AsyncMock()
    client.post.return_value = response
    monkeypatch.setattr(
        cap.httpx, "AsyncClient", lambda **_: MagicMock(
            __aenter__=AsyncMock(return_value=client), __aexit__=AsyncMock(return_value=False)
        )
    )

    await publisher.publish(text="Necesito el informe.", identity="guest-abc", language="es")

    payload = json.loads(room.local_participant.publish_data.await_args.args[0].decode())
    assert payload["type"] == "caption"
    assert payload["text"] == "Necesito el informe."
    assert payload["translations"] == {"fr": "J'ai besoin du rapport."}
    assert payload["speaker"] == "Guest 3F2A"
    assert room.local_participant.publish_data.await_args.kwargs["topic"] == cap.CAPTION_TOPIC


@pytest.mark.asyncio
async def test_a_speaker_name_is_passed_through_to_the_api(monkeypatch):
    """The agent already holds this from the room — LiveKit's own display name, or the
    literal "Salon" for a line spoken on somebody's behalf — and sends it rather than
    letting the API's own anonymised guess decide the label."""
    room = _room(_participant("guest-abc", "fr"))
    publisher = _publisher(room)

    response = MagicMock()
    response.status_code = 201
    response.json.return_value = {
        "sequence": 1, "speaker": "Marie", "role": "guest", "text": "Bonjour.",
        "language": "fr", "translations": {}, "spokenAt": None,
    }
    client = AsyncMock()
    client.post.return_value = response
    monkeypatch.setattr(
        cap.httpx, "AsyncClient", lambda **_: MagicMock(
            __aenter__=AsyncMock(return_value=client), __aexit__=AsyncMock(return_value=False)
        )
    )

    await publisher.publish(text="Bonjour.", identity="guest-abc", speaker_name="Marie")

    sent = client.post.await_args.kwargs["json"]
    assert sent["speakerName"] == "Marie"


@pytest.mark.asyncio
async def test_no_speaker_name_is_sent_when_none_is_given(monkeypatch):
    """Every existing caller — nothing here changed for them — must keep sending exactly
    what it always has, which display_label reads as "nobody supplied one"."""
    room = _room(_participant("guest-abc", "fr"))
    publisher = _publisher(room)

    response = MagicMock()
    response.status_code = 201
    response.json.return_value = {
        "sequence": 1, "speaker": "Guest 3F2A", "role": "guest", "text": "Bonjour.",
        "language": "fr", "translations": {}, "spokenAt": None,
    }
    client = AsyncMock()
    client.post.return_value = response
    monkeypatch.setattr(
        cap.httpx, "AsyncClient", lambda **_: MagicMock(
            __aenter__=AsyncMock(return_value=client), __aexit__=AsyncMock(return_value=False)
        )
    )

    await publisher.publish(text="Bonjour.", identity="guest-abc")

    assert client.post.await_args.kwargs["json"]["speakerName"] is None


@pytest.mark.asyncio
async def test_blank_speech_is_not_published(monkeypatch):
    room = _room(_participant("guest-abc", "fr"))
    await _publisher(room).publish(text="   ", identity="guest-abc")
    room.local_participant.publish_data.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_failed_store_publishes_nothing(monkeypatch):
    """Better no caption than one the transcript does not contain."""
    room = _room(_participant("guest-abc", "fr"))

    response = MagicMock()
    response.status_code = 500
    client = AsyncMock()
    client.post.return_value = response
    monkeypatch.setattr(
        cap.httpx, "AsyncClient", lambda **_: MagicMock(
            __aenter__=AsyncMock(return_value=client), __aexit__=AsyncMock(return_value=False)
        )
    )

    await _publisher(room).publish(text="Hola.", identity="guest-abc")
    room.local_participant.publish_data.assert_not_awaited()


@pytest.mark.asyncio
async def test_an_api_outage_does_not_raise(monkeypatch):
    """A caption failing must never interrupt the conversation it describes."""
    room = _room(_participant("guest-abc", "fr"))
    monkeypatch.setattr(
        cap.httpx, "AsyncClient", lambda **_: MagicMock(
            __aenter__=AsyncMock(side_effect=OSError("network down")),
            __aexit__=AsyncMock(return_value=False),
        )
    )
    await _publisher(room).publish(text="Hola.", identity="guest-abc")
    room.local_participant.publish_data.assert_not_awaited()
