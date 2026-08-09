"""What every gifted credit cost, folded out of the event stream (FR67 / NFR7).

A derived view and never a parallel write — the last acceptance criterion, and the one that
decides the shape of everything else. Story 8.1 established that two records of one fact
drift; this is the first place somebody would have been tempted to add a second table, so it
is worth stating plainly that there isn't one.

Each credit carries four amounts, and the invariant `issued = consumed + expired + abandoned`
holds for every closed entry. Three closing modes rather than two, because an account deleted
mid-credit is neither consumption nor expiry: without `abandoned` as its own state, every
period total would be silently wrong from the first deletion onwards — the worst kind of
wrong, since nothing would look broken.

Only what was **consumed** is an expense. It alone bought provider time. A credit that expired
untouched cost nothing at all, and booking it as spend would inflate the acquisition cost with
money that never left.
"""
import uuid
from datetime import datetime, timedelta, timezone

from src.credit import debit, expire_credit, grant_welcome_credit
from src.credit_journal import (
    CreditType,
    acquisition_cost_cents,
    credit_entries,
    period_totals,
)
from src.ledger import EventType, Pool, append
from src.reactivation import grant_second_credit

OPERATOR = uuid.uuid4()
START = datetime(2026, 1, 1, tzinfo=timezone.utc)
LATER = START + timedelta(days=120)


def _welcome(db, person, *, at=START):
    grant_welcome_credit(
        db, subject_id=person, identifiers=[f"{uuid.uuid4()}@example.com"], now=at
    )
    db.flush()


def _reactivation(db, person, *, at=LATER, cents=None, reason="win-back"):
    grant_second_credit(
        db,
        subject_id=person,
        amount_cents=cents,
        reason=reason,
        operator_id=OPERATOR,
        now=at,
    )
    db.flush()


# ── An entry per credit, with what it is ──────────────────────────────────────


def test_a_welcome_credit_produces_an_entry(db):
    person = uuid.uuid4()
    _welcome(db, person)

    entry, = credit_entries(db, subject_id=person)

    assert entry.subject_id == person
    assert entry.credit_type is CreditType.WELCOME
    assert entry.issued_cents == 500
    assert entry.issued_at == START


def test_a_welcome_credit_is_issued_by_the_system(db):
    person = uuid.uuid4()
    _welcome(db, person)

    entry, = credit_entries(db, subject_id=person)

    assert entry.author == "system"
    assert entry.operator_id is None


def test_the_entry_carries_the_expiry_date(db):
    from src.credit import expires_at

    person = uuid.uuid4()
    _welcome(db, person)

    entry, = credit_entries(db, subject_id=person)

    assert entry.expires_at == expires_at(START)


def test_a_reactivation_credit_produces_an_entry_of_the_same_shape(db):
    person = uuid.uuid4()
    _reactivation(db, person, reason="february win-back")

    entry, = credit_entries(db, subject_id=person)

    assert entry.credit_type is CreditType.REACTIVATION
    assert entry.issued_cents == 300
    assert entry.author == "operator"
    assert entry.operator_id == OPERATOR
    assert "february win-back" in entry.reason


def test_the_paid_balance_never_appears_here(db):
    """A gifted credit is an acquisition cost; a paid balance is a liability to the user.
    Mixing them would make the acquisition cost include money somebody handed over."""
    person = uuid.uuid4()
    append(
        db,
        type=EventType.RECHARGED,
        subject_id=person,
        amount_cents=2000,
        pool=Pool.PAID,
        occurred_at=START,
    )
    db.flush()

    assert credit_entries(db, subject_id=person) == []


# ── Four amounts, and the invariant ───────────────────────────────────────────


def test_a_fresh_credit_has_consumed_nothing(db):
    person = uuid.uuid4()
    _welcome(db, person)

    entry, = credit_entries(db, subject_id=person)

    assert (entry.consumed_cents, entry.expired_cents, entry.abandoned_cents) == (0, 0, 0)
    assert entry.closed is False


def test_spending_moves_the_amount_into_consumed(db):
    person = uuid.uuid4()
    _welcome(db, person)
    debit(db, person, cents=200, now=START)
    db.flush()

    entry, = credit_entries(db, subject_id=person)

    assert entry.consumed_cents == 200
    assert entry.closed is False


