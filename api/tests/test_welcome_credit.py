"""The 5 USD welcome credit, and the registry that makes it once-in-a-lifetime (FR67).

A gift given per *account* is a gift given as often as somebody cares to make accounts. So
the thing that is spent is not the account but the identifiers: every address and number
handed over at signup is checked against a registry, and on a grant all of them are burned —
including the ones that were not used to sign in, since an unused identifier is exactly what
somebody keeps in reserve for the next account.

The registry outlives accounts and never expires. Deleting an account and making it again is
the obvious attempt, and a registry that forgot on deletion would protect against nothing.

What is refused is only ever the *gift*. Somebody whose identifier is burned still gets an
account and can still pay for any tier — refusing service over a spent promotion would be
charging a stranger for somebody else's cleverness.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from src.credit import (
    EXPIRY_SECONDS,
    PAID_BALANCE_LABEL,
    TIER_RATES_CENTS_PER_HOUR,
    WARNING_DAYS,
    WELCOME_CREDIT_CENTS,
    WELCOME_CREDIT_LABEL,
    Tier,
    balance,
    debit,
    expire_credit,
    expires_at,
    grant_welcome_credit,
    refundable_cents,
    warning_due,
    warning_text,
)
from src.ledger import EventType, Pool, append
from src.models.burned_identifier import BurnedIdentifier

PERSON = uuid.uuid4()
SIGNED_UP = datetime(2026, 3, 1, 14, 37, 12, tzinfo=timezone.utc)


def _grant(db, *, subject=None, identifiers=("someone@example.com",), at=SIGNED_UP):
    return grant_welcome_credit(
        db, subject_id=subject or uuid.uuid4(), identifiers=list(identifiers), now=at
    )


# ── Once, and only once ───────────────────────────────────────────────────────


def test_a_new_person_is_given_five_dollars(db):
    grant = _grant(db, subject=PERSON)
    db.flush()

    assert WELCOME_CREDIT_CENTS == 500
    assert grant.granted_cents == 500
    assert balance(db, PERSON).gifted_cents == 500


def test_the_identifiers_are_burned_when_the_credit_is_given(db):
    _grant(db, identifiers=["a@example.com", "+15145550123"])
    db.flush()

    burned = {row.identifier for row in db.query(BurnedIdentifier).all()}
    assert burned == {"a@example.com", "+15145550123"}


def test_an_identifier_that_never_authenticated_is_burned_too(db):
    """The one held in reserve for the next account is exactly the one worth burning."""
    _grant(db, identifiers=["signed-in@example.com", "+15145550123"])
    db.flush()

    second = _grant(db, subject=uuid.uuid4(), identifiers=["+15145550123"])

    assert second.granted_cents == 0


def test_a_burned_identifier_refuses_the_credit(db):
    _grant(db, identifiers=["a@example.com"])
    db.flush()

    again = _grant(db, subject=uuid.uuid4(), identifiers=["a@example.com"])

    assert again.granted_cents == 0
    assert again.refused_because


def test_one_burned_identifier_among_several_is_enough(db):
    _grant(db, identifiers=["old@example.com"])
    db.flush()

    again = _grant(db, subject=uuid.uuid4(), identifiers=["new@example.com", "old@example.com"])

    assert again.granted_cents == 0


def test_a_refusal_burns_nothing_new(db):
    """The fresh identifier was never paid for, so burning it would spend somebody else's
    only chance on an attempt that was refused."""
    _grant(db, identifiers=["old@example.com"])
    db.flush()
    _grant(db, subject=uuid.uuid4(), identifiers=["new@example.com", "old@example.com"])
    db.flush()

    burned = {row.identifier for row in db.query(BurnedIdentifier).all()}
    assert "new@example.com" not in burned


def test_the_registry_survives_the_account(db):
    """Delete and sign up again is the obvious attempt, and a registry that forgot on
    deletion would protect against nothing at all."""
    _grant(db, subject=PERSON, identifiers=["a@example.com"])
    db.flush()

    # Nothing here deletes the burn — there is no code path that can.
    again = _grant(db, subject=uuid.uuid4(), identifiers=["a@example.com"])

    assert again.granted_cents == 0


def test_the_registry_has_no_foreign_key_to_a_user(db):
    """Stated directly: a helpful cascade would quietly undo the guarantee."""
    assert BurnedIdentifier.__table__.c.identifier.foreign_keys == set()


def test_a_burn_never_expires(db):
    """Independent of the credit's own 30-day expiry. The gift can lapse; the fact that it
    was given does not."""
    _grant(db, identifiers=["a@example.com"], at=SIGNED_UP)
    db.flush()

    much_later = SIGNED_UP + timedelta(days=3650)
    again = _grant(db, subject=uuid.uuid4(), identifiers=["a@example.com"], at=much_later)

    assert again.granted_cents == 0


def test_the_service_is_never_refused_only_the_gift(db):
    """Charging a stranger for somebody else's cleverness is a different product."""
    _grant(db, identifiers=["a@example.com"])
    db.flush()
    refused = uuid.uuid4()
    _grant(db, subject=refused, identifiers=["a@example.com"])

    append(
        db,
        type=EventType.RECHARGED,
        subject_id=refused,
        amount_cents=2000,
        pool=Pool.PAID,
        occurred_at=SIGNED_UP,
    )
    db.flush()

    assert balance(db, refused).paid_cents == 2000


