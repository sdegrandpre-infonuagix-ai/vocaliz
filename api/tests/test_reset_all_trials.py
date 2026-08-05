"""Clearing metered time for every account at once.

Reachable only through lambda:InvokeFunction — the maintenance function sits behind IAM and is
not wired to API Gateway. It exists because exhausting the trial is the expected outcome of
heavy testing, and the alternative was attaching a real payment method to keep testing.

Tested because it cannot be undone. The seconds it clears are recorded nowhere else, so an
action that cleared the wrong rows, or half of each row, would be discovered by its absence.
"""
from unittest.mock import patch

import pytest

from src import migrate_handler
from src.models.user import User


@pytest.fixture
def accounts(db):
    rows = [
        User(email="one@example.com", trial_seconds_used=900, billed_seconds=300),
        User(email="two@example.com", trial_seconds_used=1800, billed_seconds=0),
        User(email="three@example.com", trial_seconds_used=0, billed_seconds=0),
    ]
    db.add_all(rows)
    db.commit()
    for row in rows:
        db.refresh(row)
    return rows


def _run(db):
    with patch("src.database.SessionLocal", return_value=db), patch.object(db, "close"):
        return migrate_handler.handler({"action": "reset_all_trials"}, None)


def test_every_account_is_cleared(db, accounts):
    result = _run(db)
    assert result["status"] == "ok"
    assert result["accounts"] == 3
    assert all(u.trial_seconds_used == 0 for u in db.query(User).all())


def test_both_counters_go_together(db, accounts):
    """Clearing the metered seconds while leaving billed_seconds behind would leave an account
    charged for time it no longer shows as used — the delta between the two is what the next
    invoice reads."""
    _run(db)
    assert all(u.billed_seconds == 0 for u in db.query(User).all())


def test_the_total_cleared_is_reported(db, accounts):
    """The only receipt. Nothing else records what was there before, so a run that silently
    cleared nothing would look exactly like a run that cleared everything."""
    assert _run(db)["secondsCleared"] == 2700


def test_an_account_at_zero_is_counted_but_costs_nothing(db, accounts):
    """The count is accounts touched, not accounts that had time on them — otherwise a run
    that missed somebody and a run that found them already empty would report the same."""
    result = _run(db)
    assert result["accounts"] == 3
    assert result["secondsCleared"] == 2700


def test_no_accounts_is_not_an_error(db):
    result = _run(db)
    assert result == {"status": "ok", "accounts": 0, "secondsCleared": 0}


def test_a_blank_email_does_not_reach_the_whole_platform(db, accounts):
    """The single-account action is given an address and must find nobody when it is blank.
    Treating "no address" as "everybody" is the mistake this separation exists to prevent."""
    with patch("src.database.SessionLocal", return_value=db), patch.object(db, "close"):
        result = migrate_handler.handler({"action": "reset_trial", "email": ""}, None)
    assert result["status"] == "not_found"
    assert db.query(User).filter(User.trial_seconds_used > 0).count() == 2