def test_expiry_closes_the_entry_and_books_the_remainder(db):
    person = uuid.uuid4()
    _welcome(db, person)
    debit(db, person, cents=200, now=START)
    db.flush()
    expire_credit(db, person, now=START + timedelta(days=31))
    db.flush()

    entry, = credit_entries(db, subject_id=person)

    assert entry.consumed_cents == 200
    assert entry.expired_cents == 300
    assert entry.closed is True


def test_the_invariant_holds_on_a_closed_entry(db):
    person = uuid.uuid4()
    _welcome(db, person)
    debit(db, person, cents=200, now=START)
    db.flush()
    expire_credit(db, person, now=START + timedelta(days=31))
    db.flush()

    entry, = credit_entries(db, subject_id=person)

    assert entry.issued_cents == (
        entry.consumed_cents + entry.expired_cents + entry.abandoned_cents
    )


def test_a_credit_spent_to_nothing_is_closed_by_the_spending(db):
    person = uuid.uuid4()
    _welcome(db, person)
    debit(db, person, cents=500, now=START)
    db.flush()

    entry, = credit_entries(db, subject_id=person)

    assert entry.consumed_cents == 500
    assert entry.closed is True


# ── The third closing mode ────────────────────────────────────────────────────


def test_a_deleted_account_abandons_what_was_left(db):
    """Neither consumption nor expiry. Without this as its own state every period total
    would be silently wrong from the first deletion — the worst kind of wrong, because
    nothing looks broken."""
    person = uuid.uuid4()
    _welcome(db, person)
    debit(db, person, cents=100, now=START)
    db.flush()
    append(
        db,
        type=EventType.ABANDONED,
        subject_id=person,
        amount_cents=-400,
        pool=Pool.GIFTED,
        occurred_at=START + timedelta(days=5),
    )
    db.flush()

    entry, = credit_entries(db, subject_id=person)

    assert entry.abandoned_cents == 400
    assert entry.closed is True
    assert entry.issued_cents == (
        entry.consumed_cents + entry.expired_cents + entry.abandoned_cents
    )


def test_an_abandoned_credit_is_not_counted_as_consumption(db):
    """Nobody used it, so it bought nothing."""
    person = uuid.uuid4()
    _welcome(db, person)
    append(
        db,
        type=EventType.ABANDONED,
        subject_id=person,
        amount_cents=-500,
        pool=Pool.GIFTED,
        occurred_at=START,
    )
    db.flush()

    entry, = credit_entries(db, subject_id=person)

    assert entry.consumed_cents == 0


def test_the_entry_survives_the_account(db):
    """A charge once booked does not vanish because somebody left. The ledger has no foreign
    key to a user, which is what makes this true rather than merely intended."""
    from src.models.ledger_event import LedgerEvent

    person = uuid.uuid4()
    _welcome(db, person)

    assert LedgerEvent.__table__.c.subject_id.foreign_keys == set()
    assert credit_entries(db, subject_id=person) != []


# ── Spending is attributed to the credit that funds it ────────────────────────


def test_a_debit_is_charged_to_the_oldest_open_credit(db):
    """Somebody may hold two credits at once. Attributing spending to the wrong one would
    make each entry's consumed amount wrong even while the total stayed right."""
    person = uuid.uuid4()
    _welcome(db, person)
    _reactivation(db, person)
    debit(db, person, cents=200, now=LATER + timedelta(days=1))
    db.flush()

    welcome, reactivation = credit_entries(db, subject_id=person)

    assert welcome.consumed_cents == 200
    assert reactivation.consumed_cents == 0


def test_spending_spills_into_the_next_credit_once_the_first_is_gone(db):
    person = uuid.uuid4()
    _welcome(db, person)
    _reactivation(db, person)
    debit(db, person, cents=600, now=LATER + timedelta(days=1))
    db.flush()

    welcome, reactivation = credit_entries(db, subject_id=person)

    assert welcome.consumed_cents == 500
    assert reactivation.consumed_cents == 100


