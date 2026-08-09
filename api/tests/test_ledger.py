"""One append-only stream of financial facts, and the views folded out of it (NFR7).

`billing_events` and `ad_broadcasts` already had the right instincts — append-only, prices
frozen at the moment of the fact, idempotent invoicing. What they were not is *one* stream.
Two logs of overlapping facts drift, and when they disagree there is nothing that says which
one is right.

So every fact is written once, here, and the grant audit (FR66), the gifted-credit entries
(FR67), the paid-balance journal (FR68) and the metrics (NFR4) are all folds over it. A view
that is derived cannot contradict the stream; a view that is written alongside it eventually
will, and by then nobody can tell which of the two to believe.

The other property worth stating: an event outlives the account it is about. Deleting a user
must not erase what was charged to them — that is evidence, and the person deleting the
account is often exactly the person with a reason to want it gone.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from src.ledger import (
    Actor,
    EventType,
    Pool,
    append,
    gifted_credits,
    grant_audit,
    ledger_metrics,
    paid_balance,
    rebuild,
)
from src.models.ledger_event import LedgerAppendOnly, LedgerEvent

PERSON = uuid.uuid4()
OTHER = uuid.uuid4()
START = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _at(minutes: int) -> datetime:
    return START + timedelta(minutes=minutes)


def _grant(db, *, subject=PERSON, cents=500, at=None, actor=Actor.SYSTEM, actor_id=None):
    return append(
        db,
        type=EventType.CREDIT_GRANTED,
        subject_id=subject,
        amount_cents=cents,
        pool=Pool.GIFTED,
        occurred_at=at or _at(0),
        actor=actor,
        actor_id=actor_id,
    )


# ── Written once, and carrying what it must ───────────────────────────────────


def test_an_event_carries_everything_the_story_asks_for(db):
    event = _grant(db)

    assert event.id is not None
    assert event.occurred_at is not None
    assert event.type == EventType.CREDIT_GRANTED.value
    assert event.subject_id == PERSON
    assert event.amount_cents == 500
    assert event.actor == Actor.SYSTEM.value


def test_an_operator_is_recorded_as_the_author(db):
    """"The system did it" and "a named person did it" are different facts, and the second
    is the one an audit exists to answer."""
    operator = uuid.uuid4()

    event = _grant(db, actor=Actor.OPERATOR, actor_id=operator)

    assert event.actor == Actor.OPERATOR.value
    assert event.actor_id == operator


def test_an_event_without_money_is_still_an_event(db):
    """Abandoning a Salon is operational rather than financial, and the stream is the record
    of both — splitting them would be the two-log mistake all over again."""
    event = append(
        db,
        type=EventType.ABANDONED,
        subject_id=PERSON,
        amount_cents=None,
        occurred_at=_at(5),
    )

    assert event.amount_cents is None


def test_every_kind_of_fact_can_be_written(db):
    for kind in EventType:
        append(db, type=kind, subject_id=PERSON, amount_cents=100, occurred_at=_at(1))
    db.flush()

    assert db.query(LedgerEvent).count() == len(list(EventType))


# ── Never modified, never deleted ─────────────────────────────────────────────


def test_an_event_cannot_be_changed(db):
    """A correction that rewrote history would make the stream unauditable: the record would
    say what somebody last decided rather than what happened."""
    event = _grant(db)
    db.flush()

    event.amount_cents = 999
    with pytest.raises(LedgerAppendOnly):
        db.flush()


def test_an_event_cannot_be_deleted(db):
    event = _grant(db)
    db.flush()

    db.delete(event)
    with pytest.raises(LedgerAppendOnly):
        db.flush()


def test_a_correction_is_a_new_event_pointing_at_the_old_one(db):
    """The only shape a correction may take. Both facts stay: what was recorded, and that it
    was wrong."""
    wrong = _grant(db, cents=5000)
    db.flush()

    fix = append(
        db,
        type=EventType.CORRECTED,
        subject_id=PERSON,
        amount_cents=-4500,
        pool=Pool.GIFTED,
        occurred_at=_at(10),
        actor=Actor.OPERATOR,
        actor_id=uuid.uuid4(),
        corrects_id=wrong.id,
    )

    db.flush()

    assert fix.corrects_id == wrong.id
    assert db.query(LedgerEvent).count() == 2


def test_the_compensating_event_is_what_moves_the_balance(db):
    _grant(db, cents=5000)
    append(
        db,
        type=EventType.CORRECTED,
        subject_id=PERSON,
        amount_cents=-4500,
        pool=Pool.GIFTED,
        occurred_at=_at(10),
    )
    db.flush()

    assert gifted_credits(db, PERSON).balance_cents == 500


# ── The views are folds, never parallel writes ────────────────────────────────


def test_the_grant_audit_is_derived(db):
    _grant(db, cents=500, at=_at(0))
    _grant(db, cents=250, at=_at(60))
    db.flush()

    audit = grant_audit(db, PERSON)

    assert [entry.amount_cents for entry in audit] == [500, 250]


def test_the_grant_audit_is_in_the_order_things_happened(db):
    _grant(db, cents=250, at=_at(60))
    _grant(db, cents=500, at=_at(0))
    db.flush()

    audit = grant_audit(db, PERSON)

    assert [entry.amount_cents for entry in audit] == [500, 250]


def test_gifted_and_paid_are_two_different_balances(db):
    """FR67 and FR68 are separate journals because the money is different: one was given and
    expires, the other was paid for and does not."""
    _grant(db, cents=500)
    append(
        db,
        type=EventType.RECHARGED,
        subject_id=PERSON,
        amount_cents=2000,
        pool=Pool.PAID,
        occurred_at=_at(30),
    )
    db.flush()

    assert gifted_credits(db, PERSON).balance_cents == 500
    assert paid_balance(db, PERSON).balance_cents == 2000


def test_a_debit_draws_from_the_pool_the_event_names(db):
    """Which pool a debit comes out of is a decision somebody made when it happened, so the
    event records it. A ledger that re-derived it would be re-deciding the past."""
    _grant(db, cents=500)
    append(
        db,
        type=EventType.DEBITED,
        subject_id=PERSON,
        amount_cents=-200,
        pool=Pool.GIFTED,
        occurred_at=_at(30),
    )
    db.flush()

    assert gifted_credits(db, PERSON).balance_cents == 300
    assert paid_balance(db, PERSON).balance_cents == 0


def test_expiry_takes_gifted_credit_away(db):
    _grant(db, cents=500)
    append(
        db,
        type=EventType.EXPIRED,
        subject_id=PERSON,
        amount_cents=-500,
        pool=Pool.GIFTED,
        occurred_at=_at(60),
    )
    db.flush()

    assert gifted_credits(db, PERSON).balance_cents == 0


def test_a_refund_puts_paid_money_back(db):
    append(
        db,
        type=EventType.RECHARGED,
        subject_id=PERSON,
        amount_cents=2000,
        pool=Pool.PAID,
        occurred_at=_at(0),
    )
    append(
        db,
        type=EventType.REFUNDED,
        subject_id=PERSON,
        amount_cents=-2000,
        pool=Pool.PAID,
        occurred_at=_at(30),
    )
    db.flush()

    assert paid_balance(db, PERSON).balance_cents == 0


def test_one_persons_events_never_reach_another(db):
    _grant(db, subject=PERSON, cents=500)
    _grant(db, subject=OTHER, cents=100)
    db.flush()

    assert gifted_credits(db, PERSON).balance_cents == 500
    assert gifted_credits(db, OTHER).balance_cents == 100


def test_the_metrics_are_derived_too(db):
    """NFR4 folded out of the same stream, so a metric can never disagree with a balance."""
    _grant(db, cents=500)
    append(
        db,
        type=EventType.RECHARGED,
        subject_id=PERSON,
        amount_cents=2000,
        pool=Pool.PAID,
        occurred_at=_at(30),
    )
    db.flush()

    metrics = ledger_metrics(db)

    assert metrics.granted_cents == 500
    assert metrics.recharged_cents == 2000
    assert metrics.events == 2


# ── Rebuilding is the property that makes it verifiable ───────────────────────


def test_a_view_rebuilt_from_the_stream_is_the_same_view(db):
    """The whole reason to derive rather than to write alongside. If a rebuild differed, the
    stream would not actually contain what the view claims to summarise."""
    _grant(db, cents=500)
    append(
        db,
        type=EventType.DEBITED,
        subject_id=PERSON,
        amount_cents=-120,
        pool=Pool.GIFTED,
        occurred_at=_at(30),
    )
    db.flush()
    before = rebuild(db, PERSON)

    after = rebuild(db, PERSON)

    assert before == after


def test_a_rebuild_matches_what_was_read_incrementally(db):
    _grant(db, cents=500)
    append(
        db,
        type=EventType.RECHARGED,
        subject_id=PERSON,
        amount_cents=2000,
        pool=Pool.PAID,
        occurred_at=_at(30),
    )
    db.flush()

    view = rebuild(db, PERSON)

    assert view.gifted.balance_cents == gifted_credits(db, PERSON).balance_cents
    assert view.paid.balance_cents == paid_balance(db, PERSON).balance_cents


def test_the_stream_settles_a_disagreement(db):
    """A view is a cache of an opinion the stream already holds. When they differ the view is
    thrown away, never the events — the alternative is choosing which record to believe, and
    nothing in the system is able to make that choice."""
    _grant(db, cents=500)
    db.flush()
    stale = rebuild(db, PERSON)

    append(
        db,
        type=EventType.DEBITED,
        subject_id=PERSON,
        amount_cents=-100,
        pool=Pool.GIFTED,
        occurred_at=_at(30),
    )
    db.flush()
    fresh = rebuild(db, PERSON)

    assert stale != fresh
    assert fresh.gifted.balance_cents == 400


def test_the_order_of_a_rebuild_never_depends_on_insertion_order(db):
    """Two events stamped at the same moment need a settled order, or a rebuild is not
    actually reproducible."""
    same = _at(15)
    first = append(
        db, type=EventType.DEBITED, subject_id=PERSON, amount_cents=-100,
        pool=Pool.GIFTED, occurred_at=same,
    )
    second = append(
        db, type=EventType.DEBITED, subject_id=PERSON, amount_cents=-50,
        pool=Pool.GIFTED, occurred_at=same,
    )
    db.flush()

    order = [entry.id for entry in grant_audit(db, PERSON, kinds=(EventType.DEBITED,))]
    assert order == sorted([first.id, second.id], key=str)


# ── The stream outlives the account ───────────────────────────────────────────


def test_deleting_a_person_erases_no_event(db):
    """The inherited `billing_events` cascaded on the user, so deleting an account destroyed
    the evidence of what had been charged to it. That is exactly backwards: the person
    deleting the account is often the one with a reason to want the record gone."""
    from src.models.user import User

    person = User(id=PERSON, email="somebody@example.com")
    db.add(person)
    db.flush()
    _grant(db, subject=PERSON, cents=500)
    db.flush()

    db.delete(person)
    db.flush()

    assert db.query(LedgerEvent).count() == 1
    assert gifted_credits(db, PERSON).balance_cents == 500


def test_the_subject_is_not_a_foreign_key(db):
    """Stated directly, because a helpful migration would otherwise add one back and the
    retention guarantee would quietly disappear."""
    assert LedgerEvent.__table__.c.subject_id.foreign_keys == set()


def test_an_event_can_be_written_for_a_subject_that_no_longer_exists(db):
    """A refund processed after an account closes is still a fact that has to be recorded."""
    event = _grant(db, subject=uuid.uuid4(), cents=100)
    db.flush()

    assert event.id is not None
