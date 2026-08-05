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
    assert "<input" not in caller, "the caller is asked to type something"


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
