"""Asking whether somebody's whereabouts may be used to choose advertising (FR50).

The storage side was already careful: `salon_events.plus_code` holds a six-digit Open Location
Code cell — about five and a half kilometres — encoded at ingestion, so precise coordinates
never reach the disk, and there is deliberately no IP fallback. What was missing is the
*question*: a recorded decision, and the machinery to honour it.

Three states, not two. Never asked is not the same as refused. Somebody who has not yet seen
the screen has made no decision, and treating that silence as either answer would be putting
words in their mouth — one way by targeting them, the other by recording a refusal they never
gave.

Refusing costs nothing. They get untargeted advertising and the whole product otherwise —
a refusal that degraded the service would make the consent a purchase rather than a choice,
and a purchased consent is not consent.

And withdrawal is immediate. Not at the next Salon, not once a cache expires: a permission
that outlives its revocation by even a little was never really revocable.
"""
import uuid
from datetime import datetime, timedelta, timezone

from src.consent import (
    AdKind,
    ad_kind_for,
    location_cell_for,
    targeting_allowed,
    withdraw_location_consent,
    record_location_consent,
)

NOW = datetime(2026, 3, 1, tzinfo=timezone.utc)
LATER = NOW + timedelta(days=30)


def _person(db):
    from src.models.user import User

    person = User(id=uuid.uuid4(), email=f"{uuid.uuid4()}@example.com")
    db.add(person)
    db.flush()
    return person


# ── Three states, not two ─────────────────────────────────────────────────────


def test_somebody_who_has_not_been_asked_has_not_refused(db):
    """Silence is not an answer. Recording it as one puts words in their mouth."""
    person = _person(db)

    assert person.location_consent is None


def test_never_asked_is_not_treated_as_consent(db):
    """The other way of putting words in their mouth, and the more expensive one."""
    person = _person(db)

    assert targeting_allowed(person) is False


def test_consenting_is_recorded_with_when(db):
    person = _person(db)

    record_location_consent(person, granted=True, now=NOW)
    db.flush()

    assert person.location_consent is True
    assert person.location_consent_at == NOW


def test_refusing_is_recorded_too(db):
    """A refusal is a decision and is worth keeping: it is what stops the question being
    asked again next week."""
    person = _person(db)

    record_location_consent(person, granted=False, now=NOW)
    db.flush()

    assert person.location_consent is False
    assert person.location_consent_at == NOW


def test_a_refusal_is_distinguishable_from_never_having_been_asked(db):
    asked = _person(db)
    record_location_consent(asked, granted=False, now=NOW)
    unasked = _person(db)
    db.flush()

    assert asked.location_consent is False
    assert unasked.location_consent is None


# ── Refusing costs nothing ────────────────────────────────────────────────────


def test_a_refusal_gets_untargeted_advertising_rather_than_none(db):
    """They are still in a paid-for tier that includes advertising. What changes is the
    choosing, not the presence."""
    person = _person(db)
    record_location_consent(person, granted=False, now=NOW)

    assert ad_kind_for(person) is AdKind.GENERIC


def test_consent_gets_advertising_chosen_for_where_they_are(db):
    person = _person(db)
    record_location_consent(person, granted=True, now=NOW)

    assert ad_kind_for(person) is AdKind.TARGETED


def test_refusing_never_removes_anything_else(db):
    """A refusal that degraded the service would make consent a purchase, and a purchased
    consent is not consent. Nothing in the product asks this question except advertising."""
    import pathlib

    src = pathlib.Path(__file__).resolve().parents[1] / "src"
    users = [
        path.name
        for path in src.rglob("*.py")
        if "targeting_allowed" in path.read_text(encoding="utf-8")
    ]

    assert set(users) <= {"consent.py"}


def test_nobody_is_asked_twice_once_they_have_answered(db):
    from src.consent import should_ask

    person = _person(db)
    assert should_ask(person) is True

    record_location_consent(person, granted=False, now=NOW)

    assert should_ask(person) is False


# ── Withdrawal takes effect at once ───────────────────────────────────────────


def test_consent_can_be_withdrawn(db):
    person = _person(db)
    record_location_consent(person, granted=True, now=NOW)

    withdraw_location_consent(person, now=LATER)
    db.flush()

    assert person.location_consent is False


def test_withdrawal_stops_the_targeting_immediately(db):
    """Not at the next Salon and not once a cache expires. A permission that outlives its
    revocation by even a little was never really revocable."""
    person = _person(db)
    record_location_consent(person, granted=True, now=NOW)

    withdraw_location_consent(person, now=LATER)

    assert targeting_allowed(person) is False
    assert ad_kind_for(person) is AdKind.GENERIC


def test_withdrawal_records_when_it_happened(db):
    person = _person(db)
    record_location_consent(person, granted=True, now=NOW)

    withdraw_location_consent(person, now=LATER)
    db.flush()

    assert person.location_consent_at == LATER


def test_withdrawing_without_having_consented_is_harmless(db):
    person = _person(db)

    withdraw_location_consent(person, now=NOW)
    db.flush()

    assert person.location_consent is False


def test_somebody_can_change_their_mind_back(db):
    """Withdrawal is not a door that locks behind them."""
    person = _person(db)
    record_location_consent(person, granted=True, now=NOW)
    withdraw_location_consent(person, now=LATER)

    record_location_consent(person, granted=True, now=LATER + timedelta(days=1))

    assert targeting_allowed(person) is True


# ── Nothing is recorded without the answer ────────────────────────────────────


def test_a_cell_is_recorded_only_with_consent(db):
    """The five-and-a-half-kilometre cell from the inherited model. Without consent the
    field stays empty, which is what the existing schema already expects."""
    person = _person(db)
    record_location_consent(person, granted=True, now=NOW)

    assert location_cell_for(person, cell="87G8Q2") == "87G8Q2"


def test_no_cell_is_recorded_after_a_refusal(db):
    person = _person(db)
    record_location_consent(person, granted=False, now=NOW)

    assert location_cell_for(person, cell="87G8Q2") == ""


def test_no_cell_is_recorded_before_anybody_has_been_asked(db):
    person = _person(db)

    assert location_cell_for(person, cell="87G8Q2") == ""


def test_withdrawal_stops_new_cells_being_recorded(db):
    """The immediate effect that actually matters: after this, nothing more is written down
    about where they are."""
    person = _person(db)
    record_location_consent(person, granted=True, now=NOW)
    withdraw_location_consent(person, now=LATER)

    assert location_cell_for(person, cell="87G8Q2") == ""


def test_a_cell_is_never_narrowed_into_a_point(db):
    """Six digits is about five and a half kilometres. A longer code would be a point, and a
    point invites being treated as one — which is the reasoning the inherited model already
    wrote down."""
    person = _person(db)
    record_location_consent(person, granted=True, now=NOW)

    assert len(location_cell_for(person, cell="87G8Q2XV+2C")) <= 6


def test_the_consent_is_for_advertising_and_says_so(db):
    """Explicitly, on the screen. A permission granted for an unstated purpose is one
    somebody can reasonably say they did not understand."""
    from src.consent import CONSENT_QUESTION

    assert "advertis" in CONSENT_QUESTION.lower()
    assert "?" in CONSENT_QUESTION
