"""The landing page's backend contract: what /voice-languages and /invitations/call-the-desk
promise, independent of whatever the page currently looks like.

Previously also covered the page's own markup — a caller dialling in at the top, a front-desk
clerk's read-only view of the Salon below. That page was replaced with a plain marketing
splash (see test_index_i18n.py for what covers it now); the calling flow it exercised no
longer has a UI, but the endpoints below still do the job for whatever eventually calls them
again, and stay tested on their own terms.
"""
import pytest

PATHS = ("/", "/call")


@pytest.mark.parametrize("path", PATHS)
def test_the_page_is_served(client, path):
    resp = client.get(path)
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]


def test_both_paths_serve_the_same_page():
    """/ is where somebody arrives, /call is what a host writes down for a guest to type.
    Serving one file rather than redirecting keeps them the same page rather than two that
    drift."""
    from src.routers import guest_web

    routes = [r for r in guest_web.router.routes if r.path in PATHS]
    assert len({r.endpoint for r in routes}) == 1


# ─── The language Vocaliz will speak ─────────────────────────────────────────

def test_the_menu_is_built_from_the_api(client):
    """A page holding its own copy would offer something the API rejects, and the caller
    would press call and be refused for a reason nothing on screen could explain."""
    body = client.get("/").text
    assert "/voice-languages" in body
    assert "<option" not in body, "the choices are fetched, not written into the page"


def test_the_endpoint_serves_the_frozen_list(client):
    from src.services.voice_languages import VOICE_LANGUAGES

    body = client.get("/voice-languages").json()
    assert [e["tag"] for e in body["languages"]] == [tag for tag, _ in VOICE_LANGUAGES]


def test_the_endpoint_says_which_entries_xai_documents(client):
    """Persian is offered on the strength of testing rather than a vendor's promise. Nothing
    shows the distinction yet; flattening it here would mean it could never be shown."""
    entries = {e["tag"]: e["documented"] for e in client.get("/voice-languages").json()["languages"]}
    assert entries["fa"] is False
    assert entries["tr"] is True


def test_an_unsupported_tag_still_reaches_the_desk(client, db):
    """Asserted on the server, which is what actually decides. A caller who picked something
    the model cannot speak should still get through — falling back to following them is what
    they would have had by not choosing."""
    from unittest.mock import AsyncMock, patch

    from src.config import settings
    from src.models.salon import Salon
    from src.models.user import User

    db.add(User(email=settings.front_desk_email))
    db.commit()
    with patch("src.services.livekit_service.create_room", new_callable=AsyncMock), patch(
        "src.services.livekit_service.dispatch_agent", new_callable=AsyncMock
    ):
        resp = client.post(
            "/invitations/call-the-desk?language=klingon&email=caller@example.com"
        )
    assert resp.status_code == 200
    salon = db.query(Salon).filter(
        Salon.livekit_room_name == resp.json()["livekitRoomName"]
    ).one()
    assert salon.agent_language == "auto"


def test_a_supported_tag_is_kept_whole(client, db):
    """Regions are not truncated at the hyphen: pt-BR is not pt-PT, and collapsing them would
    pick a voice from the wrong side of an ocean."""
    from unittest.mock import AsyncMock, patch

    from src.config import settings
    from src.models.salon import Salon
    from src.models.user import User

    db.add(User(email=settings.front_desk_email))
    db.commit()
    with patch("src.services.livekit_service.create_room", new_callable=AsyncMock), patch(
        "src.services.livekit_service.dispatch_agent", new_callable=AsyncMock
    ):
        resp = client.post(
            "/invitations/call-the-desk?language=pt-PT&email=caller@example.com"
        )
    salon = db.query(Salon).filter(
        Salon.livekit_room_name == resp.json()["livekitRoomName"]
    ).one()
    assert salon.agent_language == "pt-PT"


# ─── What Vocaliz can be asked to speak ──────────────────────────────────────

def test_persian_is_offered_by_the_endpoint(client):
    """Named in the request that asked for this list, and the reason the list is not simply
    xAI's twenty."""
    tags = [e["tag"] for e in client.get("/voice-languages").json()["languages"]]
    assert "fa" in tags


def test_the_clerk_arrives_muted_on_a_call_only(client):
    """A clerk has a transcript to catch up on, and reading it while a caller hears them
    breathe is the wrong order. An ordinary Salon is a discussion its host started and wants
    to be in — arriving muted there would be a puzzle, not a courtesy."""
    body = client.get("/host").text
    assert "detail.frontDesk" in body
    assert "setMicrophoneEnabled(false)" in body


def test_the_microphone_is_still_asked_for_before_being_closed(client):
    """The permission has to be captured inside the gesture that opened the room. Skipping the
    request and simply never enabling it would leave the clerk unable to unmute at all."""
    body = client.get("/host").text
    block = body[body.index("await retryMic();"):]
    block = block[: block.index("catch (e)")]
    assert block.index("retryMic()") < block.index("setMicrophoneEnabled(false)")
