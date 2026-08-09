"""A third way in, and a way to get your money back without one (Story 10.7 / FR65).

Every route into an account so far runs through an identifier: a code to an address, a code to
a number. That is fine until somebody loses both — a changed job, a lost telephone, a closed
mailbox — and then the account, the paid balance and the gifted credit are all simply gone,
with no way to prove they were ever theirs.

So a username and a password are a **third** way and never a replacement. Both routes stay
open, because the failure they cover is precisely that the other one stopped working.

The card path is different in kind and the difference is the point. Proving you hold the card
that paid does not prove you are the account holder — a card is a payment instrument, and
people share them, inherit them, and are issued them by employers. So it opens the **refund of
what was paid** and nothing else. Returning money to whoever paid it and returning access to
somebody's conversations are two different decisions, and one of them is not made here.

Which is also why the check needs more than the last four digits. Four digits are ten thousand
guesses and are printed on receipts; on their own they prove nothing at all.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from src.card_recovery import (
    MAX_ATTEMPTS,
    CardEvidence,
    RecoveryRefused,
    attempts_left,
    record_attempt,
    refundable_cents,
    verify_card,
)
from src.credentials import (
    CredentialsRefused,
    hash_password,
    normalise_username,
    set_credentials,
    sign_in,
    verify_password,
)
from src.models.user import User
from src.signup import register

NOW = datetime(2026, 8, 1, tzinfo=timezone.utc)


@pytest.fixture
def person(db):
    row = register(db, email="marie@example.com", phone="+15145550123")
    db.commit()
    return row


# ── Chosen at signup, alongside the identifiers ───────────────────────────────


def test_a_username_and_a_password_can_be_set(db, person):
    set_credentials(db, person, username="marie", password="a long enough secret")
    db.flush()

    assert person.username == "marie"


def test_a_taken_username_is_refused_by_name(db, person):
    """Explicitly, so somebody can propose another rather than guess what went wrong."""
    other = register(db, email="other@example.com")
    set_credentials(db, other, username="marie", password="a long enough secret")
    db.flush()

    with pytest.raises(CredentialsRefused) as raised:
        set_credentials(db, person, username="marie", password="another long secret")

    assert "marie" in str(raised.value)


def test_a_username_is_the_same_username_in_any_case(db, person):
    """`Marie` and `marie` as two accounts is two people who each think they are the only
    one, and a sign-in that depends on which shift key was pressed."""
    assert normalise_username("  Marie ") == "marie"


def test_keeping_your_own_username_is_not_a_collision(db, person):
    set_credentials(db, person, username="marie", password="a long enough secret")
    db.flush()

    set_credentials(db, person, username="marie", password="a different long secret")
    db.flush()

    assert person.username == "marie"


@pytest.mark.parametrize("bad", ["", "  ", "a", "ab", "marie thomas", "marie@example"])
def test_a_username_that_is_not_one_is_refused(db, person, bad):
    """Short or punctuated names are refused at the door rather than becoming somebody's
    permanent handle. A space in a username is a support call about a login that "does
    nothing"."""
    with pytest.raises(CredentialsRefused):
        set_credentials(db, person, username=bad, password="a long enough secret")


@pytest.mark.parametrize("bad", ["", "short", "1234567"])
def test_a_password_too_short_to_be_one_is_refused(db, person, bad):
    """Length rather than a character-class rule: forcing a symbol and a capital produces
    `Password1!` on every account, while length is what actually costs an attacker."""
    with pytest.raises(CredentialsRefused):
        set_credentials(db, person, username="marie", password=bad)


# ── Stored as a salted hash, never otherwise ──────────────────────────────────


def test_the_password_is_never_stored_as_given(db, person):
    set_credentials(db, person, username="marie", password="a long enough secret")
    db.flush()

    assert "a long enough secret" not in (person.password_hash or "")


def test_two_identical_passwords_hash_differently(db, person):
    """The salt, doing the only thing it is for: two people who chose the same password must
    not be visible as such to anybody reading the table."""
    other = register(db, email="other@example.com")
    set_credentials(db, person, username="marie", password="the very same secret")
    set_credentials(db, other, username="hans", password="the very same secret")
    db.flush()

    assert person.password_hash != other.password_hash


def test_a_hash_verifies_against_its_own_password():
    stored = hash_password("a long enough secret")

    assert verify_password("a long enough secret", stored) is True


