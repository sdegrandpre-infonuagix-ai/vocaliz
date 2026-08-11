"""The cookie consent banner: accept, decline, or say nothing yet.

Nothing on these pages sets an actual HTTP cookie — every preference (language, caption
size, sound, the device token) lives in localStorage — but the choice on offer is the one a
cookie banner asks for, so declining has to mean the same thing a real one would: the page
stops reading or writing anything through it, except the choice itself, which must survive
the decision or the banner would ask again on every visit.
"""
import pathlib
import re

import pytest

WEB = pathlib.Path(__file__).resolve().parents[1] / "web"
PAGES = ("index.html", "host.html", "join.html")


def _source(page: str) -> str:
    return (WEB / page).read_text(encoding="utf-8")


# ─── Every preference is gated ────────────────────────────────────────────────
#
# The one regression this whole file exists to catch: a future preference added straight
# against localStorage, bypassing the gate silently. Counted rather than merely searched
# for, so a new raw call anywhere in the page fails this even if it happens to also call
# prefGet/prefSet right next to it.

@pytest.mark.parametrize("page", PAGES)
def test_every_localstorage_call_is_inside_the_consent_wrapper(page):
    source = _source(page)
    wrapper_start = source.index("function cookieConsent()")
    wrapper_end = source.index(
        "function acceptCookies()" if "function acceptCookies()" in source[wrapper_start:]
        else "function declineCookies()",
        wrapper_start,
    )
    # Extend to the end of declineCookies(), the last function in the block.
    wrapper_end = source.index("\n", source.index("function declineCookies()", wrapper_start))
    wrapper = source[wrapper_start:wrapper_end]

    total = len(re.findall(r"localStorage\.", source))
    inside = len(re.findall(r"localStorage\.", wrapper))
    assert total == inside, (
        f"{page}: {total - inside} localStorage call(s) outside the consent wrapper"
    )


@pytest.mark.parametrize("page", PAGES)
def test_the_wrapper_gates_on_accepted(page):
    source = _source(page)
    assert "function prefGet(key)" in source
    assert "function prefSet(key, value)" in source
    block = source[source.index("function prefGet(key)") : source.index("function prefSet(key, value)")]
    assert "cookieConsent() !== 'accepted'" in block


# ─── The banner itself ────────────────────────────────────────────────────────

@pytest.mark.parametrize("page", PAGES)
def test_the_banner_exists_with_both_choices(page):
    source = _source(page)
    assert 'id="cookie-banner"' in source
    assert 'onclick="acceptCookies()"' in source
    assert 'onclick="declineCookies()"' in source


@pytest.mark.parametrize("page", PAGES)
def test_the_banner_starts_hidden(page):
    """Shown only for a visitor who has not yet decided — the boot sequence reveals it,
    not the markup."""
    source = _source(page)
    banner = source[source.index('id="cookie-banner"') :]
    banner = banner[: banner.index(">")]
    assert 'style="display:none"' in banner


@pytest.mark.parametrize("page", PAGES)
def test_an_undecided_visitor_sees_the_banner(page):
    source = _source(page)
    assert "if (!cookieConsent())" in source


@pytest.mark.parametrize("page", PAGES)
def test_choosing_either_way_hides_the_banner_and_remembers_it(page):
    """The choice itself is written unconditionally — see setCookieConsent — because a
    decline that could not be remembered would ask again on the very next page."""
    source = _source(page)
    fn = source[source.index("function setCookieConsent(choice)") :]
    fn = fn[: fn.index("\n    }" if "\n    }" in fn[:400] else "\n  }")]
    assert "localStorage.setItem(COOKIE_CONSENT_KEY, choice)" in fn
    assert "style.display = 'none'" in fn


@pytest.mark.parametrize("page", PAGES)
def test_both_i18n_keys_are_bundled_in_english_and_french(page):
    source = _source(page)
    head = source[: source.index("function T(")]
    en_block = head[head.index("en:") : head.index("fr:")]
    fr_block = head[head.index("fr:") :]
    for key in ("cookieMsg", "cookieAccept", "cookieDecline"):
        assert f"{key}:" in en_block, f"{page}: {key} missing from English"
        assert f"{key}:" in fr_block, f"{page}: {key} missing from French"
