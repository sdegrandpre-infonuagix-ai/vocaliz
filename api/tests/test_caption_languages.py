"""The caption languages are declared in three places and nothing kept them in step.

host.html, join.html and the mobile app each carry their own list. A language added to one and
forgotten in another is invisible until somebody joins from the wrong client and finds a
language their friend can choose and they cannot — and the two pages are the host and guest
halves of the same conversation, so a divergence there splits one salon.

Farsi is the case that prompted this. It also has to be reachable, which means four lists
agreeing rather than three: the API serves dictionaries from its own allowlist, so a language
generated but not named there answers 404 and silently falls back to English.
"""
import pathlib
import re

import pytest

from src.services import translation_service

WEB = pathlib.Path(__file__).resolve().parents[1] / "web"
MOBILE = pathlib.Path(__file__).resolve().parents[2] / "mobile" / "src" / "hooks"


def _web_caption_codes(page: str) -> list[str]:
    source = (WEB / page).read_text(encoding="utf-8")
    start = source.index("var CAPTION_LANGS = [")
    block = source[start : source.index("];", start)]
    # ['en', 'English'] — the first quoted item of each pair is the code.
    return [m.group(1) for m in re.finditer(r"\[\s*'([a-z-]*)'\s*,", block)]


def _mobile_caption_codes() -> list[str]:
    source = (MOBILE / "useCaptions.ts").read_text(encoding="utf-8")
    start = source.index("export const CAPTION_LANGUAGES")
    block = source[start : source.index("];", start)]
    return [m.group(1) for m in re.finditer(r"code:\s*'([a-z-]*)'", block)]


ALL_CLIENTS = {
    "host.html": _web_caption_codes("host.html"),
    "join.html": _web_caption_codes("join.html"),
    "mobile": _mobile_caption_codes(),
}


# ─── The three lists agree ───────────────────────────────────────────────────

def test_every_client_offers_the_same_caption_languages():
    """Host page, guest page and mobile app. A guest who cannot choose what the host can is
    the failure this prevents."""
    as_sets = {name: set(codes) for name, codes in ALL_CLIENTS.items()}
    reference = as_sets["host.html"]
    for name, codes in as_sets.items():
        assert codes == reference, f"{name} differs: {codes ^ reference}"


def test_as_spoken_is_offered_everywhere():
    """The empty code is "as spoken" — no translation at all, and the default."""
    for name, codes in ALL_CLIENTS.items():
        assert "" in codes, name


def test_no_client_lists_a_language_twice():
    for name, codes in ALL_CLIENTS.items():
        assert len(codes) == len(set(codes)), f"{name} repeats {codes}"


# ─── Farsi ───────────────────────────────────────────────────────────────────

def test_farsi_is_offered_for_captions():
    for name, codes in ALL_CLIENTS.items():
        assert "fa" in codes, name


def test_farsi_has_both_interface_dictionaries():
    for page in ("host", "join"):
        assert (WEB / "i18n" / f"{page}.{'fa'}.json").exists()


def test_farsi_survives_normalisation():
    """The code has to reach Amazon Translate in the form it accepts: "fa-IR" is refused
    where "fa" answers."""
    assert translation_service.normalise("fa") == "fa"
    assert translation_service.normalise("fa-IR") == "fa"


# ─── Every offered language has a dictionary ─────────────────────────────────

def test_the_interface_covers_every_caption_language():
    """No exceptions. A caption language with no interface dictionary would offer translated
    speech beside an English interface — the site speaking a language it does not read."""
    generate_targets = {
        m.group(1)
        for m in re.finditer(r'"([a-z]{2})"', _targets_block())
    }
    # English and French are written by hand inline, so they have no generated file.
    captions = set(ALL_CLIENTS["host.html"]) - {"", "en", "fr"}
    assert captions == generate_targets, f"difference: {captions ^ generate_targets}"


def _targets_block() -> str:
    generate = (WEB / "i18n" / "generate.py").read_text(encoding="utf-8")
    start = generate.index("TARGETS = [")
    return generate[start : generate.index("]", start)]


@pytest.mark.parametrize("page", ["host", "join"])
def test_every_interface_language_has_both_dictionaries(page):
    """A language in TARGETS with no file on disk would fall back to English silently."""
    for code in re.findall(r'"([a-z]{2})"', _targets_block()):
        assert (WEB / "i18n" / f"{page}.{code}.json").exists(), f"{page}.{code}.json missing"


# ─── Reachability and the product noun ───────────────────────────────────────

def _api_allowlist() -> set[str]:
    source = (
        pathlib.Path(__file__).resolve().parents[1] / "src" / "routers" / "guest_web.py"
    ).read_text(encoding="utf-8")
    start = source.index("_I18N_LANGUAGES = frozenset(")
    return set(re.findall(r'"([a-z]{2})"', source[start : source.index(")", start)]))


def test_every_generated_language_is_reachable():
    """The dictionaries are served through an allowlist, deliberately — the language is part of
    a path, and a constructed path is how directory traversal starts. The cost is one more list
    to keep in step: a file on disk that the allowlist does not name is unreachable, and the
    page falls back to English without saying why."""
    generated = set(re.findall(r'"([a-z]{2})"', _targets_block()))
    assert _api_allowlist() == generated, f"difference: {_api_allowlist() ^ generated}"


@pytest.mark.parametrize("page", ["host", "join"])
def test_the_product_noun_is_never_translated(page):
    """"Salon" became "salão de beleza" in Portuguese and the beauty-salon word in three other
    languages — the product renamed as a hairdresser. Both generators hold it back now, and this
    is what would catch a regeneration that lost the protection."""
    import json

    for code in re.findall(r'"([a-z]{2})"', _targets_block()):
        strings = json.loads(
            (WEB / "i18n" / f"{page}.{code}.json").read_text(encoding="utf-8")
        )
        # Any string that mentions a Salon must still spell it that way.
        for key, value in strings.items():
            if key in ("roomSub", "whatIsVocaliz", "salonEnded", "connectedTitle"):
                assert "Salon" in value, f"{page}.{code}.json {key}: {value}"
