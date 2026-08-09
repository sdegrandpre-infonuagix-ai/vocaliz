"""Granting somebody a second credit by hand, from a command line and nowhere else (FR67).

The burned-identifier registry from Story 8.2 exists to stop somebody collecting the welcome
credit over and over. It also, unavoidably, stops Vocaliz running its own reactivation
campaign — which is a cost of the design rather than a flaw in it. This is the explicit
exception, and the word matters: the registry is never expired, never cleared, never
weakened. One grant is allowed *through* it, and the registry is exactly as it was afterwards.

Two things keep the exception from becoming a back door. Ninety days must have passed since
the last gift, so nobody can be given the credit repeatedly by asking nicely. And every grant
is journalled with its author, its reason and its amount — issuing money without a trace is
the one thing an audit never forgives.

It is a command line and nothing else. No screen, no route, no admin accounts table: access
to the production environment *is* the access control, which means there is no administrator
authentication to build and therefore none to get wrong.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from src.credit import WELCOME_CREDIT_LABEL, balance, grant_welcome_credit
from src.ledger import Actor, EventType, Pool
from src.models.burned_identifier import BurnedIdentifier
from src.models.ledger_event import LedgerEvent
from src.reactivation import (
    MIN_DAYS_BETWEEN_GIFTS,
    REACTIVATION_CREDIT_CENTS,
    confirmation_text,
    grant_second_credit,
    grant_to_cohort,
)

OPERATOR = uuid.uuid4()
FIRST_GRANT = datetime(2026, 1, 1, tzinfo=timezone.utc)
LONG_AFTER = FIRST_GRANT + timedelta(days=120)


def _person(db, *, address=None, at=FIRST_GRANT):
    person = uuid.uuid4()
    grant_welcome_credit(
        db,
        subject_id=person,
        identifiers=[address or f"{uuid.uuid4()}@example.com"],
        now=at,
    )
    db.flush()
    return person


def _grant(db, person, *, at=LONG_AFTER, cents=None, reason="win-back"):
    return grant_second_credit(
        db,
        subject_id=person,
        amount_cents=cents,
        reason=reason,
        operator_id=OPERATOR,
        now=at,
    )


# ── Through the registry, never around it ─────────────────────────────────────


def test_a_burned_identifier_does_not_block_a_manual_grant(db):
    """The explicit exception. Somebody who tried Vocaliz and drifted away is exactly who a
    reactivation campaign is for."""
    person = _person(db, address="drifted@example.com")

    grant = _grant(db, person)
    db.flush()

    assert grant.granted_cents == REACTIVATION_CREDIT_CENTS


def test_the_registry_is_untouched_by_the_exception(db):
    """Never expired, never cleared, never weakened. One grant passes through it and it is
    exactly as it was afterwards — otherwise the exception would be a deletion."""
    person = _person(db, address="drifted@example.com")
    before = db.query(BurnedIdentifier).count()

    _grant(db, person)
    db.flush()

    assert db.query(BurnedIdentifier).count() == before
    assert db.query(BurnedIdentifier).filter(
        BurnedIdentifier.identifier == "drifted@example.com"
    ).one_or_none() is not None


def test_the_welcome_credit_is_still_refused_afterwards(db):
    """The exception was one grant, not a reopening. Somebody signing up again with the same
    address still gets nothing automatically."""
    person = _person(db, address="drifted@example.com")
    _grant(db, person)
    db.flush()

    again = grant_welcome_credit(
        db, subject_id=uuid.uuid4(), identifiers=["drifted@example.com"], now=LONG_AFTER
    )

    assert again.granted_cents == 0


# ── Ninety days, so it is not a back door ─────────────────────────────────────


def test_the_minimum_delay_is_ninety_days(db):
    assert MIN_DAYS_BETWEEN_GIFTS == 90


def test_a_second_credit_too_soon_is_refused(db):
    person = _person(db)

    grant = _grant(db, person, at=FIRST_GRANT + timedelta(days=30))

    assert grant.granted_cents == 0
    assert grant.refused_because


def test_the_refusal_says_how_long_is_left(db):
    """An operator told only "refused" will try again tomorrow, and the day after."""
    person = _person(db)

    grant = _grant(db, person, at=FIRST_GRANT + timedelta(days=30))

    assert "90" in grant.refused_because


def test_exactly_ninety_days_is_long_enough(db):
    person = _person(db)

    grant = _grant(db, person, at=FIRST_GRANT + timedelta(days=MIN_DAYS_BETWEEN_GIFTS))

    assert grant.granted_cents > 0


def test_a_day_short_is_not(db):
    person = _person(db)

    grant = _grant(db, person, at=FIRST_GRANT + timedelta(days=MIN_DAYS_BETWEEN_GIFTS - 1))

    assert grant.granted_cents == 0


def test_somebody_who_never_had_a_credit_can_be_granted_one_immediately(db):
    """No previous gift means no delay to wait out."""
    grant = _grant(db, uuid.uuid4(), at=FIRST_GRANT)

    assert grant.granted_cents > 0


# ── The amount ────────────────────────────────────────────────────────────────


def test_the_default_is_three_dollars(db):
    assert REACTIVATION_CREDIT_CENTS == 300


def test_a_named_amount_wins_over_the_default(db):
    """Bringing somebody back and getting them to try in the first place are not worth the
    same, so the operator decides."""
    person = _person(db)

    grant = _grant(db, person, cents=1000)

    assert grant.granted_cents == 1000


def test_an_amount_above_the_ceiling_is_refused(db):
    from src.coverage import TOP_UP_CEILING_CENTS

    person = _person(db)

    with pytest.raises(ValueError):
        _grant(db, person, cents=TOP_UP_CEILING_CENTS + 1)


def test_an_amount_of_nothing_is_refused_rather_than_written(db):
    """A grant of zero is a journal entry that says money moved when it did not."""
    person = _person(db)

    with pytest.raises(ValueError):
        _grant(db, person, cents=0)


# ── It behaves like any other gifted credit ───────────────────────────────────


def test_it_lands_in_the_gifted_balance(db):
    """Added to whatever gifted credit is already there — this person still holds their
    original welcome credit, so the claim is the increase rather than the total."""
    person = _person(db)
    before = balance(db, person).gifted_cents

    _grant(db, person)
    db.flush()

    assert balance(db, person).gifted_cents == before + REACTIVATION_CREDIT_CENTS


def test_it_is_not_refundable_because_no_money_was_paid_in(db):
    from src.credit import refundable_cents

    person = _person(db)
    _grant(db, person)
    db.flush()

    assert refundable_cents(db, person) == 0


def test_it_expires_like_the_welcome_credit(db):
    from src.credit import expires_at

    person = _person(db)

    grant = _grant(db, person)

    assert grant.expires_at == expires_at(LONG_AFTER)


# ── Every grant leaves a trace ────────────────────────────────────────────────


def test_the_operator_is_recorded_rather_than_the_system(db):
    """"A named person did it" is exactly the fact an audit of issued money exists to
    answer."""
    person = _person(db)
    _grant(db, person)
    db.flush()

    row = (
        db.query(LedgerEvent)
        .filter(LedgerEvent.subject_id == person, LedgerEvent.actor == Actor.OPERATOR.value)
        .one()
    )

    assert row.actor_id == OPERATOR
    assert row.type == EventType.CREDIT_GRANTED.value
    assert row.pool == Pool.GIFTED.value


def test_the_reason_is_recorded(db):
    person = _person(db)
    _grant(db, person, reason="february win-back")
    db.flush()

    row = (
        db.query(LedgerEvent)
        .filter(LedgerEvent.subject_id == person, LedgerEvent.actor == Actor.OPERATOR.value)
        .one()
    )

    assert "february win-back" in row.detail


def test_a_grant_without_a_reason_is_refused(db):
    """Issuing money with no stated purpose is the entry an audit stops at."""
    person = _person(db)

    with pytest.raises(ValueError):
        _grant(db, person, reason="")


def test_a_manual_grant_is_distinguishable_from_a_welcome_one(db):
    person = _person(db)
    _grant(db, person)
    db.flush()

    grants = db.query(LedgerEvent).filter(
        LedgerEvent.subject_id == person, LedgerEvent.type == EventType.CREDIT_GRANTED.value
    ).all()

    assert len(grants) == 2
    assert {row.actor for row in grants} == {Actor.SYSTEM.value, Actor.OPERATOR.value}
    assert any(row.detail == WELCOME_CREDIT_LABEL for row in grants)


# ── A cohort in one operation ─────────────────────────────────────────────────


def test_a_campaign_can_grant_to_several_people_at_once(db):
    people = [_person(db) for _ in range(3)]

    grants = grant_to_cohort(
        db, subject_ids=people, reason="win-back", operator_id=OPERATOR, now=LONG_AFTER
    )
    db.flush()

    assert len(grants) == 3


def test_each_beneficiary_gets_their_own_journal_entry(db):
    """One operation, but never one aggregated entry. A cohort row would make a single
    person's grant unanswerable."""
    people = [_person(db) for _ in range(3)]

    grant_to_cohort(
        db, subject_ids=people, reason="win-back", operator_id=OPERATOR, now=LONG_AFTER
    )
    db.flush()

    for person in people:
        assert (
            db.query(LedgerEvent)
            .filter(
                LedgerEvent.subject_id == person,
                LedgerEvent.actor == Actor.OPERATOR.value,
            )
            .count()
            == 1
        )