def test_each_entry_still_balances_when_spending_spans_two_credits(db):
    person = uuid.uuid4()
    _welcome(db, person)
    _reactivation(db, person)
    debit(db, person, cents=600, now=LATER + timedelta(days=1))
    db.flush()
    expire_credit(db, person, now=LATER + timedelta(days=40))
    db.flush()

    for entry in credit_entries(db, subject_id=person):
        assert entry.issued_cents == (
            entry.consumed_cents + entry.expired_cents + entry.abandoned_cents
        )


# ── What it actually cost ─────────────────────────────────────────────────────


def test_only_what_was_consumed_is_an_expense(db):
    """It alone bought provider time. A credit that expired untouched cost nothing, and
    booking it as spend would inflate acquisition with money that never left."""
    person = uuid.uuid4()
    _welcome(db, person)
    debit(db, person, cents=120, now=START)
    db.flush()
    expire_credit(db, person, now=START + timedelta(days=31))
    db.flush()

    assert acquisition_cost_cents(db) == 120


def test_a_wholly_unused_credit_costs_nothing(db):
    person = uuid.uuid4()
    _welcome(db, person)
    expire_credit(db, person, now=START + timedelta(days=31))
    db.flush()

    assert acquisition_cost_cents(db) == 0


def test_an_abandoned_credit_costs_nothing_either(db):
    person = uuid.uuid4()
    _welcome(db, person)
    append(
        db,
        type=EventType.ABANDONED,
        subject_id=person,
        amount_cents=-500,
        pool=Pool.GIFTED,
        occurred_at=START,
    )
    db.flush()

    assert acquisition_cost_cents(db) == 0


# ── Totals for a period, by type ──────────────────────────────────────────────


def test_the_three_states_are_reported_separately(db):
    """Never one number. Issued, consumed and expired answer different questions, and a
    single total would answer none of them."""
    person = uuid.uuid4()
    _welcome(db, person)
    debit(db, person, cents=200, now=START)
    db.flush()
    expire_credit(db, person, now=START + timedelta(days=31))
    db.flush()

    totals = period_totals(db, since=START, until=START + timedelta(days=40))

    assert totals[CreditType.WELCOME].issued_cents == 500
    assert totals[CreditType.WELCOME].consumed_cents == 200
    assert totals[CreditType.WELCOME].expired_cents == 300


def test_the_totals_are_broken_down_by_credit_type(db):
    """A welcome credit and a win-back are different campaigns with different economics."""
    person = uuid.uuid4()
    _welcome(db, person)
    _reactivation(db, person)

    totals = period_totals(db, since=START, until=LATER + timedelta(days=1))

    assert totals[CreditType.WELCOME].issued_cents == 500
    assert totals[CreditType.REACTIVATION].issued_cents == 300


def test_every_type_appears_even_when_none_were_issued(db):
    """A missing row reads as zero issued when it means the query found nothing — and those
    are different answers to somebody deciding whether a campaign ran."""
    totals = period_totals(db, since=START, until=LATER)

    assert set(totals) == set(CreditType)


def test_a_credit_issued_outside_the_period_is_not_counted(db):
    person = uuid.uuid4()
    _welcome(db, person)

    totals = period_totals(db, since=LATER, until=LATER + timedelta(days=10))

    assert totals[CreditType.WELCOME].issued_cents == 0


# ── Derived, never written alongside ──────────────────────────────────────────


def test_there_is_no_table_behind_any_of_this(db):
    """The last acceptance criterion, and the one that decided the shape of the rest. A
    second table would be a second record of the same fact, and Story 8.1 exists because two
    records drift."""
    import pathlib

    # The module docstring is stripped first: it explains the rule, and a guard that read
    # its own explanation would teach the next person to reword rather than to obey.
    text = (
        pathlib.Path(__file__).resolve().parents[1] / "src" / "credit_journal.py"
    ).read_text(encoding="utf-8")
    code = text.split('"""', 2)[-1]

    assert "__tablename__" not in code
    assert "db.add" not in code


def test_rebuilding_gives_the_same_answer(db):
    """It is a fold, so reading it twice cannot differ. That is the property a derived view
    has and a stored one has to be trusted about."""
    person = uuid.uuid4()
    _welcome(db, person)
    debit(db, person, cents=200, now=START)
    db.flush()

    assert credit_entries(db, subject_id=person) == credit_entries(db, subject_id=person)
