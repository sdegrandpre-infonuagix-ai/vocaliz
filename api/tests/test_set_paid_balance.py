"""Setting one account's paid balance to an exact amount, by email.

Reachable only through lambda:InvokeFunction, like every maintenance action in this
module. There is no balance column to write — paid_balance is a fold over the ledger
stream — so this reads the current total and appends one event for the difference, the
same as topup_all_accounts does for every account at once rather than one by email.
"""
from unittest.mock import patch

import pytest

from src import migrate_handler
from src.credit import balance
from src.models.user import User


@pytest.fixture
def account(db):
    user = User(email="target@example.com")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _run(db, **event):
    with patch("src.database.SessionLocal", return_value=db), patch.object(db, "close"):
        return migrate_handler.handler({"action": "set_paid_balance", **event}, None)


def test_a_fresh_account_is_set_to_the_target(db, account):
    result = _run(db, email=account.email, targetCents=10000)
    assert result["status"] == "ok"
    assert result["previousPaidCents"] == 0
    assert result["paidCents"] == 10000
    assert result["deltaCents"] == 10000
    assert balance(db, account.id).paid_cents == 10000


def test_an_existing_balance_is_corrected_by_the_difference_not_added_to(db, account):
    _run(db, email=account.email, targetCents=2000)
    result = _run(db, email=account.email, targetCents=10000)
    assert result["deltaCents"] == 8000
    assert balance(db, account.id).paid_cents == 10000


def test_a_lower_target_debits_the_difference(db, account):
    _run(db, email=account.email, targetCents=10000)
    result = _run(db, email=account.email, targetCents=3000)
    assert result["deltaCents"] == -7000
    assert balance(db, account.id).paid_cents == 3000


def test_already_at_the_target_is_a_no_op(db, account):
    _run(db, email=account.email, targetCents=10000)
    result = _run(db, email=account.email, targetCents=10000)
    assert result["status"] == "unchanged"
    assert balance(db, account.id).paid_cents == 10000


def test_gifted_credit_is_never_touched(db, account):
    """Paid and gifted are different money — a correction to one must not reset the
    other's own thirty-day clock (FR67) by writing into that pool instead."""
    _run(db, email=account.email, targetCents=10000)
    assert balance(db, account.id).gifted_cents == 0


def test_an_unknown_email_is_reported_not_guessed(db):
    result = _run(db, email="nobody@example.com", targetCents=10000)
    assert result == {"status": "not_found", "email": "nobody@example.com"}
