"""The four options, on the screen somebody actually joins from (Story 10.4 / FR35).

The endpoint was built first and the screen second, which leaves one failure mode worth
guarding above all others: the page offering a tier the server has never heard of. The server
answers an unknown tier with a 400 naming it — deliberately, so a disagreement surfaces rather
than becoming a silent downgrade — which means a typo in this markup does not degrade the
experience, it refuses every guest who picks that option.

So the values in the page are compared against the enum itself. Prose can drift; these cannot.
"""
import pathlib
import re

import pytest

from src.credit import Tier

JOIN = pathlib.Path(__file__).resolve().parents[1] / "web" / "join.html"


@pytest.fixture(scope="module")
def source() -> str:
    return JOIN.read_text(encoding="utf-8")


def _dictionaries(source: str) -> list[str]:
    """The inline English and French dictionaries, as raw text."""
    return re.findall(r"badge: '(?:No install|Sans installation)'.*?(?=\n    \})", source, re.S)


# ── What is offered ───────────────────────────────────────────────────────────


def test_every_tier_is_offered(source):
    offered = set(re.findall(r'input type="radio" name="tier" value="([^"]+)"', source))

    assert offered == {tier.value for tier in Tier}


def test_no_tier_the_server_has_never_heard_of(source):
    """The failure this file exists for. An unknown value is a 400 naming it, so a typo here
    refuses every guest who picks that option rather than quietly costing them less."""
    offered = re.findall(r'input type="radio" name="tier" value="([^"]+)"', source)

    assert all(value in {tier.value for tier in Tier} for value in offered)


def test_the_cheapest_is_the_one_preselected(source):
    """Somebody who reads nothing and presses Join lands on Base. A preselected paid tier
    would be a charge obtained by inattention."""
    checked = re.findall(r'value="([^"]+)"[^>]*\schecked', source)

    assert checked == [Tier.BASE.value]


def test_each_option_says_what_it_buys(source):
    """A list of four names is not a choice. Each carries what differs from the one below."""
    for key in ("tierBaseWhat", "tierAWhat", "tierBWhat", "tierCWhat"):
        assert f'data-i18n="{key}"' in source


# ── Both languages, or neither ────────────────────────────────────────────────


def test_the_copy_exists_in_english_and_in_french(source):
    """A key present in one dictionary and missing from the other renders as a blank line to
    half the people who see it."""
    keys = (
        "tierHeading", "tierBase", "tierBaseWhat", "tierA", "tierAWhat",
        "tierB", "tierBWhat", "tierC", "tierCWhat",
    )
    for key in keys:
        assert source.count(f"{key}:") == 2, key


def test_the_full_salon_copy_exists_in_both_too(source):
    """Story 10.2's refusal is read aloud as well as shown, so a missing translation is a
    silence rather than a blank."""
    for key in ("errFullTitle", "errFullDetail"):
        assert source.count(f"{key}:") == 2, key


# ── When it is shown, and when it is not ──────────────────────────────────────


def test_the_choice_is_hidden_when_the_host_is_paying(source):
    """Asking somebody to pick a budget they are not spending is a question with no meaning.
    The server decides, and the page reads `hostPaysAll` rather than inferring it."""
    assert "creds.hostPaysAll === false" in source


def test_an_older_server_hides_the_choice_rather_than_offering_it(source):
    """Strict equality, so a response with no `hostPaysAll` at all leaves the question
    unasked. The other reading would show four options to somebody whose server cannot
    record any of them."""
    assert "creds.hostPaysAll !== false" in source
    assert "!creds.hostPaysAll" not in source


def test_it_is_asked_on_the_way_in_only(source):
    """Somebody retrying after a dropped connection has already answered, and asking again
    would look like the first answer was lost."""
    assert "readyMode === 'initial'" in source


# ── Settled before anything is billable ───────────────────────────────────────


def test_the_choice_is_recorded_before_the_room_is_entered(source):
    """What somebody chose has to be settled before they can be charged for anything."""
    join_body = source.split("async function joinNow()", 1)[1]

    assert join_body.index("recordTierChoice()") < join_body.index("new LivekitClient.Room")


def test_the_microphone_gesture_is_still_spent_first(source):
    """`warmUpMicrophone` has to run before any other await, or the browser stops treating
    the click as a user gesture. The recording call goes after it, never between."""
    join_body = source.split("async function joinNow()", 1)[1]

    assert join_body.index("warmUpMicrophone()") < join_body.index("recordTierChoice()")


def test_a_failure_to_record_does_not_cost_the_conversation(source):
    """The conversation is the product. The fallback is downward — the server never heard of
    a choice it did not receive — and getting less than was asked for is the safe direction."""
    body = source.split("async function recordTierChoice()", 1)[1].split("\n  }", 1)[0]

    assert "catch" in body
    assert "showError" not in body


# ── Reachable, and not by colour alone ────────────────────────────────────────


def test_the_options_are_native_radios(source):
    """Keyboard reachable and announced as a group with a position, with no ARIA of ours to
    keep correct."""
    assert 'role="radiogroup"' in source
    assert source.count('type="radio" name="tier"') == len(Tier)


def test_the_selection_is_not_carried_by_colour_alone(source):
    """UX-DR7. The radio itself marks the choice; the border and background are the second
    signal, never the only one."""
    assert ".tier-option:has(input:checked)" in source


def test_keyboard_focus_is_visible_on_its_own(source):
    """Distinct from selection: tabbing through four options must be visible before any of
    them is chosen."""
    assert ".tier-option:focus-within" in source
    assert "outline" in source.split(".tier-option:focus-within", 1)[1][:200]


def test_the_target_is_big_enough_for_a_thumb(source):
    """UX-DR5. The whole label is the target, and it is at least 44px on the short side."""
    assert "min-height: 44px" in source


# ── Contrast, computed rather than asserted (UX-DR8) ──────────────────────────


def _luminance(hex_colour: str) -> float:
    """Relative luminance, per WCAG 2.1."""
    channels = [int(hex_colour[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [
        value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4
        for value in channels
    ]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def _contrast(foreground: str, background: str) -> float:
    first, second = _luminance(foreground), _luminance(background)
    lighter, darker = max(first, second), min(first, second)
    return (lighter + 0.05) / (darker + 0.05)


@pytest.mark.parametrize(
    "foreground,background,floor,what",
    [
        ("#2C2C2C", "#FFFFFF", 4.5, "the tier name on the card"),
        ("#5A5A5A", "#FFFFFF", 4.5, "what each tier buys"),
        ("#2C2C2C", "#FBF6F7", 4.5, "the tier name once selected"),
        ("#5A5A5A", "#FBF6F7", 4.5, "what it buys once selected"),
        # A focus ring and a selected border are non-text: AA asks 3:1 of them.
        ("#7B2D3B", "#FFFFFF", 3.0, "the focus outline and selected border"),
    ],
)
def test_the_chooser_clears_wcag_aa(foreground, background, floor, what):
    """Computed rather than claimed. A comment saying "about 13:1" is a comment; this fails
    if somebody adjusts a colour and the ratio quietly drops under the bar."""
    assert _contrast(foreground, background) >= floor, what


@pytest.mark.parametrize(
    "colour", ["#2C2C2C", "#5A5A5A", "#7B2D3B", "#FBF6F7", "#DDD"]
)
def test_the_colours_checked_are_the_colours_used(source, colour):
    """The check above is worth nothing if the stylesheet moved on without it."""
    chooser = source.split("/* The tier chooser (Story 10.4)", 1)[1].split("/* The account offer", 1)[0]

    assert colour in chooser