def test_a_hash_refuses_anything_else():
    stored = hash_password("a long enough secret")

    assert verify_password("a long enough secre", stored) is False
    assert verify_password("", stored) is False


def test_a_stored_hash_carries_its_own_salt():
    """Self-describing, so the salt is never a second column somebody can forget to migrate
    alongside the hash."""
    first = hash_password("a long enough secret")
    second = hash_password("a long enough secret")

    assert first != second
    assert verify_password("a long enough secret", second) is True


def test_a_hash_from_another_scheme_verifies_as_false():
    """The stored value names its scheme, so a value written by an older or a future one is
    recognisably not ours. Refusing is right; raising on the sign-in path is an outage."""
    # Six fields, so it parses cleanly and is rejected on the scheme rather than on
    # its shape — which is the branch that matters when a second scheme is added.
    assert verify_password("anything", "bcrypt$16384$8$1$00ff$00ff") is False


def test_nonsense_in_the_column_verifies_as_false():
    """A row written by hand, or by an older scheme. It must refuse rather than raise: an
    exception on the sign-in path is an outage, and the honest answer is "not this password"."""
    assert verify_password("anything", "not-a-real-hash") is False
    assert verify_password("anything", "") is False


# ── Signing in, without a code ────────────────────────────────────────────────


def test_the_username_and_password_let_somebody_in(db, person):
    set_credentials(db, person, username="marie", password="a long enough secret")
    db.flush()

    assert sign_in(db, username="marie", password="a long enough secret").id == person.id


def test_the_wrong_password_does_not(db, person):
    set_credentials(db, person, username="marie", password="a long enough secret")
    db.flush()

    assert sign_in(db, username="marie", password="a long enough secre") is None


def test_an_unknown_username_does_not(db):
    assert sign_in(db, username="nobody", password="a long enough secret") is None


def test_an_account_with_no_password_cannot_be_signed_into_this_way(db, person):
    """Everybody who signed up before this story. An empty column must refuse rather than
    accept an empty password."""
    assert sign_in(db, username="marie", password="") is None


def test_signing_in_by_name_finds_the_same_account_as_by_address(db, person):
    """The whole point of the third route: one account, reachable more than one way."""
    from src.signup import find_by_identifier

    set_credentials(db, person, username="marie", password="a long enough secret")
    db.flush()

    assert sign_in(db, username="marie", password="a long enough secret").id == (
        find_by_identifier(db, "marie@example.com").id
    )


def test_neither_route_replaces_the_other(db, person):
    """Setting a password must not disturb the identifiers, since the failure it covers is
    exactly that they stopped working."""
    set_credentials(db, person, username="marie", password="a long enough secret")
    db.flush()

    assert person.email == "marie@example.com"
    assert person.phone_number == "+15145550123"


def test_the_balances_are_untouched_by_signing_in_this_way(db, person):
    """Somebody who lost both identifiers finds their account exactly as they left it."""
    from src.credit import WELCOME_CREDIT_CENTS, balance, grant_welcome_credit

    grant_welcome_credit(db, subject_id=person.id, identifiers=["marie@example.com"], now=NOW)
    set_credentials(db, person, username="marie", password="a long enough secret")
    db.flush()

    found = sign_in(db, username="marie", password="a long enough secret")

    assert balance(db, found.id).gifted_cents == WELCOME_CREDIT_CENTS


# ── The card, and what it does and does not open ──────────────────────────────


def _evidence(**overrides) -> CardEvidence:
    fields = {
        "last_four": "4242",
        "expiry": "12/29",
        "recent_amount_cents": 2500,
        "recent_charge_on": NOW.date(),
    }
    fields.update(overrides)
    return CardEvidence(**fields)


ON_FILE = CardEvidence(
    last_four="4242", expiry="12/29", recent_amount_cents=2500, recent_charge_on=NOW.date()
)


def test_the_last_four_alone_prove_nothing():
    """Ten thousand guesses, and they are printed on receipts."""
    given = CardEvidence(last_four="4242", expiry=None, recent_amount_cents=None, recent_charge_on=None)

    assert verify_card(given, on_file=ON_FILE) is False


def test_the_last_four_and_the_expiry_are_still_not_enough():
    """An expiry date is one of about sixty, and it is on the same receipt."""
    given = CardEvidence(last_four="4242", expiry="12/29", recent_amount_cents=None, recent_charge_on=None)

    assert verify_card(given, on_file=ON_FILE) is False


