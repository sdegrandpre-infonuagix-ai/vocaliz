"""Reading a string must never take the page down with it.

Reported from a live session as `Cannot read properties of undefined (reading 'roomSub')`.
`T()` indexed `I18N[lang][key]` directly, and `lang` is allowed to name a dictionary that has
not arrived yet — a stored choice is validated against the sixteen supported languages, not
against what is loaded. Only English and French ship inline, so for the other fourteen the
first render happens before the fetch lands.

The damage was not one missing string. The first render runs during boot, so the exception
took everything after it: no config, no sign-in, a dead page for fourteen of sixteen
languages.

Checked two ways. The static assertion always runs and pins the exact shape that broke. The
behavioural one extracts the real function and executes it under Node, which is what actually
proves a missing dictionary is survivable.
"""
import pathlib
import re
import shutil
import subprocess
import textwrap

import pytest

WEB = pathlib.Path(__file__).resolve().parents[1] / "web"
PAGES = ("host.html", "join.html")


def _source(page: str) -> str:
    return (WEB / page).read_text(encoding="utf-8")


# ─── The shape that broke ────────────────────────────────────────────────────

@pytest.mark.parametrize("page", PAGES)
def test_no_page_indexes_straight_through_the_active_dictionary(page):
    """`I18N[lang][key]` is the regression itself, spelled out."""
    assert "I18N[lang][" not in _source(page), (
        "an absent dictionary would throw during boot and take the page with it"
    )


@pytest.mark.parametrize("page", PAGES)
def test_english_is_bundled_so_the_fallback_can_never_be_absent(page):
    """The fallback reads `I18N.en[key]` unguarded, which is only safe because English is
    inline in the page rather than fetched."""
    source = _source(page)
    head = source[: source.index("function T(")]
    assert re.search(r"\ben\s*:\s*\{", head), "English must be defined before T() uses it"


# ─── The behaviour ───────────────────────────────────────────────────────────

def _extract_T(page: str) -> str:
    """Pull the real `function T(...)` out of the page by matching braces.

    Deliberately the shipped function rather than a copy: a copy would keep passing after the
    page regressed, which is the failure mode this test exists to avoid.
    """
    source = _source(page)
    start = source.index("function T(")
    depth = 0
    for i in range(source.index("{", start), len(source)):
        if source[i] == "{":
            depth += 1
        elif source[i] == "}":
            depth -= 1
            if depth == 0:
                return source[start : i + 1]
    raise AssertionError(f"could not find the end of T() in {page}")


def _run_in_node(page: str, lang: str, key: str, *, params: str = "null") -> str:
    harness = textwrap.dedent(
        f"""
        // Only English is loaded, which is the state the page boots in for the fourteen
        // languages that are fetched rather than bundled.
        var I18N = {{ en: {{ {key}: 'Salon {{room}}' }} }};
        var lang = {lang!r};
        {_extract_T(page)}
        process.stdout.write(String(T({key!r}, {params})));
        """
    )
    result = subprocess.run(
        ["node", "-e", harness], capture_output=True, text=True, timeout=30
    )
    assert result.returncode == 0, f"T() threw: {result.stderr.strip()[:400]}"
    return result.stdout


@pytest.mark.skipif(shutil.which("node") is None, reason="Node is needed to run the page JS")
@pytest.mark.parametrize("page", PAGES)
def test_a_language_whose_dictionary_has_not_arrived_falls_back(page):
    """The reported crash. Japanese is chosen, its dictionary is still in flight."""
    assert _run_in_node(page, "ja", "roomSub") == "Salon {room}"