def test_one_refusal_in_a_cohort_does_not_stop_the_others(db):
    """A campaign of two hundred should not fail because one person was granted a credit
    last month."""
    too_soon = _person(db, at=LONG_AFTER - timedelta(days=10))
    eligible = _person(db)

    grants = grant_to_cohort(
        db,
        subject_ids=[too_soon, eligible],
        reason="win-back",
        operator_id=OPERATOR,
        now=LONG_AFTER,
    )
    db.flush()

    assert [grant.granted_cents for grant in grants] == [0, REACTIVATION_CREDIT_CENTS]


# ── Confirmed before anything is written ──────────────────────────────────────


def test_the_confirmation_states_the_total_and_the_head_count():
    """Before writing anything. An operator about to issue money should see how much and to
    how many, not discover it from the ledger afterwards."""
    text = confirmation_text(beneficiaries=200, amount_cents=300)

    assert "200" in text
    assert "600.00" in text


def test_the_confirmation_uses_the_named_amount():
    text = confirmation_text(beneficiaries=10, amount_cents=1000)

    assert "100.00" in text


# ── A command line, and no other way in ───────────────────────────────────────


def test_the_grant_is_reachable_from_no_route_at_all():
    """No screen, no endpoint, no admin accounts table. Access to production *is* the access
    control, which means there is no administrator authentication to build and none to get
    wrong."""
    import pathlib

    routers = pathlib.Path(__file__).resolve().parents[1] / "src" / "routers"
    for module in routers.glob("*.py"):
        source = module.read_text(encoding="utf-8")
        assert "reactivation" not in source, f"{module.name} exposes the manual grant"


def test_there_is_a_command_line_entry_point():
    from src.cli import grant_credit

    assert hasattr(grant_credit, "main")
