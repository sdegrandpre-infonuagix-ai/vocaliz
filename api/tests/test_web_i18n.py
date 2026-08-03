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
