"""What is owed to users, folded out of the same event stream (FR68 / NFR7).

The mirror of Story 8.11, and the distinction between them is the whole point. A gifted credit
is a **charge** — money Vocaliz spent to acquire somebody. A paid balance is a **debt** —
money a user handed over that has not yet been turned into service. Adding the two together
would make both unreadable, so they are never mixed and never summed.

Four movements, not three. Collected, consumed and refunded describe what happened *during* a
period; outstanding describes what is still owed *at the end of it*. A refund is deliberately
kept apart from consumption: money going back out is not money earned, and folding it into
consumption would report revenue that was handed back.

And a paid balance never expires. Somebody who stops using Vocaliz is still owed what they
put in, indefinitely — which is why dormant balances have to be isolatable by age, and why
the holder is written to every year while the money is still theirs.
"""
import uuid
from datetime import datetime, timedelta, timezone

from src.credit import debit, grant_welcome_credit
from src.ledger import EventType, Pool, append
from src.paid_journal import (
    DORMANCY_YEARS,
    REMINDER_COPY_TO,
    dormant_balances,
    outstanding_cents,
    paid_totals,
    reminder_due,
    reminder_text,
)

START = datetime(2026, 1, 1, tzinfo=timezone.utc)
A_YEAR_ON = START + timedelta(days=365)


def _paid_in(db, person, cents, *, at=START):
    append(
        db,
        type=EventType.RECHARGED,
        subject_id=person,
        amount_cents=cents,
        pool=Pool.PAID,
        occurred_at=at,
    )
    db.flush()


# ── The four movements ────────────────────────────────────────────────────────


def test_a_successful_top_up_is_collected(db):
    person = uuid.uuid4()
    _paid_in(db, person, 2000)

    totals = paid_totals(db, since=START, until=A_YEAR_ON)

    assert totals.collected_cents == 2000


def test_spending_the_paid_balance_is_consumed(db):
    """The part of the prepayment actually turned into service rendered."""
    person = uuid.uuid4()
    _paid_in(db, person, 2000)
    debit(db, person, cents=500, now=START)
    db.flush()

    totals = paid_totals(db, since=START, until=A_YEAR_ON)

    assert totals.consumed_cents == 500


def test_a_refund_is_kept_apart_from_consumption(db):
    """Money going back out is not money earned. Folding a refund into consumption would
    report revenue that was handed back."""
    person = uuid.uuid4()
    _paid_in(db, person, 2000)
    append(
        db,
        type=EventType.REFUNDED,
        subject_id=person,
        amount_cents=-800,
        pool=Pool.PAID,
        occurred_at=START,
    )
    db.flush()

    totals = paid_totals(db, since=START, until=A_YEAR_ON)

    assert totals.refunded_cents == 800
    assert totals.consumed_cents == 0


def test_what_is_still_owed_is_reported_alongside(db):
    """Three movements describe the period; outstanding describes the moment it closed."""
    person = uuid.uuid4()
    _paid_in(db, person, 2000)
    debit(db, person, cents=500, now=START)
    db.flush()

    totals = paid_totals(db, since=START, until=A_YEAR_ON)

    assert totals.outstanding_cents == 1500


def test_the_four_are_never_collapsed_into_one(db):
    person = uuid.uuid4()
    _paid_in(db, person, 2000)
    debit(db, person, cents=500, now=START)
    db.flush()

    totals = paid_totals(db, since=START, until=A_YEAR_ON)

    assert (totals.collected_cents, totals.consumed_cents, totals.refunded_cents) == (
        2000,
        500,
        0,
    )


def test_a_movement_outside_the_period_is_not_counted(db):
    person = uuid.uuid4()
    _paid_in(db, person, 2000, at=START)

    totals = paid_totals(db, since=A_YEAR_ON, until=A_YEAR_ON + timedelta(days=30))

    assert totals.collected_cents == 0


# ── A debt, never a charge ────────────────────────────────────────────────────


def test_a_gifted_credit_never_appears_in_the_liability(db):
    """One is a debt to a user, the other a cost of acquiring them. Summing the two would
    make both unreadable."""
    person = uuid.uuid4()
    grant_welcome_credit(db, subject_id=person, identifiers=["a@example.com"], now=START)
    db.flush()

    assert outstanding_cents(db) == 0


def test_spending_gifted_credit_is_not_consumption_of_the_paid_balance(db):
    person = uuid.uuid4()
    grant_welcome_credit(db, subject_id=person, identifiers=["a@example.com"], now=START)
    db.flush()
    debit(db, person, cents=300, now=START)
    db.flush()

    totals = paid_totals(db, since=START, until=A_YEAR_ON)

    assert totals.consumed_cents == 0


def test_the_liability_is_the_sum_across_everybody(db):
    """What is owed is a figure about Vocaliz, not about one person."""
    first, second = uuid.uuid4(), uuid.uuid4()
    _paid_in(db, first, 2000)
    _paid_in(db, second, 500)

    assert outstanding_cents(db) == 2500


def test_a_spent_balance_is_no_longer_owed(db):
    person = uuid.uuid4()
    _paid_in(db, person, 2000)
    debit(db, person, cents=2000, now=START)
    db.flush()

    assert outstanding_cents(db) == 0


# ── Dormant money stays owed ──────────────────────────────────────────────────


