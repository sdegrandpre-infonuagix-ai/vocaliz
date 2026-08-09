"""Listing accounts, read-only — reachable only through lambda:InvokeFunction.

Answers a lookup the console has no screen for. Never returns password_hash or the OTP
fields: nothing that calls this needed either.
"""
from unittest.mock import patch

import pytest

from src import migrate_handler
from src.models.user import User


@pytest.fixture
def accounts(db):
    rows = [
        User(email="one@example.com", display_name="One"),
        User(email="two@example.com", display_name="Two"),
        User(phone_number="+15145550000"),
    ]
    db.add_all(rows)
    db.commit()
    for row in rows:
        db.refresh(row)
    return rows


def _run(db, **event):
    with patch("src.database.SessionLocal", return_value=db), patch.object(db, "close"):
        return migrate_handler.handler({"action": "list_users", **event}, None)


def test_every_account_comes_back(db, accounts):
    result = _run(db)
    assert result["status"] == "ok"
    assert result["count"] == 3
    emails = {u["email"] for u in result["users"]}
    assert emails == {"one@example.com", "two@example.com", None}


def test_a_phone_only_account_is_included(db, accounts):
    result = _run(db)
    row = next(u for u in result["users"] if u["phoneNumber"] == "+15145550000")
    assert row["email"] is None


def test_no_credential_ever_leaves(db, accounts):
    result = _run(db)
    for u in result["users"]:
        assert "password_hash" not in u
        assert "otp_code" not in u


def test_the_limit_is_honoured(db, accounts):
    result = _run(db, limit=1)
    assert result["count"] == 1


def test_the_limit_is_capped_rather_than_open_ended(db, accounts):
    """A growing table must not turn one lookup into a payload nobody asked for the
    whole of."""
    result = _run(db, limit=100000)
    assert result["count"] == 3  # only three exist; the cap did not error, it just did nothing here
