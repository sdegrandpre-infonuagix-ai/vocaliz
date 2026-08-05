"""The participant report, on demand and in a browser.

Behind the same gate as everything else in the admin router: a token whose account is in
admin_emails, which today names one address. The page itself is public and empty — everything
it shows arrives from this endpoint — so these tests are about who gets the rows, and about the
rows being the same ones the hourly email carries.

That last point is the one worth guarding. Two readings of one table that could disagree would
be worse than having only the email, because the report is what decisions get made from.
"""
import pytest

from src.models.user import User
from src.services import participant_report
from src.services.jwt_service import issue_token


@pytest.fixture
def admin(db):
    """The address in admin_emails. Config defaults to it, so nothing is overridden here."""
    user = User(email="s.degrandpre@vocaliz.net")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user, issue_token(str(user.id))


@pytest.fixture
def outsider(db):
    user = User(email="somebody.else@example.com")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user, issue_token(str(user.id))


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


# ─── The gate ─────────────────────────────────────────────────────────────────

def test_without_a_token_there_is_nothing(client):
    assert client.get("/admin/report").status_code in (401, 403)


def test_a_signed_in_stranger_is_refused(client, outsider):
    """A valid account is not an administrator. Every host on the platform holds a token, so
    authentication alone would publish the whole participation table."""
    _, token = outsider
    assert client.get("/admin/report", headers=_auth(token)).status_code == 403


def test_the_administrator_gets_the_report(client, admin):
    _, token = admin
    resp = client.get("/admin/report", headers=_auth(token))
    assert resp.status_code == 200


# ─── The rows are the email's rows ────────────────────────────────────────────

def test_the_columns_are_the_ones_the_email_uses(client, admin, db):
    """Sent by the API rather than known by the page. They have changed twice already, and a
    page holding its own copy would draw yesterday's headings over today's figures."""
    _, token = admin
    body = client.get("/admin/report", headers=_auth(token)).json()
    assert body["columns"] == participant_report.COLUMNS


def test_the_rows_are_built_by_the_same_function_as_the_email(client, admin, db):
    """Not a second query that happens to look similar. One builder, so the page and the
    email cannot drift into telling different stories about the same table."""
    _, token = admin
    body = client.get("/admin/report", headers=_auth(token)).json()
    assert body["rows"] == participant_report.collect(db)


def test_the_count_matches_the_rows(client, admin):
    _, token = admin
    body = client.get("/admin/report", headers=_auth(token)).json()
    assert body["contacts"] == len(body["rows"])


def test_the_caveats_travel_with_the_figures(client, admin):
    """Several columns are weaker than they look. A reader who sees "Salons de cet appareil: 3"
    without them concludes three visits by one person, which is not what it measures."""
    _, token = admin
    body = client.get("/admin/report", headers=_auth(token)).json()
    assert body["caveats"], "the qualifications must not be optional"
    joined = " ".join(body["caveats"])
    for subject in ("Salons de cet appareil", "Micro", "Pays", "Secondes cumulees"):
        assert subject in joined


def test_the_caveats_are_not_a_second_copy_of_the_email_text():
    """Split from the block the email prints, never rewritten. Two copies of a paragraph this
    easy to leave alone drift the first time a column changes meaning."""
    assert "\n".join(participant_report.caveat_lines()) == participant_report._CAVEAT_TEXT


# ─── The page ─────────────────────────────────────────────────────────────────

def test_the_page_is_served(client):
    resp = client.get("/report")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]


def test_the_page_carries_no_data_of_its_own(client):
    """It is a shell. Anybody may load it; nobody sees a participation in it without a code."""
    body = client.get("/report").text
    assert "/admin/report" in body, "the page must fetch rather than embed"
    assert "@example.com" not in body


def test_the_page_asks_for_a_code_at_one_fixed_address(client):
    """Not a field. Typing the address would make this a login page for a platform with one
    administrator, and would let a visitor aim the code at themselves."""
    body = client.get("/report").text
    assert "s.degrandpre@vocaliz.net" in body
    assert "/auth/otp/request" in body
    assert 'type="email"' not in body


def test_the_page_renders_cells_as_text_rather_than_markup(client):
    """The values are addresses and identities typed by people, shown to the one person on
    this platform who could not afford to be phished."""
    body = client.get("/report").text
    assert "td.textContent" in body
    assert "td.innerHTML" not in body


def test_the_page_asks_not_to_be_indexed(client):
    """A search result linking here would invite exactly the attempts the code refuses."""
    assert "noindex" in client.get("/report").text