def test_a_paid_balance_never_expires(db):
    """Unlike a gifted credit. Somebody who stopped using Vocaliz is still owed what they
    put in, however long ago."""
    person = uuid.uuid4()
    _paid_in(db, person, 2000)

    assert outstanding_cents(db, as_of=START + timedelta(days=3650)) == 2000


def test_dormant_balances_can_be_isolated_by_age(db):
    """Which is what makes the liability manageable rather than merely large."""
    recent, old = uuid.uuid4(), uuid.uuid4()
    _paid_in(db, recent, 2000, at=A_YEAR_ON)
    _paid_in(db, old, 500, at=START)

    dormant = dormant_balances(db, as_of=A_YEAR_ON + timedelta(days=1))

    assert [row.subject_id for row in dormant] == [old]


def test_a_dormant_row_carries_the_amount_and_the_age(db):
    person = uuid.uuid4()
    _paid_in(db, person, 500, at=START)

    row, = dormant_balances(db, as_of=A_YEAR_ON + timedelta(days=1))

    assert row.balance_cents == 500
    assert row.last_activity_at == START


def test_an_empty_balance_is_never_dormant(db):
    """There is nothing to be owed, so there is nothing to isolate."""
    person = uuid.uuid4()
    _paid_in(db, person, 500, at=START)
    debit(db, person, cents=500, now=START)
    db.flush()

    assert dormant_balances(db, as_of=A_YEAR_ON + timedelta(days=1)) == []


def test_activity_resets_the_clock(db):
    person = uuid.uuid4()
    _paid_in(db, person, 2000, at=START)
    debit(db, person, cents=100, now=A_YEAR_ON)
    db.flush()

    assert dormant_balances(db, as_of=A_YEAR_ON + timedelta(days=1)) == []


# ── Writing to somebody whose money is sitting there ──────────────────────────


def test_the_anniversary_is_a_year(db):
    assert DORMANCY_YEARS == 1


def test_a_reminder_is_due_after_a_year_of_silence(db):
    person = uuid.uuid4()
    _paid_in(db, person, 2000, at=START)

    assert reminder_due(db, person, as_of=A_YEAR_ON + timedelta(days=1)) is True


def test_no_reminder_before_the_anniversary(db):
    person = uuid.uuid4()
    _paid_in(db, person, 2000, at=START)

    assert reminder_due(db, person, as_of=START + timedelta(days=200)) is False


def test_nobody_is_written_to_about_an_empty_balance(db):
    """There is nothing to claim, and a letter saying so is a letter that should not have
    been sent."""
    person = uuid.uuid4()
    _paid_in(db, person, 500, at=START)
    debit(db, person, cents=500, now=START)
    db.flush()

    assert reminder_due(db, person, as_of=A_YEAR_ON + timedelta(days=1)) is False


def test_a_reminder_already_sent_this_year_is_not_repeated(db):
    person = uuid.uuid4()
    _paid_in(db, person, 2000, at=START)
    append(
        db,
        type=EventType.DORMANT_REMINDED,
        subject_id=person,
        occurred_at=A_YEAR_ON + timedelta(days=1),
        detail="2000",
    )
    db.flush()

    assert reminder_due(db, person, as_of=A_YEAR_ON + timedelta(days=30)) is False


def test_another_year_of_silence_earns_another_reminder(db):
    """Every anniversary, for as long as the money is still theirs and still untouched."""
    person = uuid.uuid4()
    _paid_in(db, person, 2000, at=START)
    append(
        db,
        type=EventType.DORMANT_REMINDED,
        subject_id=person,
        occurred_at=A_YEAR_ON,
        detail="2000",
    )
    db.flush()

    assert reminder_due(db, person, as_of=A_YEAR_ON + timedelta(days=366)) is True


def test_the_reminder_states_the_amount_still_held(db):
    text = reminder_text(balance_cents=2000)

    assert "20.00" in text


def test_the_reminder_says_the_account_is_inactive(db):
    text = reminder_text(balance_cents=2000).lower()

    assert "inactive" in text
    assert "vocaliz" in text


def test_a_copy_goes_to_the_operator(db):
    assert REMINDER_COPY_TO == "s.degrandpre@vocaliz.net"


def test_every_reminder_is_journalled_in_the_same_stream(db):
    """The trace of what was done to reach the holder of dormant money. In the one stream,
    like everything else — a second log of it would be the mistake Story 8.1 removed."""
    person = uuid.uuid4()
    _paid_in(db, person, 2000, at=START)
    append(
        db,
        type=EventType.DORMANT_REMINDED,
        subject_id=person,
        occurred_at=A_YEAR_ON,
        detail="2000",
    )
    db.flush()

    from src.models.ledger_event import LedgerEvent

    row = (
        db.query(LedgerEvent)
        .filter(LedgerEvent.type == EventType.DORMANT_REMINDED.value)
        .one()
    )

    assert row.subject_id == person
    assert row.detail == "2000"


# ── Derived, like everything else ─────────────────────────────────────────────


def test_there_is_no_table_behind_this_either(db):
    import pathlib

    text = (
        pathlib.Path(__file__).resolve().parents[1] / "src" / "paid_journal.py"
    ).read_text(encoding="utf-8")
    code = text.split('"""', 2)[-1]

    assert "__tablename__" not in code
    assert "db.add" not in code


def test_reading_it_twice_gives_the_same_answer(db):
    person = uuid.uuid4()
    _paid_in(db, person, 2000)

    assert paid_totals(db, since=START, until=A_YEAR_ON) == paid_totals(
        db, since=START, until=A_YEAR_ON
    )
