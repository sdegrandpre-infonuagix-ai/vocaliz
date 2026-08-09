"""The orchestrator over HTTP: text in, text out.

What these tests hold to account is the round trip the product actually runs on. The API
creates the host's LiveKit room and the Salon in one breath and says so here; the host adds
up to two more humans, each with their own interpreter in their own room; then each agent
asks what it owes its human and reports what its human said.

The property worth stating, because it is the one the topology exists for: **no audio
crosses this surface in either direction.** What one person says arrives as text and leaves
as text, in somebody else's language, and the only thing that ever touched sound is the
agent at each end.
"""
import pytest
from fastapi.testclient import TestClient

from src.config import Settings
from src.journal import InMemoryJournalStore, SalonLog
from src.main import create_app
from src.salon import InMemoryRoomProvisioner, Salon
from src.settings import InMemorySettingsStore

SETTINGS = Settings(
    livekit_url="ws://localhost:7880",
    livekit_api_key="devkey",
    livekit_api_secret="a-secret-nobody-should-see",
    database_url="postgresql://salon:hunter2@aurora:5432/salon",
    environment="test",
)


async def _translate(text, *, source, target):
    return f"{text} [{target}]"


@pytest.fixture
def client():
    """An application wired to memory rather than to a database and a LiveKit project.

    Exactly the seam `salon_factory` exists for. The composition root in `app.py` supplies
    the real one; here the conversations are real and everything under them is not, which is
    what lets the whole surface be exercised in milliseconds.
    """
    rooms = InMemoryRoomProvisioner()
    # One store across every Salon this application hosts, as in production. A store per
    # build would make every takeover look like a brand-new conversation, which is exactly
    # the bug `test_hosting_a_salon_that_already_has_a_history` exists to catch.
    store = InMemoryJournalStore()

    async def factory(**_):
        async def build(salon_id: str) -> Salon:
            log = await SalonLog.resume(
                salon_id=salon_id, store=store, translate=_translate
            )
            return Salon(log=log, rooms=rooms)

        return build

    application = create_app(
        settings=SETTINGS,
        settings_store=InMemorySettingsStore(),
        salon_factory=factory,
    )
    with TestClient(application) as client:
        yield client
        registry = application.state.registry
        for salon_id in registry.hosted:
            registry.release(salon_id)


def _host(client, salon_id="salon-1"):
    return client.put(
        f"/salons/{salon_id}",
        json={"livekitRoomName": "vocaliz-abc123", "hostId": "marie"},
    )


def _join(client, participant_id, language, salon_id="salon-1", **extra):
    return client.post(
        f"/salons/{salon_id}/participants",
        json={"participantId": participant_id, "language": language, **extra},
    )


def _say(client, participant_id, text, language, salon_id="salon-1"):
    return client.post(
        f"/salons/{salon_id}/participants/{participant_id}/utterances",
        json={"text": text, "language": language},
    )


def _script(client, participant_id, salon_id="salon-1"):
    return client.get(f"/salons/{salon_id}/participants/{participant_id}/script")


# ── Hosting ───────────────────────────────────────────────────────────────────


def test_the_api_says_which_salon_this_instance_holds(client):
    response = _host(client)

    assert response.status_code == 200
    assert response.json()["hosted"] is True


def test_hosting_the_same_salon_twice_keeps_the_conversation(client):
    """The API creates the room and the Salon in one breath, so a retried request is
    ordinary. Building a second Salon over the first would silently drop everything said so
    far — which nobody would see until somebody asked what they had missed."""
    _host(client)
    _join(client, "marie", "fr")
    _join(client, "hans", "de")
    _say(client, "hans", "Guten Tag", "de")

    _host(client)

    lines = _script(client, "marie").json()["lines"]
    assert any(line.get("tour", {}).get("text") == "Guten Tag" for line in lines)


def test_an_instance_on_its_way_out_refuses_a_new_salon(client):
    """503 rather than 500, so the API tries another instance. Taking a Salon while draining
    means dropping it minutes later."""
    client.app.state.registry.begin_drain()

    assert _host(client, "salon-2").status_code == 503


