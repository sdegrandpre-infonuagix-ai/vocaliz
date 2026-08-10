"""Crediting every account's paid balance by the same amount, once.

Reachable only through lambda:InvokeFunction, like every maintenance action in this
module. Written as one RECHARGED ledger event per account rather than a stored total —
the same reasoning as everywhere else in credit.py: a balance that was computed can be
explained event by event, one that was only ever stored cannot.
"""
from unittest.mock import patch

import pytest

from src import migrate_handler
from src.credit import balance
from src.models.user import User


@pytest.fixture
def accounts(db):
    rows = [
        User(email="one@example.com"),
        User(email="two@example.com"),
        User(email="three@example.com"),
    ]
    db.add_all(rows)
    db.commit()
    for row in rows:
        db.refresh(row)
    return rows


def _run(db, **event):
    with patch("src.database.SessionLocal", return_value=db), patch.object(db, "close"):
        return migrate_handler.handler({"action": "topup_all_accounts", **event}, None)


def test_every_account_is_credited(db, accounts):
    result = _run(db, amountCents=2000)
    assert result["status"] == "ok"
    assert result["accounts"] == 3
    for user in accounts:
        assert balance(db, user.id).paid_cents == 2000


def test_the_default_amount_is_twenty_dollars(db, accounts):
    _run(db)
    assert balance(db, accounts[0].id).paid_cents == 2000


def test_it_stacks_with_whatever_is_already_there(db, accounts):
    _run(db, amountCents=500)
    _run(db, amountCents=2000)
    assert balance(db, accounts[0].id).paid_cents == 2500


def test_gifted_credit_is_never_touched(db, accounts):
    """Paid and gifted are different money — gifted still carries its own thirty-day
    clock (FR67), which a top-up must not reset by writing into that pool instead."""
    _run(db, amountCents=2000)
    assert balance(db, accounts[0].id).gifted_cents == 0
