"""The caption languages are declared in three places and nothing kept them in step.

host.html, join.html and the mobile app each carry their own list. A language added to one and
forgotten in another is invisible until somebody joins from the wrong client and finds a
language their friend can choose and they cannot — and the two pages are the host and guest
halves of the same conversation, so a divergence there splits one salon.

Farsi is the case that prompted this: added for captions, deliberately not added to the
interface dictionaries. That asymmetry is a decision, so it is written down here rather than
left for the next person to discover and "correct".
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


def test_farsi_survives_normalisation():
    """The code has to reach Amazon Translate in the form it accepts: "fa-IR" is refused
    where "fa" answers."""
    assert translation_service.normalise("fa") == "fa"
    assert translation_service.normalise("fa-IR") == "fa"


def test_farsi_is_deliberately_absent_from_the_interface_languages():
    """Captions are translated by Amazon Translate at request time; the interface is a
    committed dictionary per language. Offering Farsi captions costs nothing extra, translating
    the interface means two more generated files nobody here can review.

    If Farsi interface dictionaries are ever added, this test should be deleted along with the
    note in generate.py — it exists to make the gap deliberate, not permanent.
    """
    generate = (WEB / "i18n" / "generate.py").read_text(encoding="utf-8")
    targets = generate[generate.index("TARGETS = [") : generate.index("]", generate.index("TARGETS = ["))]
    assert '"fa"' not in targets
    assert not (WEB / "i18n" / "host.fa.json").exists()
    # And the reason is recorded where somebody would go to change it.
    assert "Farsi is offered for captions" in generate


# ─── The interface languages are otherwise the caption languages ─────────────

def test_the_interface_covers_every_other_caption_language():
    """Everything except Farsi and the two hand-written languages must have a dictionary, or a
    reader gets translated speech beside an English interface without anyone deciding that."""
    generate_targets = {
        m.group(1)
        for m in re.finditer(r'"([a-z]{2})"', _targets_block())
    }
    captions = set(ALL_CLIENTS["host.html"]) - {"", "en", "fr", "fa"}
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