def test_a_salon_this_instance_does_not_hold_is_not_found(client):
    assert _script(client, "marie", salon_id="somewhere-else").status_code == 404


# ── The host, then two more ───────────────────────────────────────────────────


def test_a_human_joins_and_is_given_their_own_room(client):
    """One human and one interpreter per room, so the room is named for the pair. Derived
    from the Salon and the participant rather than stored: an instance taking this Salon
    over can name it again from what it already has."""
    _host(client)

    response = _join(client, "marie", "fr", name="Marie")

    assert response.status_code == 201
    assert response.json()["roomName"] == "salon-1--marie"


def test_the_host_can_add_two_more_humans_each_in_their_own_room(client):
    """A SALON is up to three pairs. What makes echo unavailable rather than cancelled is
    that no two of these room names are ever the same."""
    _host(client)

    rooms = {
        _join(client, who, language).json()["roomName"]
        for who, language in (("marie", "fr"), ("hans", "de"), ("rhys", "cy"))
    }

    assert len(rooms) == 3


def test_nobody_sends_an_interpreter_and_none_is_accepted(client):
    """The boundary, stated as an absence. A participant's interpreter lives in their agent,
    beside their audio, and there is no field here that could carry one."""
    from src.serving import JoinRequest

    assert "interpreter" not in JoinRequest.model_fields


# ── The conversation itself ───────────────────────────────────────────────────


def test_what_one_human_says_reaches_another_as_text_in_their_language(client):
    """The round trip, and the whole product in one assertion. Hans speaks German into his
    own room; Marie's agent is handed the words to say to her, still marked as German so its
    interpreter can translate and speak them in one movement."""
    _host(client)
    _join(client, "marie", "fr")
    _join(client, "hans", "de")

    _say(client, "hans", "Guten Tag", "de")
    lines = _script(client, "marie").json()["lines"]

    [turn] = [line for line in lines if line["kind"] == "tour"]
    assert turn["tour"]["text"] == "Guten Tag"
    assert turn["tour"]["language"] == "de"  # what it is in
    assert turn["language"] == "fr"  # what to say it in


def test_reporting_what_was_said_answers_with_what_it_became(client):
    """A long intervention is cut into several messages so nobody waits for the end of it,
    so the count is the useful answer rather than an acknowledgement."""
    _host(client)
    _join(client, "hans", "de")

    body = _say(client, "hans", "Guten Tag", "de").json()

    assert body["recorded"] == 1
    assert body["sequences"] == [1]


def test_nobody_is_served_their_own_words(client):
    _host(client)
    _join(client, "marie", "fr")
    _say(client, "marie", "Bonjour", "fr")

    lines = _script(client, "marie").json()["lines"]

    assert [line for line in lines if line["kind"] == "tour"] == []


def test_a_script_is_handed_over_once(client):
    """The reading position moves when the script is handed over. Hearing a sentence twice
    is worse than hearing it late — a listener cannot tell a repeat from somebody saying the
    same thing again."""
    _host(client)
    _join(client, "marie", "fr")
    _join(client, "hans", "de")
    _say(client, "hans", "Guten Tag", "de")

    first = _script(client, "marie").json()["lines"]
    second = _script(client, "marie").json()["lines"]

    assert first != []
    assert second == []


def test_somebody_arriving_is_told_who_is_already_here(client):
    """Story 6.9, over the wire. Nobody has spoken since Rhys arrived, so there is no seam
    to say it at — without the flush at the end of a script it would wait for a stranger to
    speak before Rhys was told whose voice they were hearing."""
    _host(client)
    _join(client, "marie", "fr", name="Marie")
    _say(client, "marie", "Bonjour", "fr")
    _join(client, "rhys", "cy", name="Rhys")

    lines = _script(client, "rhys").json()["lines"]

    assert any("Marie" in line.get("text", "") for line in lines)