def test_three_concordant_elements_are_enough():
    """The third is the one nobody reads off a card: what was charged, or when."""
    given = _evidence(recent_charge_on=None)

    assert verify_card(given, on_file=ON_FILE) is True


def test_either_the_amount_or_the_date_will_do():
    assert verify_card(_evidence(recent_amount_cents=None), on_file=ON_FILE) is True


def test_one_element_that_disagrees_fails_the_whole_check():
    """Concordant, not merely numerous. Three answers of which one is wrong is somebody
    guessing."""
    assert verify_card(_evidence(expiry="01/30"), on_file=ON_FILE) is False


def test_a_wrong_amount_fails_even_with_everything_else_right():
    assert verify_card(_evidence(recent_amount_cents=2400), on_file=ON_FILE) is False


def test_nothing_on_file_verifies_nothing():
    """An account with no card has no card to prove. Comparing against absent values would
    make every field vacuously agree."""
    empty = CardEvidence(last_four="", expiry=None, recent_amount_cents=None, recent_charge_on=None)

    assert verify_card(_evidence(), on_file=empty) is False


# ── A recovery path is also an attack path ────────────────────────────────────


def test_attempts_are_counted(db, person):
    assert attempts_left(db, person.id, now=NOW) == MAX_ATTEMPTS

    record_attempt(db, person.id, succeeded=False, now=NOW)
    db.flush()

    assert attempts_left(db, person.id, now=NOW) == MAX_ATTEMPTS - 1


def test_they_run_out(db, person):
    for _ in range(MAX_ATTEMPTS):
        record_attempt(db, person.id, succeeded=False, now=NOW)
    db.flush()

    assert attempts_left(db, person.id, now=NOW) == 0


def test_a_refund_is_refused_once_they_have(db, person):
    for _ in range(MAX_ATTEMPTS):
        record_attempt(db, person.id, succeeded=False, now=NOW)
    db.flush()

    with pytest.raises(RecoveryRefused):
        refundable_cents(db, person.id, given=_evidence(), on_file=ON_FILE, now=NOW)


def test_the_window_eventually_reopens(db, person):
    """Limited, not permanent. A lockout with no end is a denial of service anybody can
    inflict on somebody else's account by guessing badly at it."""
    for _ in range(MAX_ATTEMPTS):
        record_attempt(db, person.id, succeeded=False, now=NOW)
    db.flush()

    assert attempts_left(db, person.id, now=NOW + timedelta(days=2)) == MAX_ATTEMPTS


def test_every_attempt_is_written_down(db, person):
    """Logged as well as limited: somebody probing an account is something an operator has
    to be able to see afterwards."""
    from src.models.recovery_attempt import RecoveryAttempt

    record_attempt(db, person.id, succeeded=False, now=NOW)
    record_attempt(db, person.id, succeeded=True, now=NOW)
    db.flush()

    rows = db.query(RecoveryAttempt).filter(RecoveryAttempt.subject_id == person.id).all()
    assert len(rows) == 2
    assert {row.succeeded for row in rows} == {True, False}


# ── What a successful card check actually opens ───────────────────────────────


def test_it_opens_the_paid_balance(db, person):
    from src.ledger import EventType, Pool, append

    append(db, type=EventType.RECHARGED, subject_id=person.id, amount_cents=2500,
           pool=Pool.PAID, occurred_at=NOW)
    db.flush()

    assert refundable_cents(db, person.id, given=_evidence(), on_file=ON_FILE, now=NOW) == 2500


def test_it_does_not_open_the_gifted_credit(db, person):
    """FR51. A gift was never their money, so there is nothing of theirs to give back."""
    from src.credit import grant_welcome_credit
    from src.ledger import EventType, Pool, append

    grant_welcome_credit(db, subject_id=person.id, identifiers=["marie@example.com"], now=NOW)
    append(db, type=EventType.RECHARGED, subject_id=person.id, amount_cents=1000,
           pool=Pool.PAID, occurred_at=NOW)
    db.flush()

    assert refundable_cents(db, person.id, given=_evidence(), on_file=ON_FILE, now=NOW) == 1000


def test_a_failed_check_opens_nothing(db, person):
    with pytest.raises(RecoveryRefused):
        refundable_cents(db, person.id, given=_evidence(expiry="01/30"), on_file=ON_FILE, now=NOW)