@pytest.mark.skipif(shutil.which("node") is None, reason="Node is needed to run the page JS")
@pytest.mark.parametrize("page", PAGES)
def test_a_bundled_language_still_reads_its_own_dictionary(page):
    """The fallback must not have quietly replaced the normal path."""
    source = _extract_T(page)
    harness = textwrap.dedent(
        f"""
        var I18N = {{ en: {{ k: 'english' }}, ja: {{ k: 'japanese' }} }};
        var lang = 'ja';
        {source}
        process.stdout.write(T('k'));
        """
    )
    out = subprocess.run(["node", "-e", harness], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    assert out.stdout == "japanese"


@pytest.mark.skipif(shutil.which("node") is None, reason="Node is needed to run the page JS")
def test_placeholders_survive_the_fallback():
    """host.html interpolates; a fallback that dropped parameters would print `{room}` at the
    reader instead of the salon name."""
    assert _run_in_node("host.html", "ja", "roomSub", params="{room: 'Vocaliz'}") == (
        "Salon Vocaliz"
    )


@pytest.mark.skipif(shutil.which("node") is None, reason="Node is needed to run the page JS")
@pytest.mark.parametrize("page", PAGES)
def test_an_unknown_key_yields_the_key_rather_than_nothing(page):
    """A missing string should be identifiable on screen, not blank."""
    assert _run_in_node(page, "ja", "roomSub").strip() != ""
    harness = textwrap.dedent(
        f"""
        var I18N = {{ en: {{}} }};
        var lang = 'ja';
        {_extract_T(page)}
        process.stdout.write(T('somethingNobodyDefined'));
        """
    )
    out = subprocess.run(["node", "-e", harness], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    assert out.stdout == "somethingNobodyDefined"


# ─── Caption size ────────────────────────────────────────────────────────────
#
# The buttons set a font-size on the caption container and every child kept its own px, which
# ignores a parent's font-size outright. They changed nothing at all, and looked correct: the
# code was there, the state was stored, the value round-tripped to the account. Only the
# rendered result was wrong, and nothing was checking it.

@pytest.mark.parametrize("page", PAGES)
def test_the_caption_children_scale_with_their_container(page):
    """Every caption element sized in em, not px. One absolute size among them is enough to
    make the size buttons partly inert, which is harder to notice than wholly inert."""
    source = _source(page)
    start = source.index(".cap-line")
    block = source[start : source.index("</style>", start)]
    absolute = re.findall(r"(\.cap-[a-z]+)\s*\{[^}]*font-size:\s*[\d.]+px", block)
    # cap-notice is deliberately excluded: it is a statement about the room rather than part of
    # the transcript, so it does not follow the reading size.
    offenders = [c for c in absolute if c != ".cap-notice"]
    assert not offenders, f"{page}: absolute caption sizes {offenders}"


@pytest.mark.parametrize("page", PAGES)
def test_the_scale_is_applied_to_the_container(page):
    """The container is what carries the scale; a rule that set it on each line would have to
    know their proportions to each other."""
    source = _source(page)
    assert "log.style.fontSize = capScale + '%'" in source


@pytest.mark.parametrize("page", PAGES)
def test_the_steps_are_whole_percentages(page):
    """Integers, because the stored value is compared against this list and a float read back
    from a database is not reliably the float in it."""
    source = _source(page)
    steps = source[source.index("var CAP_STEPS = ["):]
    steps = steps[: steps.index("]")]
    assert "." not in steps, f"{page}: fractional caption steps in {steps}"


@pytest.mark.parametrize("page", PAGES)
def test_the_stored_size_is_applied_before_the_first_click(page):
    """Without this the reader's choice only took effect the next time they pressed a button."""
    source = _source(page)
    start = source.index("function initCaptions()")
    # A window rather than a brace scan: the two pages indent their top level differently, and
    # matching on indentation is how the first version of this test failed on one of them.
    assert "applyCaptionSize()" in source[start : start + 700]


# ─── The microphone, and the gesture Safari insists on ───────────────────────
#
# Eight hosts reached a room and none was ever heard, seven of them on phones. Two causes, both
# readable in the page: the microphone was asked for long after the click that authorised it, and
# sound was muted by default on mobile too.

@pytest.mark.parametrize("page", PAGES)
def test_the_microphone_is_asked_for_while_the_click_is_still_warm(page):
    """iOS Safari grants getUserMedia only inside the activation window a gesture opens. Two
    network round trips and a WebRTC handshake used to stand in between, so Safari refused —
    and only on somebody's first visit, which is the worst possible shape for a defect."""
    source = _source(page)
    assert "async function warmUpMicrophone()" in source
    assert "navigator.mediaDevices.getUserMedia({ audio: true })" in source


@pytest.mark.parametrize(
    "page,handler",
    [("host.html", "async function createSession()"), ("join.html", "async function joinNow()")],
)
def test_nothing_is_awaited_before_the_microphone(page, handler):
    """The whole point of the fix is the order. An await placed above this line would spend the
    gesture again and put the defect back without changing a visible thing."""
    source = _source(page)
    body = source[source.index(handler):]
    warm = body.index("await warmUpMicrophone()")
    # Positions, not a word search: the comment above the call says "await" itself, and a test
    # that reads its own explanation proves nothing.
    for blocking in ("await api(", "await fetch(", "await room."):
        at = body.find(blocking)
        if at != -1:
            assert warm < at, f"{page}: {blocking} runs before the microphone is asked for"


@pytest.mark.parametrize("page", PAGES)
def test_the_permission_is_kept_and_the_stream_is_not(page):
    """It is the permission that matters, not the audio: LiveKit opens its own track a moment
    later. Holding this one would leave the recording indicator lit for no reason."""
    source = _source(page)
    warm = source[source.index("async function warmUpMicrophone()"):]
    warm = warm[: warm.index("\n}") if "\n}" in warm[:2000] else 1500]
    assert "track.stop()" in warm


# ─── Sound, and the instruction the code contradicted ────────────────────────

@pytest.mark.parametrize("page", PAGES)
def test_sound_is_not_muted_for_everyone(page):
    """It was `var soundOn = false` unconditionally, so a mobile host heard nothing and had no
    idea why — against an explicit instruction that mobile should follow the device volume."""
    source = _source(page)
    assert "var soundOn = false;" not in source


@pytest.mark.parametrize("page", PAGES)
def test_the_default_depends_on_the_device(page):
    source = _source(page)
    block = source[source.index("var soundOn = (function ()"):]
    block = block[: block.index("})();")]
    # The same categories the report is built from, so "phone" means one thing in both places.
    for kind in ("iphone", "android-phone", "tablet"):
        assert kind in block, f"{page}: {kind} not considered"


@pytest.mark.parametrize("page", PAGES)
def test_a_stored_choice_beats_the_device_default(page):
    """Somebody who turned sound off meant it, on a phone as much as on a laptop. The toggle
    writes '0' as well as '1' precisely so that "off on purpose" is distinguishable from "never
    chose"."""
    source = _source(page)
    block = source[source.index("var soundOn = (function ()"):]
    block = block[: block.index("})();")]
    assert "stored === '1'" in block and "stored === '0'" in block
    assert "SOUND_KEY, soundOn ? '1' : '0'" in source


# ─── The countdown, and what replaced it ─────────────────────────────────────
#
# A Salon opened on a timer: fifteen seconds after the first invitation the agent spoke. It
# interrupted a host still reading and made a host who was ready wait. The host now activates
# the agent, so the button press is the timing.

@pytest.mark.parametrize("page", PAGES)
def test_no_countdown_survives_anywhere_in_the_page(page):
    """Markup, styles, strings and timers were four separate places. Leaving any one of them
    is a panel that shows a number nothing counts down, or a string nothing displays."""
    source = _source(page)
    for leftover in ("countdown", "Countdown", "guest_invited", "opensInSeconds"):
        assert leftover not in source, f"{page}: {leftover} still present"


def test_the_agent_control_is_what_starts_a_salon():
    """The host page carries the button. It is the only way a Salon begins now, so it must
    open in the state that offers activation rather than the one that offers a pause."""
    source = _source("host.html")
    assert "var agentState = { present: true, muted: true }" in source
    assert 'data-i18n="agentResume"' in source


def test_the_activate_wording_fits_a_first_press():
    """"Resume" is a lie the first time — there is nothing yet to resume, and the host has
    never heard the agent speak."""
    source = _source("host.html")
    head = source[: source.index("agentPause: \"Mettre")]
    assert "agentResume: 'Activate the agent'" in head


def test_the_button_looks_like_an_action_only_while_it_is_one():
    """Primary while the Salon waits to be started, ordinary once the agent is listening. A
    control that stayed gold would compete with everything else on the page forever."""
    source = _source("host.html")
    assert "agentState.muted ? 'btn btn-primary' : 'btn btn-outline'" in source


def test_a_paused_agent_says_so_rather_than_explaining_removal():
    """The host's first question about a paused agent is whether it can hear them. The hint
    that describes what removing does answers a question nobody asked yet."""
    source = _source("host.html")
    assert "agentHintPaused" in source
    hint = source[source.index("var hint = 'agentHintAbsent'") :][:300]
    assert "agentState.muted ? 'agentHintPaused' : 'agentHintPresent'" in hint


@pytest.mark.parametrize("page", PAGES)
def test_captions_are_bounded_in_characters_not_pixels(page):
    """The cards are three times wider than they were, and a caption stretched across all of
    it is unreadable in the specific way long lines are.

    ch rather than px because the reader sets their own caption size. A fixed pixel width
    would cut the characters per line at every step up, turning a control meant to help
    reading into one that hinders it — the same class of mistake as sizing the caption
    children in px while scaling their container."""
    source = _source(page)
    block = source[source.index(".cap-text"):]
    block = block[: block.index("</style>")]
    assert "max-width:65ch" in block.replace(" ", ""), (
        f"{page}: captions are not bounded by a character count"
    )