def test_somebody_with_no_name_is_not_announced_by_one(client):
    """Names are optional over the wire and a missing one is not invented. An introduction
    that says nothing useful is worse than none — and a guest who joined by telephone with
    no account has nothing to be called."""
    _host(client)
    _join(client, "marie", "fr")
    _say(client, "marie", "Bonjour", "fr")
    _join(client, "rhys", "cy")

    lines = _script(client, "rhys").json()["lines"]

    assert all("None" not in line.get("text", "") for line in lines)


def test_leaving_closes_one_room_and_keeps_what_was_said(client):
    """Leaving is not a reason for everybody else to lose half the conversation."""
    _host(client)
    _join(client, "marie", "fr")
    _join(client, "hans", "de")
    _say(client, "hans", "Guten Tag", "de")

    assert client.delete("/salons/salon-1/participants/hans").status_code == 200

    lines = _script(client, "marie").json()["lines"]
    assert any(line.get("tour", {}).get("text") == "Guten Tag" for line in lines)


def test_a_departure_reported_twice_is_not_an_error(client):
    """A connection that dies is often reported twice, and neither report may fail."""
    _host(client)
    _join(client, "marie", "fr")

    client.delete("/salons/salon-1/participants/marie")

    assert client.delete("/salons/salon-1/participants/marie").status_code == 200


def test_ending_a_salon_releases_it(client):
    _host(client)
    _join(client, "marie", "fr")

    assert client.delete("/salons/salon-1").status_code == 200
    assert client.app.state.registry.hosted == ()


# ── The boundary ──────────────────────────────────────────────────────────────


def test_no_route_accepts_or_returns_audio(client):
    """Stated against the schema rather than in prose, so it fails the build if it stops
    being true. A field that could carry sound — bytes, a URL to a recording, a track name —
    would be the boundary eroding one convenient field at a time."""
    from src.serving import HostRequest, JoinRequest, UtteranceRequest

    audio_shaped = ("audio", "track", "bytes", "pcm", "frame", "sample", "codec", "stream")

    fields = [
        name
        for model in (HostRequest, JoinRequest, UtteranceRequest)
        for name in model.model_fields
    ]

    assert [name for name in fields if any(word in name.lower() for word in audio_shaped)] == []


@pytest.mark.asyncio
async def test_an_application_with_no_factory_refuses_to_host_rather_than_losing_words():
    """`src.main:app` is the domain, which does not know what implements it. Accepting a
    Salon it has nowhere to put would answer every request cheerfully and lose the
    conversation — the failure that takes longest to notice."""
    from src.main import _no_factory

    with pytest.raises(RuntimeError, match="no salon factory"):
        await _no_factory("salon-1")


def test_a_room_that_cannot_be_opened_is_a_503_and_not_a_stack_trace(client):
    """Provisioning is the one thing here that reaches outside this process. A rejected
    credential or a LiveKit outage arrives as whatever the SDK chose to raise, and left alone
    that surfaces as a 500 telling the caller nothing it can act on — which is exactly what
    happened the first time this ran against a real container."""
    _host(client)
    salon = client.app.state.registry.get("salon-1")

    async def refuse(*args, **kwargs):
        raise RuntimeError("livekit said 401")

    salon._rooms.provision = refuse

    response = _join(client, "marie", "fr")

    assert response.status_code == 503
    assert "room" in response.json()["detail"]


def test_hosting_a_salon_that_already_has_a_history_carries_on_from_it(client):
    """The 500 this file was written after. A fresh journal numbers its first message 1, so
    hosting a Salon that already has rows makes the next thing anybody says collide with the
    primary key — the conversation stops at its first word.

    It is also the whole of the claim that affinity is a preference rather than a condition
    of survival: an instance picking a Salon up must read what it already is.
    """
    _host(client)
    _join(client, "hans", "de")
    _say(client, "hans", "Guten Tag", "de")

    # A second instance taking it over — same store, same identifier, nothing in memory.
    application = client.app
    application.state.registry.release("salon-1")
    _host(client)

    body = _say(client, "hans", "Und noch etwas", "de").json()

    assert body["recorded"] == 1
    assert body["sequences"] == [2]  # after the first, not on top of it