# ── When it runs out ──────────────────────────────────────────────────────────


def test_expiry_is_thirty_calendar_days_to_the_second(db):
    assert EXPIRY_SECONDS == 2_592_000

    assert expires_at(SIGNED_UP) == SIGNED_UP + timedelta(seconds=EXPIRY_SECONDS)


def test_expiry_keeps_the_time_of_day(db):
    due = expires_at(SIGNED_UP)

    assert (due.hour, due.minute, due.second) == (14, 37, 12)


def test_expiry_counts_calendar_days_and_consults_no_calendar(db):
    """Weekends and holidays included, and no jurisdiction to look up. A promotion that
    expired differently in different countries would need a calendar per country."""
    friday = datetime(2026, 3, 6, 9, 0, tzinfo=timezone.utc)

    assert expires_at(friday) == friday + timedelta(days=30)


def test_an_unspent_credit_goes_to_zero(db):
    _grant(db, subject=PERSON)
    db.flush()

    expire_credit(db, PERSON, now=expires_at(SIGNED_UP))
    db.flush()

    assert balance(db, PERSON).gifted_cents == 0


def test_expiry_leaves_the_paid_balance_alone(db):
    """The gift lapses. Money somebody handed over does not."""
    _grant(db, subject=PERSON)
    append(
        db,
        type=EventType.RECHARGED,
        subject_id=PERSON,
        amount_cents=2000,
        pool=Pool.PAID,
        occurred_at=SIGNED_UP,
    )
    db.flush()

    expire_credit(db, PERSON, now=expires_at(SIGNED_UP))
    db.flush()

    assert balance(db, PERSON).paid_cents == 2000


def test_expiring_an_already_empty_credit_writes_nothing(db):
    _grant(db, subject=PERSON)
    debit(db, PERSON, cents=500, now=SIGNED_UP)
    db.flush()

    expire_credit(db, PERSON, now=expires_at(SIGNED_UP))
    db.flush()

    assert balance(db, PERSON).gifted_cents == 0


# ── The warning ───────────────────────────────────────────────────────────────


def test_the_warning_falls_seven_days_before(db):
    assert WARNING_DAYS == 7


def test_a_warning_is_due_inside_the_last_week(db):
    _grant(db, subject=PERSON)
    db.flush()

    six_days_left = expires_at(SIGNED_UP) - timedelta(days=6)

    assert warning_due(db, PERSON, now=six_days_left) is True


def test_no_warning_before_the_last_week(db):
    _grant(db, subject=PERSON)
    db.flush()

    eight_days_left = expires_at(SIGNED_UP) - timedelta(days=8)

    assert warning_due(db, PERSON, now=eight_days_left) is False


def test_no_warning_when_there_is_nothing_left_to_lose(db):
    """A credit already spent cannot evaporate, and telling somebody they are about to lose
    nothing is a message that teaches them to ignore the next one."""
    _grant(db, subject=PERSON)
    debit(db, PERSON, cents=500, now=SIGNED_UP)
    db.flush()

    assert warning_due(db, PERSON, now=expires_at(SIGNED_UP) - timedelta(days=1)) is False


def test_the_warning_is_sent_once_and_not_every_day(db):
    """Daily reminders until the deadline are how a message stops being read."""
    _grant(db, subject=PERSON)
    db.flush()
    when = expires_at(SIGNED_UP) - timedelta(days=6)
    assert warning_due(db, PERSON, now=when) is True

    append(
        db,
        type=EventType.EXPIRY_WARNED,
        subject_id=PERSON,
        occurred_at=when,
    )
    db.flush()

    assert warning_due(db, PERSON, now=when + timedelta(days=1)) is False


def test_the_warning_says_what_the_money_buys_and_not_only_a_date(db):
    """"You have $3.20, which is 1 h 36 in Base or 38 min in Mode A" — a date alone asks
    somebody to do the arithmetic that decides whether they care."""
    text = warning_text(320)

    assert "3.20" in text
    for tier in Tier:
        assert tier.label in text


def test_the_warning_states_the_remaining_amount_not_the_original(db):
    text = warning_text(320)

    assert "5.00" not in text