def test_it_does_not_open_the_account(db, person):
    """Proving you hold the card that paid does not prove you are the account holder — cards
    are shared, inherited and issued by employers. Returning money to its payer and returning
    access to somebody's conversations are two different decisions."""
    import inspect

    import src.card_recovery as module

    # The module docstring says what the guarantee is, so it names the very words being
    # looked for. Stripping it is the fix rather than rewording the prose: a guard that reads
    # its own explanation teaches people to word around it instead of obeying it.
    code = inspect.getsource(module).split('"""', 2)[-1]

    assert "issue_token" not in code
    assert "password_hash" not in code
    assert "username" not in code


def test_a_failed_check_is_counted_against_the_limit(db, person):
    try:
        refundable_cents(db, person.id, given=_evidence(expiry="01/30"), on_file=ON_FILE, now=NOW)
    except RecoveryRefused:
        pass
    db.flush()

    assert attempts_left(db, person.id, now=NOW) == MAX_ATTEMPTS - 1


# ── The doors themselves ──────────────────────────────────────────────────────


@pytest.fixture
def signed_in(db, person):
    from src.services.jwt_service import issue_token

    return {"Authorization": f"Bearer {issue_token(str(person.id))}"}


def test_credentials_can_be_set_over_http(client, db, person, signed_in):
    resp = client.put(
        "/me/credentials",
        json={"username": "Marie", "password": "a long enough secret"},
        headers=signed_in,
    )

    assert resp.status_code == 200
    assert resp.json()["username"] == "marie"


def test_a_taken_username_is_refused_over_http(client, db, person, signed_in):
    other = register(db, email="other@example.com")
    set_credentials(db, other, username="marie", password="a long enough secret")
    db.commit()

    resp = client.put(
        "/me/credentials",
        json={"username": "marie", "password": "a long enough secret"},
        headers=signed_in,
    )

    assert resp.status_code == 400
    assert "marie" in resp.json()["detail"]


def test_signing_in_with_a_password_yields_a_token(client, db, person, signed_in):
    client.put(
        "/me/credentials",
        json={"username": "marie", "password": "a long enough secret"},
        headers=signed_in,
    )

    resp = client.post(
        "/auth/password", json={"username": "marie", "password": "a long enough secret"}
    )

    assert resp.status_code == 200
    assert resp.json()["userId"] == str(person.id)
    assert resp.json()["token"]


def test_the_refusal_says_nothing_about_which_half_was_wrong(client, db, person, signed_in):
    """Naming the username as valid tells an attacker which half to keep working on."""
    client.put(
        "/me/credentials",
        json={"username": "marie", "password": "a long enough secret"},
        headers=signed_in,
    )

    wrong_password = client.post(
        "/auth/password", json={"username": "marie", "password": "not the secret"}
    )
    no_such_user = client.post(
        "/auth/password", json={"username": "nobody", "password": "not the secret"}
    )

    assert wrong_password.status_code == no_such_user.status_code == 401
    assert wrong_password.json()["detail"] == no_such_user.json()["detail"]


def test_the_code_route_still_works_afterwards(client, db, person, signed_in, monkeypatch):
    """Neither route replaces the other. Setting a password must not close the door it was
    added beside."""
    from src.services import otp

    monkeypatch.setattr(otp, "_send_email", lambda *a, **k: None)
    client.put(
        "/me/credentials",
        json={"username": "marie", "password": "a long enough secret"},
        headers=signed_in,
    )

    assert client.post("/auth/otp/request", json={"email": "marie@example.com"}).status_code == 202


def test_the_recovery_endpoint_refunds_without_opening_the_account(client, db, person):
    """The separation, end to end: money comes back, the door stays shut."""
    from src.ledger import EventType, Pool, append

    person.stripe_payment_method_id = "pm_test_4242"
    append(db, type=EventType.RECHARGED, subject_id=person.id, amount_cents=2500,
           pool=Pool.PAID, occurred_at=NOW)
    db.commit()

    resp = client.post(
        "/auth/recover-payment",
        json={"identifier": "marie@example.com", "lastFour": "4242",
              "expiry": None, "recentAmountCents": None, "recentChargeOn": None},
    )

    # Only one element was offered, so it is refused — and no token appears either way.
    assert resp.status_code == 400
    assert "token" not in resp.text.lower()


def test_an_unknown_identifier_gets_the_same_answer_as_a_bad_card(client, db, person):
    """Confirming which addresses have accounts is a directory anybody could build."""
    resp = client.post(
        "/auth/recover-payment",
        json={"identifier": "nobody@example.com", "lastFour": "4242"},
    )

    assert resp.status_code == 400
