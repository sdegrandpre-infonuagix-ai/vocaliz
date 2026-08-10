"""The landing page's own i18n, following the same contract host.html and join.html already
proved out in test_web_i18n.py — not folded into that file's `PAGES` tuple, because most of
what it tests (captions, dictation, the microphone gesture) does not exist on this page at
all and would fail here for reasons that have nothing to do with translation.

The one regression that matters is the one `test_web_i18n.py` documents: `T()` indexing
`I18N[lang][key]` directly throws the moment a stored or browser-detected language names a
dictionary that has not been fetched yet, and the first render runs during boot — so the
exception takes the whole page with it, not just one string.
"""
import pathlib
import re
import shutil
import subprocess
import textwrap

import pytest

WEB = pathlib.Path(__file__).resolve().parents[1] / "web"
INDEX = (WEB / "index.html").read_text(encoding="utf-8")


def test_no_direct_index_into_the_active_dictionary():
    assert "I18N[lang][" not in INDEX, (
        "an absent dictionary would throw during boot and take the page with it"
    )


def test_english_is_bundled_so_the_fallback_can_never_be_absent():
    head = INDEX[: INDEX.index("function T(")]
    assert re.search(r"\ben\s*:\s*\{", head), "English must be defined before T() uses it"


def test_french_is_bundled_too():
    """The other language this product is built in, not fetched like the rest."""
    head = INDEX[: INDEX.index("function T(")]
    assert re.search(r"\bfr\s*:\s*\{", head), "French must be defined before T() uses it"


def _extract_T() -> str:
    start = INDEX.index("function T(")
    depth = 0
    for i in range(INDEX.index("{", start), len(INDEX)):
        if INDEX[i] == "{":
            depth += 1
        elif INDEX[i] == "}":
            depth -= 1
            if depth == 0:
                return INDEX[start : i + 1]
    raise AssertionError("could not find the end of T() in index.html")


def _run_in_node(lang: str, key: str) -> str:
    harness = textwrap.dedent(
        f"""
        var I18N = {{ en: {{ {key}: 'fallback text' }} }};
        var lang = {lang!r};
        {_extract_T()}
        process.stdout.write(String(T({key!r})));
        """
    )
    result = subprocess.run(["node", "-e", harness], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, f"T() threw: {result.stderr.strip()[:400]}"
    return result.stdout


@pytest.mark.skipif(shutil.which("node") is None, reason="Node is needed to run the page JS")
def test_a_language_whose_dictionary_has_not_arrived_falls_back():
    assert _run_in_node("ja", "quote") == "fallback text"


@pytest.mark.skipif(shutil.which("node") is None, reason="Node is needed to run the page JS")
def test_a_bundled_language_reads_its_own_dictionary():
    harness = textwrap.dedent(
        f"""
        var I18N = {{ en: {{ k: 'english' }}, ja: {{ k: 'japanese' }} }};
        var lang = 'ja';
        {_extract_T()}
        process.stdout.write(T('k'));
        """
    )
    out = subprocess.run(["node", "-e", harness], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    assert out.stdout == "japanese"


@pytest.mark.skipif(shutil.which("node") is None, reason="Node is needed to run the page JS")
def test_an_unknown_key_yields_the_key_rather_than_nothing():
    assert _run_in_node("ja", "quote").strip() != ""
    harness = textwrap.dedent(
        f"""
        var I18N = {{ en: {{}} }};
        var lang = 'ja';
        {_extract_T()}
        process.stdout.write(T('somethingNobodyDefined'));
        """
    )
    out = subprocess.run(["node", "-e", harness], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    assert out.stdout == "somethingNobodyDefined"


# ─── The combo box's languages must be servable ─────────────────────────────
#
# A language offered here with no matching dictionary, or no matching entry in the API's
# allowlist, is a selection that reaches a 404 instead of a translation — silently, since
# `setLang` only puts the picker back where it started and logs nothing to the screen.

def _supported_langs() -> list[str]:
    block = INDEX[INDEX.index("var SUPPORTED_LANGS = [") :]
    block = block[: block.index("]")]
    return re.findall(r"\"([a-z]+)\"", block)


def test_every_supported_language_except_the_two_bundled_ones_is_in_the_api_allowlist():
    from src.routers.guest_web import _I18N_LANGUAGES

    generated = [lang for lang in _supported_langs() if lang not in ("en", "fr")]
    assert generated, "expected at least one machine-translated language"
    missing = [lang for lang in generated if lang not in _I18N_LANGUAGES]
    assert not missing, f"not in the API's i18n allowlist: {missing}"


def test_the_page_is_in_the_apis_i18n_allowlist():
    from src.routers.guest_web import _I18N_PAGES

    assert "index" in _I18N_PAGES


def test_the_page_is_in_the_generator_s_page_list():
    from web.i18n.generate import PAGES

    assert "index" in PAGES


def test_the_quote_s_generic_use_of_salon_is_not_brand_protected():
    """The tagline's own "Salon" is a hardcoded link, never a translated key — the only
    place the word appears in translated text is the Wikipedia quote, where it means the
    historical gathering, not the product. Protecting it there would strand an English
    word inside an otherwise-translated sentence."""
    from web.i18n.generate import PAGE_PRODUCT_WORDS

    words = dict(PAGE_PRODUCT_WORDS["index"])
    assert "Salon" not in words
    assert "Salons" not in words
