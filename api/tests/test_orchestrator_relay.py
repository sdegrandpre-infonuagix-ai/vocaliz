"""The API, standing between an agent and the orchestrator that holds its Salon.

The orchestrator answers inside the VPC and nowhere else, deliberately: it holds the text of
every live conversation. The agent worker runs on LiveKit Cloud, outside it. This is the way
through, and it is the API rather than a new public endpoint because the API is already public
and already authenticated.

Two things are worth holding to account. **The orchestrator named on the Salon's row is the
one reached** — a Salon is stateful, and any other instance would answer with a second, emptier
version of the same conversation. And **the paths mirror the orchestrator's exactly**, so the
day the worker moves into the VPC, the agent's client is the same code pointed at a different
address.
"""
import uuid
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from src.models.salon import Salon
from src.models.user import User
from src.services import relay_token

ORCHESTRATOR = "http://orchestrator.vocaliz.internal:8080"
PARTICIPANT = "marie"


@pytest.fixture
def host(db):
    person = User(email="marie@example.com", display_name="Marie")
    db.add(person)
    db.commit()
    db.refresh(person)
    return person, None


@pytest.fixture
def salon(db, host):
    person, _ = host
    made = Salon(
        host_user_id=person.id,
        livekit_room_name="vocaliz-abc",
        source_type="none",
        orchestrator_url=ORCHESTRATOR,
    )
    db.add(made)
    db.commit()
    db.refresh(made)
    return made


def _auth(salon, participant_id=PARTICIPANT):
    return _auth_for(str(salon.id), participant_id)


def _auth_for(salon_id, participant_id=PARTICIPANT):
    """A token scoped to a salon id given as a literal string — for the tests that need to
    reach past authorisation into `_salon()`'s own handling of an unknown or malformed id."""
    token = relay_token.issue(salon_id=salon_id, participant_id=participant_id)
    return {"Authorization": f"Bearer {token}"}


def _answers(status=200, payload=None):
    return AsyncMock(return_value=httpx.Response(status_code=status, json=payload or {}))


# ── The way through ───────────────────────────────────────────────────────────


def test_a_script_is_fetched_from_the_orchestrator_holding_this_salon(client, host, salon):
    """Never the configured one: the one written on this Salon's row when it was created."""
    request = _answers(payload={"lines": [{"kind": "annonce", "language": "fr"}]})

    with patch("httpx.AsyncClient.request", request):
        response = client.get(
            f"/orchestrator/salons/{salon.id}/participants/marie/script", headers=_auth(salon)
        )

    assert response.status_code == 200
    assert response.json()["lines"][0]["kind"] == "annonce"
    method, url = request.await_args.args
    assert method == "GET"
    assert url == f"{ORCHESTRATOR}/salons/{salon.id}/participants/marie/script"


def test_what_a_human_said_is_forwarded_unchanged(client, host, salon):
    request = _answers(payload={"recorded": 1, "sequences": [4]})

    with patch("httpx.AsyncClient.request", request):
        response = client.post(
            f"/orchestrator/salons/{salon.id}/participants/marie/utterances",
            json={"text": "Bonjour", "language": "fr"},
            headers=_auth(salon),
        )

    assert response.json()["recorded"] == 1
    assert request.await_args.kwargs["json"]["text"] == "Bonjour"


def test_the_paths_mirror_the_orchestrators_own(client, host, salon):
    """Not tidiness. It means the agent's client is the same code whichever address it is
    pointed at, so the day this router is deleted nothing on the agent side is rewritten."""
    request = _answers(status=201)

    with patch("httpx.AsyncClient.request", request):
        client.post(
            f"/orchestrator/salons/{salon.id}/participants",
            json={"participantId": "marie", "language": "fr"},
            headers=_auth(salon),
        )

    assert request.await_args.args[1] == f"{ORCHESTRATOR}/salons/{salon.id}/participants"


def test_leaving_is_forwarded_too(client, host, salon):
    request = _answers(payload={"left": True})

    with patch("httpx.AsyncClient.request", request):
        response = client.delete(
            f"/orchestrator/salons/{salon.id}/participants/marie", headers=_auth(salon)
        )

    assert response.status_code == 200
    assert request.await_args.args[0] == "DELETE"


# ── What it refuses ───────────────────────────────────────────────────────────