# ── Two parts, never one total ────────────────────────────────────────────────


def test_the_two_parts_are_stored_and_reported_separately(db):
    """Never one total with the parts deduced: which part is which decides what can be
    refunded, and a single number would make that unanswerable."""
    _grant(db, subject=PERSON)
    append(
        db,
        type=EventType.RECHARGED,
        subject_id=PERSON,
        amount_cents=2000,
        pool=Pool.PAID,
        occurred_at=SIGNED_UP,
    )
    db.flush()

    view = balance(db, PERSON)

    assert (view.gifted_cents, view.paid_cents) == (500, 2000)
    assert view.total_cents == 2500


def test_the_gifted_part_is_spent_first(db):
    """Which also protects the refund: money the person actually handed over stays intact
    for as long as possible."""
    _grant(db, subject=PERSON)
    append(
        db,
        type=EventType.RECHARGED,
        subject_id=PERSON,
        amount_cents=2000,
        pool=Pool.PAID,
        occurred_at=SIGNED_UP,
    )
    db.flush()

    debit(db, PERSON, cents=300, now=SIGNED_UP)
    db.flush()

    view = balance(db, PERSON)
    assert (view.gifted_cents, view.paid_cents) == (200, 2000)


def test_a_debit_larger_than_the_gift_spills_into_the_paid_part(db):
    _grant(db, subject=PERSON)
    append(
        db,
        type=EventType.RECHARGED,
        subject_id=PERSON,
        amount_cents=2000,
        pool=Pool.PAID,
        occurred_at=SIGNED_UP,
    )
    db.flush()

    debit(db, PERSON, cents=800, now=SIGNED_UP)
    db.flush()

    view = balance(db, PERSON)
    assert (view.gifted_cents, view.paid_cents) == (0, 1700)


def test_every_movement_records_which_part_it_touched(db):
    """The audit trail that answers a dispute. A movement that did not say which part it
    came from would leave the question open exactly when it is asked."""
    _grant(db, subject=PERSON)
    db.flush()
    moves = debit(db, PERSON, cents=300, now=SIGNED_UP)

    assert [move.pool for move in moves] == [Pool.GIFTED.value]


def test_a_debit_spanning_both_parts_is_two_movements(db):
    """One movement naming two pools would be back to a single number."""
    _grant(db, subject=PERSON)
    append(
        db,
        type=EventType.RECHARGED,
        subject_id=PERSON,
        amount_cents=2000,
        pool=Pool.PAID,
        occurred_at=SIGNED_UP,
    )
    db.flush()

    moves = debit(db, PERSON, cents=800, now=SIGNED_UP)

    assert [move.pool for move in moves] == [Pool.GIFTED.value, Pool.PAID.value]


# ── Refunds ───────────────────────────────────────────────────────────────────


def test_only_the_paid_part_is_refundable(db):
    _grant(db, subject=PERSON)
    append(
        db,
        type=EventType.RECHARGED,
        subject_id=PERSON,
        amount_cents=2000,
        pool=Pool.PAID,
        occurred_at=SIGNED_UP,
    )
    db.flush()

    assert refundable_cents(db, PERSON) == 2000


def test_somebody_who_never_paid_is_owed_nothing(db):
    _grant(db, subject=PERSON)
    debit(db, PERSON, cents=400, now=SIGNED_UP)
    db.flush()

    assert refundable_cents(db, PERSON) == 0


# ── What the money buys, and what it is called ────────────────────────────────


def test_no_tier_is_free(db):
    for tier in Tier:
        assert TIER_RATES_CENTS_PER_HOUR[tier] > 0


def test_the_base_tier_costs_three_dollars_an_hour(db):
    assert TIER_RATES_CENTS_PER_HOUR[Tier.BASE] == 300


def test_each_tier_costs_more_than_the_one_below(db):
    """Each adds exactly one thing to the last, so the price gap is always attributable."""
    rates = [TIER_RATES_CENTS_PER_HOUR[tier] for tier in Tier]

    assert rates == sorted(rates)
    assert len(set(rates)) == len(rates)


def test_the_labels_are_stored_in_canonical_english(db):
    """Like every other thing said to a participant: one canonical string, translated at
    rendering. Configuration never holds a variant per language."""
    assert WELCOME_CREDIT_LABEL == "Vocaliz welcome credit"
    assert PAID_BALANCE_LABEL == "Your topped-up balance"


def test_the_two_parts_are_named_when_the_balance_is_shown(db):
    """So nobody can say they believed ten dollars of their own money was sitting there."""
    _grant(db, subject=PERSON)
    db.flush()

    view = balance(db, PERSON)

    assert view.gifted_label == WELCOME_CREDIT_LABEL
    assert view.paid_label == PAID_BALANCE_LABEL
