"""Tests for salon creation endpoint."""
import io
import pytest
from unittest.mock import AsyncMock, patch

from src.models.salon import Salon
from src.models.user import User
from src.services.jwt_service import issue_token


@pytest.fixture
def user(db):
    u = User(email="15141234567@example.com", phone_number="+15141234567")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u, issue_token(str(u.id))


# ─── Auth guard ─────────────────────────────────────────────────────────────

def test_create_salon_requires_auth(client):
    response = client.post("/salons", data={"source_url": "https://example.com"})
    assert response.status_code == 401


# ─── Source-less salon ─────────────────────────────────────────────────────

@patch("src.routers.salons.livekit_service.create_room", new_callable=AsyncMock)
@patch("src.routers.salons.livekit_service.generate_participant_token", return_value="tok")
@patch("src.routers.salons.livekit_service.new_room_name", return_value="salon-test")
def test_create_salon_no_source(mock_name, mock_token, mock_room, client, user):
    """A salon may start with no document and no URL — the agent then asks the
    participants what they want to discuss."""
    _, token = user
    response = client.post("/salons", data={}, headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 201
    body = response.json()
    assert body["sourceType"] == "none"
    assert body["livekitRoomName"] == "salon-test"
    assert body["hostToken"] == "tok"


@patch("src.routers.salons.livekit_service.create_room", new_callable=AsyncMock)
@patch("src.routers.salons.livekit_service.generate_participant_token", return_value="tok")
@patch("src.routers.salons.livekit_service.new_room_name", return_value="salon-test")
def test_create_salon_no_source_persists_empty_content(
    mock_name, mock_token, mock_room, client, db, user
):
    """No source means no extracted content to inject into the agent prompt."""
    from src.models.salon import Salon
    _, token = user
    client.post("/salons", data={}, headers={"Authorization": f"Bearer {token}"})
    salon = db.query(Salon).first()
    assert salon.source_type == "none"
    assert salon.source_content is None
    assert salon.source_url is None
    assert salon.source_filename is None


# ─── The host's own tier choice ───────────────────────────────────────────────
#
# `host_tier` has billed the host since Story 8.4 (see the heartbeat's `Tier(salon.host_tier)
# if salon.host_tier else Tier.BASE`), but nothing before this wrote it — every host was
# silently billed at Base regardless of what they thought they had chosen.


@patch("src.routers.salons.livekit_service.create_room", new_callable=AsyncMock)
@patch("src.routers.salons.livekit_service.generate_participant_token", return_value="tok")
@patch("src.routers.salons.livekit_service.new_room_name", return_value="salon-test")
def test_create_salon_records_the_chosen_host_tier(mock_name, mock_token, mock_room, client, db, user):
    _, token = user
    response = client.post(
        "/salons",
        data={"host_tier": "Mode B"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201
    assert db.query(Salon).first().host_tier == "Mode B"


@patch("src.routers.salons.livekit_service.create_room", new_callable=AsyncMock)
@patch("src.routers.salons.livekit_service.generate_participant_token", return_value="tok")
@patch("src.routers.salons.livekit_service.new_room_name", return_value="salon-test")
def test_create_salon_with_no_tier_chosen_leaves_it_unset(mock_name, mock_token, mock_room, client, db, user):
    """Unset, not 'Base' written out — the heartbeat already treats the two the same way,
    and writing the string here would just be a second place that fact has to hold."""
    _, token = user
    client.post("/salons", data={}, headers={"Authorization": f"Bearer {token}"})
    assert db.query(Salon).first().host_tier is None


def test_create_salon_rejects_an_unknown_tier(client, user):
    _, token = user
    response = client.post(
        "/salons",
        data={"host_tier": "Deluxe"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 400


# ─── Agent dispatch ──────────────────────────────────────────────────────────

@patch("src.routers.salons.livekit_service.dispatch_agent", new_callable=AsyncMock)
@patch("src.routers.salons.livekit_service.create_room", new_callable=AsyncMock)
@patch("src.routers.salons.livekit_service.generate_participant_token", return_value="tok")
@patch("src.routers.salons.livekit_service.new_room_name", return_value="salon-test")
def test_create_salon_dispatches_agent_with_context(
    mock_name, mock_token, mock_room, mock_dispatch, client, user
):
    """The agent is useless without salon context, so creation must dispatch it.

    Passing the context through job metadata (not room metadata) keeps the host token
    away from participants.
    """
    _, token = user
    response = client.post("/salons", data={}, headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 201

    mock_dispatch.assert_awaited_once()
    kwargs = mock_dispatch.await_args.kwargs
    assert mock_dispatch.await_args.args[0] == "salon-test"
    assert kwargs["salon_id"] == response.json()["salonId"]

    # Must be a Salon API JWT for the host, not the LiveKit participant token: the agent
    # authenticates against our REST API with it.
    from src.services.jwt_service import decode_token
    host, _ = user
    assert kwargs["host_token"] != "tok"
    assert decode_token(kwargs["host_token"])["sub"] == str(host.id)

    # The host is this dispatch's participant. The relay token is scoped to them and to
    # this Salon specifically — never the host_token above, which every agent of this Salon
    # carries regardless of whose room it is dispatched into.
    from src.services import relay_token as relay_token_service

    assert kwargs["participant_id"] == str(host.id)
    assert relay_token_service.scope_of(kwargs["relay_token"]) == (
        response.json()["salonId"],
        str(host.id),
    )
    # No orchestrator is reachable in this test environment, so nothing was handed to one —
    # `False` is the honest record of that, not a stand-in for "not implemented yet".
    assert kwargs["follow_journal"] is False


@pytest.mark.real_livekit_service
@pytest.mark.asyncio
@patch("src.services.livekit_service.lk_api.LiveKitAPI")
async def test_dispatch_agent_swallows_livekit_failure(mock_api):
    """Dispatch failure must not raise: the room exists and participants can still talk.

    Exercises the real service, not a mock of it — patching dispatch_agent itself would
    bypass the try/except this asserts.
    """
    from src.services import livekit_service

    mock_api.side_effect = RuntimeError("livekit unreachable")
    assert await livekit_service.dispatch_agent(
        "salon-test",
        salon_id="s1",
        host_token="tok",
        participant_id="marie",
        relay_token="scoped-tok",
        follow_journal=False,
    ) is None


@pytest.mark.real_livekit_service
@pytest.mark.asyncio
@patch("src.services.livekit_service.lk_api.LiveKitAPI")
async def test_notify_room_swallows_livekit_failure(mock_api):
    """Same for notifications: a lost source_added message must not fail the request."""
    from src.services import livekit_service

    mock_api.side_effect = RuntimeError("livekit unreachable")
    assert await livekit_service.notify_room("salon-test", {"action": "source_added"}) is None


# ─── URL source ──────────────────────────────────────────────────────────────

@patch("src.routers.salons.livekit_service.create_room", new_callable=AsyncMock)
@patch("src.routers.salons.livekit_service.generate_participant_token", return_value="lk-tok")
@patch("src.routers.salons.livekit_service.new_room_name", return_value="salon-abc")
@patch(
    "src.routers.salons.content_service.fetch_url_document",
    new_callable=AsyncMock,
    return_value=("Article text.", {"article_date": "", "author": "", "publisher": ""}),
)
def test_create_salon_url_success(mock_content, mock_name, mock_token, mock_room, client, user, db):
    _, token = user
    response = client.post(
        "/salons",
        data={"source_url": "https://example.com/article"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["livekitRoomName"] == "salon-abc"
    assert data["hostToken"] == "lk-tok"
    assert data["sourceType"] == "url"
    assert "salonId" in data
    assert "createdAt" in data

    from src.models.salon import Salon
    salon = db.query(Salon).first()
    assert salon.source_url == "https://example.com/article"
    assert salon.source_content == "Article text."


# ─── Document upload ─────────────────────────────────────────────────────────

@patch("src.routers.salons.livekit_service.create_room", new_callable=AsyncMock)
@patch("src.routers.salons.livekit_service.generate_participant_token", return_value="lk-tok")
@patch("src.routers.salons.livekit_service.new_room_name", return_value="salon-doc")
def test_create_salon_txt_upload(mock_name, mock_token, mock_room, client, user, db):
    _, token = user
    response = client.post(
        "/salons",
        files={"file": ("test.txt", io.BytesIO(b"Plain text content."), "text/plain")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201
    assert response.json()["sourceType"] == "document"

    from src.models.salon import Salon
    salon = db.query(Salon).first()
    assert salon.source_filename == "test.txt"
    assert salon.source_content == "Plain text content."


@patch("src.routers.salons.livekit_service.create_room", new_callable=AsyncMock)
@patch("src.routers.salons.livekit_service.generate_participant_token", return_value="tok")
@patch("src.routers.salons.livekit_service.new_room_name", return_value="salon-bad")
def test_create_salon_unsupported_file_type(mock_name, mock_token, mock_room, client, user):
    _, token = user
    response = client.post(
        "/salons",
        files={"file": ("test.docx", io.BytesIO(b"data"), "application/vnd.openxmlformats")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 415


# ─── Content service unit tests ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_extract_html_text_strips_scripts():
    from src.services.content_service import _extract_html_text
    html = "<html><body><script>alert(1)</script><p>Hello world</p></body></html>"
    result = _extract_html_text(html)
    assert "Hello world" in result
    assert "alert" not in result


def test_content_url_rejects_non_http():
    import asyncio
    from fastapi import HTTPException
    from src.services.content_service import fetch_url_content
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(fetch_url_content("ftp://bad"))
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_fetch_url_rejects_ssrf_loopback():
    from fastapi import HTTPException
    from src.services.content_service import fetch_url_content
    with pytest.raises(HTTPException) as exc_info:
        await fetch_url_content("http://127.0.0.1/admin")
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_fetch_url_rejects_ssrf_link_local():
    from fastapi import HTTPException
    from src.services.content_service import fetch_url_content
    with pytest.raises(HTTPException) as exc_info:
        await fetch_url_content("http://169.254.169.254/latest/meta-data/")
    assert exc_info.value.status_code == 400


# ─── One open salon per host ───────────────────────────────────────────────

@patch("src.services.livekit_service.delete_room", new_callable=AsyncMock)
@patch("src.routers.salons.livekit_service.create_room", new_callable=AsyncMock)
@patch("src.routers.salons.livekit_service.generate_participant_token", return_value="tok")
def test_creating_a_salon_closes_the_previous_one(
    mock_token, mock_room, mock_delete, client, db, user
):
    """A host may never hold two open salons.

    A stale salon keeps its agent alive and talking, so joining the new room could
    surface the previous agent — the failure this rule exists to prevent.
    """
    from src.models.salon import Salon

    _, token = user
    headers = {"Authorization": f"Bearer {token}"}

    first = client.post("/salons", data={}, headers=headers).json()["salonId"]
    second = client.post("/salons", data={}, headers=headers).json()["salonId"]
    assert first != second

    db.expire_all()
    salons = {str(s.id): s.status for s in db.query(Salon).all()}
    assert salons[first] == "ended"
    assert salons[second] == "active"


@patch("src.services.livekit_service.delete_room", new_callable=AsyncMock)
@patch("src.routers.salons.livekit_service.create_room", new_callable=AsyncMock)
@patch("src.routers.salons.livekit_service.generate_participant_token", return_value="tok")
def test_previous_room_is_deleted_not_just_marked_ended(
    mock_token, mock_room, mock_delete, client, db, user
):
    """Deleting the room is what stops the old agent; the row only settles accounting."""
    from src.models.salon import Salon

    _, token = user
    headers = {"Authorization": f"Bearer {token}"}

    client.post("/salons", data={}, headers=headers)
    first_room = db.query(Salon).first().livekit_room_name

    client.post("/salons", data={}, headers=headers)

    mock_delete.assert_awaited()
    assert first_room in [call.args[0] for call in mock_delete.await_args_list]


@patch("src.services.livekit_service.delete_room", new_callable=AsyncMock)
@patch("src.routers.salons.livekit_service.create_room", new_callable=AsyncMock)
@patch("src.routers.salons.livekit_service.generate_participant_token", return_value="tok")
def test_another_host_salon_is_left_alone(
    mock_token, mock_room, mock_delete, client, db, user
):
    """Cleanup is scoped to the caller: it must never close someone else's salon."""
    from src.models.salon import Salon
    from src.models.user import User
    from src.services.jwt_service import issue_token

    other = User(email="other.host@example.com")
    db.add(other)
    db.commit()
    db.refresh(other)
    theirs = Salon(
        host_user_id=other.id,
        livekit_room_name="salon-theirs",
        source_type="none",
        status="active",
    )
    db.add(theirs)
    db.commit()

    _, token = user
    client.post("/salons", data={}, headers={"Authorization": f"Bearer {token}"})

    db.expire(theirs)
    db.refresh(theirs)
    assert theirs.status == "active"


# ─── Live captions need the token to allow it ────────────────────────────────

def test_participant_token_allows_updating_own_attributes():
    """Captions depend on it, and its absence fails silently.

    A participant announces the language it is reading by setting its own caption_lang
    attribute. Without canUpdateOwnMetadata the server refuses the call, the agent sees
    nobody asking for a translation, and captions come back in the language they were
    spoken — which is indistinguishable from a translator that is not working.
    """
    import jwt as pyjwt

    from src.config import settings
    from src.services import livekit_service

    token = livekit_service.generate_participant_token("salon-x", "user-1")
    claims = pyjwt.decode(token, settings.livekit_api_secret, algorithms=["HS256"])
    assert claims["video"]["canUpdateOwnMetadata"] is True


# ─── Public configuration ────────────────────────────────────────────────────

def test_config_is_readable_without_a_token(client):
    """The sign-in screen reads it, so requiring a token would make it unusable."""
    assert client.get("/config").status_code == 200


def test_sms_is_off_by_default(client):
    """Text messaging waits on an AWS review. Off is the safe direction: a host never
    sees a channel that cannot deliver."""
    assert client.get("/config").json()["smsEnabled"] is False


def test_the_config_names_the_front_desk(client):
    """The landing page sends the desk's sign-in code to this address and never asks anybody to
    type it. A field would let a visitor aim the code at themselves; served from here, the two
    cannot disagree when whoever is on shift changes."""
    from src.config import settings

    assert client.get("/config").json()["frontDeskEmail"] == settings.front_desk_email


def test_config_follows_the_setting(client):
    from src.config import settings

    original = settings.sms_enabled
    settings.sms_enabled = True
    try:
        assert client.get("/config").json()["smsEnabled"] is True
    finally:
        settings.sms_enabled = original


def test_a_phone_invitation_is_still_accepted_while_the_field_is_hidden(client, db):
    """The flag governs what is offered, not what is allowed.

    Hiding the field is a client concern; refusing the request would also break the API
    for anyone testing the path before the review clears.
    """
    from unittest.mock import patch

    from src.models.salon import Salon
    from src.models.user import User
    from src.services import sms_service
    from src.services.jwt_service import issue_token

    user = User(email="flaghost@example.com")
    db.add(user)
    db.commit()
    db.refresh(user)
    sess = Salon(
        host_user_id=user.id,
        livekit_room_name="salon-flag",
        source_type="url",
        source_content="c",
        status="active",
    )
    db.add(sess)
    db.commit()
    db.refresh(sess)

    with patch.object(sms_service, "send_invitation_sms", return_value=True):
        response = client.post(
            f"/salons/{sess.id}/invitations",
            json={"guestPhone": "+15145550123"},
            headers={"Authorization": f"Bearer {issue_token(str(user.id))}"},
        )
    assert response.status_code == 201


def test_a_room_holds_two_people_and_the_agent():
    """Down from four, and the reduction is what makes the room trustworthy.

    Caption attribution comes from active-speaker detection, which guesses when two people
    overlap. With two humans there is only ever one other voice to be confused with yours —
    and for an interpreter that is not a nicety: mistaking who spoke reverses the direction of
    a translation and says somebody's own words back to them.
    """
    from src.config import settings

    assert settings.livekit_room_max_participants == 3


# ─── The front-end pages revalidate cheaply ──────────────────────────────────

def test_a_page_carries_an_etag_and_forbids_blind_reuse(client):
    """no-cache means "revalidate before use", not "do not keep". It is only useful paired with
    a validator the server actually compares."""
    r = client.get("/host")
    assert r.status_code == 200
    assert r.headers.get("etag")
    assert "no-cache" in r.headers.get("cache-control", "")


def test_an_unchanged_page_answers_304_with_no_body(client):
    """FileResponse sends an ETag and never reads If-None-Match — it is built without a request.
    Before this the browser revalidated on every load and got the full 64 KB back every time."""
    first = client.get("/host")
    again = client.get("/host", headers={"If-None-Match": first.headers["etag"]})
    assert again.status_code == 304
    assert again.content == b""
    assert again.headers.get("etag") == first.headers["etag"]


def test_a_stale_etag_gets_the_page(client):
    """The case that matters after a deployment: the browser's copy is out of date and must be
    replaced, not revalidated into place."""
    r = client.get("/host", headers={"If-None-Match": '"something-else"'})
    assert r.status_code == 200
    assert b"VOCALIZ" in r.content


def test_the_guest_page_revalidates_the_same_way(client):
    first = client.get("/join/whatever")
    assert first.headers.get("etag")
    again = client.get("/join/whatever", headers={"If-None-Match": first.headers["etag"]})
    assert again.status_code == 304


# ─── Handing the Salon to an orchestrator ──────────────────────────────────
#
# The room and the conversation are two halves of one act, so the orchestrator is told at
# creation. What matters most below is the failure case: this must not be on the critical
# path of starting a conversation.


@patch("src.routers.salons.orchestrator_client.host_salon", new_callable=AsyncMock)
@patch("src.routers.salons.livekit_service.create_room", new_callable=AsyncMock)
@patch("src.routers.salons.livekit_service.generate_participant_token", return_value="tok")
@patch("src.routers.salons.livekit_service.new_room_name", return_value="salon-test")
def test_creating_a_salon_hands_it_to_an_orchestrator(
    mock_name, mock_token, mock_room, mock_host, client, user, db
):
    """The room name goes with it, and the host's identity. Neither is used to reach the
    Salon later — room names are derived — but they are what joins a log line about this
    Salon to a log line about that room."""
    mock_host.return_value = "http://orchestrator:8080"
    _, token = user

    response = client.post("/salons", data={}, headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 201
    assert mock_host.await_args.kwargs["room_name"] == "salon-test"
    salon = db.query(Salon).filter_by(livekit_room_name="salon-test").one()
    assert salon.orchestrator_url == "http://orchestrator:8080"


@patch("src.routers.salons.orchestrator_client.host_salon", new_callable=AsyncMock)
@patch("src.routers.salons.livekit_service.create_room", new_callable=AsyncMock)
@patch("src.routers.salons.livekit_service.generate_participant_token", return_value="tok")
@patch("src.routers.salons.livekit_service.new_room_name", return_value="salon-test")
def test_a_salon_opens_even_when_no_orchestrator_takes_it(
    mock_name, mock_token, mock_room, mock_host, client, user, db
):
    """The one that matters, and the ordinary case today: no orchestrator is deployed. A
    Salon that opens without translation is worse than one that works and vastly better than
    a host who cannot begin — and null is the honest record of which happened."""
    mock_host.return_value = None
    _, token = user

    response = client.post("/salons", data={}, headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 201
    salon = db.query(Salon).filter_by(livekit_room_name="salon-test").one()
    assert salon.orchestrator_url is None


@patch("src.routers.salons.livekit_service.create_room", new_callable=AsyncMock)
@patch("src.routers.salons.livekit_service.generate_participant_token", return_value="tok")
@patch("src.routers.salons.livekit_service.new_room_name", return_value="salon-test")
def test_the_room_has_a_seat_for_the_agent_on_top_of_the_people(
    mock_name, mock_token, mock_room, client, user
):
    """The bug this file was written after, and it was silent.

    `participant_cap` counts people; LiveKit's `max_participants` counts everyone in the room,
    and the agent is in the room. Passing one straight into the other sized the room one seat
    short: a host who asked for two got a room for two, both humans took the seats, and
    LiveKit refused the agent. Nothing errored — the dispatch succeeded, the worker was
    healthy — and what reached production was a live audio channel between two people with no
    interpreter at all.
    """
    _, token = user

    client.post(
        "/salons", data={"participant_cap": 2}, headers={"Authorization": f"Bearer {token}"}
    )

    assert mock_room.await_args.kwargs["max_participants"] == 3