def test_nothing_passes_without_a_token(client, salon):
    """The whole reason this is the API and not a new public endpoint: the authentication
    already exists here and did not have to be invented."""
    assert (
        client.get(f"/orchestrator/salons/{salon.id}/participants/marie/script").status_code
        == 401
    )


def test_a_vocaliz_sign_in_token_does_not_work_here(client, host, salon):
    """The hole tranche 1 actually had. A Vocaliz account JWT proves an identity, not a
    Salon — accepting it here meant any signed-in user could call any Salon's relay, and
    nothing had exploited that only because nothing yet minted a token that told two Salons
    apart. `purpose` is what makes the two kinds impossible to confuse."""
    from src.services.jwt_service import issue_token

    person, _ = host
    response = client.get(
        f"/orchestrator/salons/{salon.id}/participants/marie/script",
        headers={"Authorization": f"Bearer {issue_token(str(person.id))}"},
    )

    assert response.status_code == 401


def test_a_token_scoped_to_a_different_participant_is_refused(client, salon):
    """403 rather than 401: the token is real, it is simply not for this seat. Refused here
    rather than reported — it is the shape a bug takes, not an attack."""
    response = client.get(
        f"/orchestrator/salons/{salon.id}/participants/marie/script",
        headers=_auth(salon, participant_id="hans"),
    )

    assert response.status_code == 403


def test_a_token_scoped_to_a_different_salon_is_refused(client, salon, db, host):
    """The property the whole design rests on: holding a token for one Salon must never
    reach another, whatever address it is pointed at."""
    person, _ = host
    other = Salon(
        host_user_id=person.id,
        livekit_room_name="vocaliz-other",
        source_type="none",
        orchestrator_url=ORCHESTRATOR,
    )
    db.add(other)
    db.commit()

    response = client.get(
        f"/orchestrator/salons/{other.id}/participants/marie/script",
        headers=_auth(salon),  # scoped to `salon`, aimed at `other`
    )

    assert response.status_code == 403


def test_joining_is_authorised_against_the_body_not_only_the_path(client, salon):
    """`join` is the one call where the participant is announced rather than named in the
    path, so a token for `marie` must not be usable to join as `hans`."""
    response = client.post(
        f"/orchestrator/salons/{salon.id}/participants",
        json={"participantId": "hans", "language": "fr"},
        headers=_auth(salon, participant_id="marie"),
    )

    assert response.status_code == 403


def test_a_salon_with_no_orchestrator_says_so_rather_than_pretending(client, host, db):
    """503 and not 404: the Salon exists and is perfectly usable, it simply has nobody holding
    its text — which is what happens when none was reachable at creation. The conversation runs
    without translation, and saying so is honest."""
    person, _ = host
    made = Salon(
        host_user_id=person.id, livekit_room_name="vocaliz-none", source_type="none"
    )
    db.add(made)
    db.commit()

    response = client.get(
        f"/orchestrator/salons/{made.id}/participants/marie/script", headers=_auth(made)
    )

    assert response.status_code == 503


def test_an_unknown_salon_is_not_found(client, host):
    stranger = str(uuid.uuid4())
    response = client.get(
        f"/orchestrator/salons/{stranger}/participants/marie/script",
        headers=_auth_for(stranger),
    )

    assert response.status_code == 404


def test_a_salon_identifier_that_is_not_one_is_not_found_either(client, host):
    """Rather than a 500 out of the UUID parser, which is what a probe sweeping the path
    would otherwise produce in the log."""
    response = client.get(
        "/orchestrator/salons/not-a-uuid/participants/marie/script",
        headers=_auth_for("not-a-uuid"),
    )

    assert response.status_code == 404


def test_an_unreachable_orchestrator_is_a_503_and_not_a_stack_trace(client, host, salon):
    with patch("httpx.AsyncClient.request", AsyncMock(side_effect=httpx.ConnectError(""))):
        response = client.get(
            f"/orchestrator/salons/{salon.id}/participants/marie/script", headers=_auth(salon)
        )

    assert response.status_code == 503


def test_the_orchestrators_own_refusal_is_passed_through(client, host, salon):
    """A 404 from the orchestrator means it is no longer holding this Salon — a real answer
    the agent can act on by stopping. Flattening it into a 502 would tell it the network broke
    instead."""
    with patch("httpx.AsyncClient.request", _answers(status=404)):
        response = client.get(
            f"/orchestrator/salons/{salon.id}/participants/marie/script", headers=_auth(salon)
        )

    assert response.status_code == 404
