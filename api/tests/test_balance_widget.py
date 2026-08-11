"""Gift and paid balance, shown top-right — before a Salon exists and inside one.

The same `/me/balance` endpoint host.html's tier chooser already reads from at creation
time (see api/tests/test_salons.py for that side); this only checks the two pages poll it
and render it, on the same clock as the metering tick (FR63) so it is never far behind
what a top-up or a spend actually did.
"""
import pathlib

WEB = pathlib.Path(__file__).resolve().parents[1] / "web"
PAGES = ("host.html", "join.html")


def _source(page: str) -> str:
    return (WEB / page).read_text(encoding="utf-8")


import pytest


@pytest.mark.parametrize("page", PAGES)
def test_the_widget_exists_and_starts_hidden(page):
    source = _source(page)
    assert 'id="balance-widget"' in source
    widget = source[source.index('id="balance-widget"') :]
    widget = widget[: widget.index(">")]
    assert 'style="display:none"' in widget


@pytest.mark.parametrize("page", PAGES)
def test_it_polls_on_the_same_clock_as_the_metering_tick(page):
    source = _source(page)
    assert "function startBalancePolling()" in source
    fn = source[source.index("function startBalancePolling()") :]
    fn = fn[: fn.index("\n    }" if "\n    }" in fn[:300] else "\n  }")]
    assert "setInterval(loadBalance, 5000)" in fn


@pytest.mark.parametrize("page", PAGES)
def test_no_token_means_no_balance_shown(page):
    """Signed out, or a guest whose account registration never landed — either way there
    is no /me/balance to ask, and the widget must say nothing rather than show stale or
    fabricated numbers."""
    source = _source(page)
    fn_name = "loadBalance"
    fn = source[source.index(f"async function {fn_name}()") :]
    fn = fn[: fn.index("\n    }" if "\n    }" in fn[:300] else "\n  }")]
    assert "renderBalance(null)" in fn


def test_the_host_console_polls_from_sign_in_not_only_inside_a_room():
    """The host chooses a tier before a Salon exists at all, and what they can afford is
    exactly the question that choice answers — so this has to be visible before creation,
    not only once a room is joined."""
    source = _source("host.html")
    fn = source[source.index("async function signedIn()") :]
    fn = fn[: fn.index("var pendingSalon")]
    assert "startBalancePolling()" in fn


def test_the_guest_page_polls_once_it_has_an_account_to_ask_about():
    """Every guest gets one the moment their microphone works (spendToken), whether or not
    they ever open the separate account-creation card."""
    source = _source("join.html")
    fn = source[source.index("function spendToken()") :]
    fn = fn[: fn.index("\n  }")]
    assert "startBalancePolling()" in fn
