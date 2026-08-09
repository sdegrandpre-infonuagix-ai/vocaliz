"""The front door: place a call at the top, watch the desk below.

Both sides of the hotel scenario on one page, because they only make sense together — a caller
with nobody reading, or a desk with nobody calling, each looks like half a product.

The desk joins the Salon for real. Read-only is about the controls, not the presence: the clerk
is in the room and hearing it, and there is nothing to press. Answering happens in the console,
and these tests are mostly about that boundary holding — a panel that looked like it could
answer would be the worst kind of lie in front of somebody with a caller waiting.
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


def test_the_call_is_the_first_thing_on_the_page(client):
    """Somebody rings, and everything below is the answer to that."""
    body = client.get("/").text
    assert body.index("Call Vocaliz") < body.index("front-desk clerk")


def test_the_button_rings_the_desk_with_nothing_to_type(client):
    """Somebody who has never heard of Vocaliz should be in a room one press after arriving.
    A code would mean they had to have been given one, which is the opposite of ringing a
    front desk."""
    body = client.get("/").text
    assert "/invitations/call-the-desk" in body
    caller = body[body.index('id="dialer"') : body.index("</header>")]
    # An optional address is allowed and a required one is not. Nothing in the dialer may be
    # a precondition: somebody who just wants to ask a question would hang up rather than
    # register for one.
    assert "required" not in caller
    assert 'placeholder="000000"' not in caller, "a code would mean they had to be given one"


def test_the_microphone_is_asked_for_inside_the_click(client):
    """iOS Safari grants getUserMedia only in the activation window a gesture opens."""
    body = client.get("/").text
    assert body.index("getUserMedia") < body.index("fetch('/invitations/call-the-desk")


# ─── The desk, and what read-only has to mean ─────────────────────────────────

def test_the_desk_joins_the_salon(client):
    """Not a mock-up and not a poller: the clerk is in the room, on the same data channel the
    console reads."""
    body = client.get("/").text
    assert "/join'" in body or "/join'," in body
    assert "deskRoom.connect" in body


def test_the_desk_never_enables_a_microphone(client):
    """The one line that makes this read-only in the room rather than only on screen."""
    body = client.get("/").text
    desk = body[body.index("async function openDesk"):]
    assert "setMicrophoneEnabled" not in desk


def test_the_desk_has_nothing_to_press(client):
    """No pause, no removal, no place to type. Every one of those exists in the console, and
    a copy here that half-worked would be worse than no copy."""
    body = client.get("/").text
    desk = body[body.index('id="desk"'):]
    desk = desk[: desk.index("</section>")]
    for control in ("<textarea", "toggleAgentMute", "togglePrivateToAgent", "cap-lang"):
        assert control not in desk, f"the desk offers {control}, which it must not"


def test_the_desk_says_it_is_read_only(client):
    """On the page, not only in the code. Somebody with a caller waiting should not have to
    discover it by trying."""
    body = client.get("/").text
    assert "Read only" in body


def test_the_desk_shows_what_was_said_before_it_opened(client):
    """The data channel carries turns from now on and knows nothing of the ones already
    spoken. A desk opened mid-call would start blank in front of a clerk who needs precisely
    what was already said."""
    assert "/utterances?lang=" in client.get("/").text


def _without_comments(block: str) -> str:
    """The same block with its `//` lines removed.

    The comment above the render loop says "textContent, never innerHTML", so a test counting
    the word reads its own explanation and fails. Third time this has caught me: prose is not
    evidence about behaviour, in either direction.
    """
    return "\n".join(
        line for line in block.splitlines() if not line.lstrip().startswith("//")
    )


def test_the_desk_renders_speech_as_text_rather_than_markup(client):
    """These are strangers on a telephone line, transcribed."""
    body = client.get("/").text
    desk = _without_comments(body[body.index("function render()") : body.index("log.scrollTop")])
    assert ".textContent" in desk
    # Emptying the list is not injection; assigning speech to it would be. A blanket ban on
    # innerHTML would have been satisfied by a slower clear and taught nothing.
    assert desk.count("innerHTML") == desk.count("innerHTML = ''")


def test_a_turn_is_never_shown_twice(client):
    """The agent may retry a turn, and a desk showing the same sentence twice reads as the
    caller having said it twice."""
    body = client.get("/").text
    assert "turns[i].sequence === msg.sequence" in body


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


def test_the_choice_travels_with_the_call(client):
    body = client.get("/").text
    assert "/invitations/call-the-desk?language=" in body


def test_the_choice_is_remembered(client):
    """Somebody who needs Persian needs it every time and should not have to find the menu
    again on their second call."""
    assert "localStorage.setItem(LANG_KEY" in client.get("/").text


def test_the_remembered_choice_is_applied_after_the_options_exist(client):
    """Setting a select's value before its options exist silently keeps the first entry, and
    a remembered choice that quietly reverts to auto is worse than none at all."""
    body = client.get("/").text
    block = body[body.index("loadVoiceLanguages"):]
    block = block[: block.index("})();")]
    assert block.index("appendChild(option)") < block.index("select.value = voiceLang")


def test_an_unreachable_list_does_not_block_the_call(client):
    """No choice means follow the speaker, which is what every Salon did before this control
    existed. Refusing to place a call over a menu would be the wrong trade."""
    body = client.get("/").text
    block = body[body.index("loadVoiceLanguages"):]
    block = block[: block.index("})();")]
    assert "catch" in block and "console.warn" in block


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

def test_the_spoken_languages_are_listed_at_the_foot(client):
    """It answers a question somebody asks after reading the rest — "will it understand me?"
    — so it belongs where that question arises rather than above the call button."""
    body = client.get("/").text
    assert "<footer>" in body
    assert body.index("Call Vocaliz") < body.index("<footer>")


def test_the_footer_is_built_from_the_same_request_as_the_menu(client):
    """Two lists built separately eventually disagree, and the one nobody maintains is the
    one somebody reads before deciding whether to call."""
    body = client.get("/").text
    assert "renderSpokenLanguages(body.languages" in body


def test_auto_is_not_listed_as_a_language(client):
    """"Follow the speaker" is a setting. Reading it among the tongues Vocaliz speaks would
    be an odd thing to find in that list."""
    body = client.get("/").text
    block = body[body.index("function renderSpokenLanguages"):]
    block = block[: block.index("\n  }")]
    assert "entry.tag === 'auto'" in block


def test_persian_reaches_the_footer(client):
    """Named in the request that asked for this list, and the reason the list is not simply
    xAI's twenty."""
    tags = [e["tag"] for e in client.get("/voice-languages").json()["languages"]]
    assert "fa" in tags


# ─── The green light ─────────────────────────────────────────────────────────

def test_the_caller_sees_when_a_human_arrives(client):
    """The agent says it out loud — "I will let you know when they connect". This is the same
    fact for somebody watching rather than listening."""
    body = client.get("/").text
    assert 'id="presence-dot"' in body
    assert "ParticipantConnected" in body


def test_the_light_ignores_the_agent(client):
    """The agent is a participant too, so a count would go green the instant the call
    connected — announcing the very thing the caller is waiting to stop waiting for."""
    body = client.get("/").text
    block = body[body.index("function renderPresence"):]
    block = block[: block.index("async function hangUp")]
    assert "!== 'agent'" in block


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
