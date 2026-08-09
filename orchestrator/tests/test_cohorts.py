"""Whether a cohort converts before its credit expires, and how long it takes them to.

Two numbers, and both are easy to publish in a way that misleads.

The conversion rate is a proportion of a *cohort*, which only means anything once that
cohort's 30-day window has closed. A cohort three days old has had three days to convert and
will look catastrophic next to one that had a month. Reporting it without saying so would
make every recent cohort an emergency, and the fix people reach for is to stop looking.

The delay is a distribution and never a mean. One person who converted after 29 days pulls
an average past the point of usefulness, while the median, p25, p75 and p90 say what
actually happened to people.
"""
from datetime import datetime, timedelta, timezone

import pytest

from src.cohorts import (
    EXPIRY_DAYS,
    Cohort,
    Delay,
    Signup,
    conversion,
    delay_distribution,
)

START = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _at(minutes: float) -> datetime:
    return START + timedelta(minutes=minutes)


def _signup(name: str, *, first_success: float | None = None, failures: int = 0) -> Signup:
    return Signup(
        person_id=name,
        signed_up_at=START,
        first_successful_recharge_at=None if first_success is None else _at(first_success),
        failed_attempts=failures,
    )


# ── The window ────────────────────────────────────────────────────────────────


def test_the_window_is_thirty_days():
    assert EXPIRY_DAYS == 30


def test_a_closed_cohort_reports_its_rate():
    cohort = Cohort(
        name="january",
        signups=[_signup("a", first_success=100.0), _signup("b")],
        as_of=START + timedelta(days=31),
    )

    result = conversion(cohort)

    assert result.rate == pytest.approx(0.5)
    assert result.partial is False


def test_a_cohort_whose_window_is_still_open_is_flagged():
    """Three days in, it has had three days to convert. Comparing it to a closed cohort is
    comparing a month of opportunity with a weekend."""
    cohort = Cohort(
        name="march",
        signups=[_signup("a", first_success=100.0), _signup("b")],
        as_of=START + timedelta(days=3),
    )

    assert conversion(cohort).partial is True


def test_the_window_closes_exactly_at_thirty_days():
    cohort = Cohort(name="c", signups=[_signup("a")], as_of=START + timedelta(days=EXPIRY_DAYS))

    assert conversion(cohort).partial is False


def test_a_day_short_is_still_partial():
    cohort = Cohort(
        name="c", signups=[_signup("a")], as_of=START + timedelta(days=EXPIRY_DAYS - 1)
    )

    assert conversion(cohort).partial is True


def test_a_partial_cohort_refuses_to_be_compared_to_a_closed_one():
    """Not a warning in a footnote — the comparison itself raises. A caveat printed next to
    a number is read by nobody, and the number is what gets quoted."""
    closed = conversion(
        Cohort(name="a", signups=[_signup("a", first_success=1.0)], as_of=_at(60 * 24 * 40))
    )
    open_yet = conversion(
        Cohort(name="b", signups=[_signup("b", first_success=1.0)], as_of=_at(60 * 24 * 3))
    )

    with pytest.raises(ValueError) as raised:
        closed.compare(open_yet)

    assert "partial" in str(raised.value).lower()


def test_two_closed_cohorts_compare_fine():
    first = conversion(
        Cohort(name="a", signups=[_signup("a", first_success=1.0)], as_of=_at(60 * 24 * 40))
    )
    second = conversion(
        Cohort(
            name="b",
            signups=[_signup("b", first_success=1.0), _signup("c")],
            as_of=_at(60 * 24 * 40),
        )
    )

    # `a.compare(b)` reads as the change from a to b, so a drop is negative.
    assert first.compare(second) == pytest.approx(-0.5)


# ── Who counts, and where ─────────────────────────────────────────────────────


def test_somebody_who_never_recharged_counts_against_the_rate():
    cohort = Cohort(
        name="c",
        signups=[_signup("a", first_success=10.0), _signup("b"), _signup("c")],
        as_of=_at(60 * 24 * 40),
    )

    assert conversion(cohort).rate == pytest.approx(1 / 3)


def test_but_is_left_out_of_the_delay():
    """They have no delay. Counting them as a large one would invent a number, and counting
    them as zero would invent a better one."""
    distribution = delay_distribution(
        [_signup("a", first_success=10.0), _signup("b"), _signup("c")]
    )

    assert distribution.count == 1


def test_a_recharge_after_the_window_is_not_a_conversion():
    """The rate is conversion *before expiry*. Somebody who came back in week six is a
    different and happier story, and folding them in would hide that the credit ran out."""
    cohort = Cohort(
        name="c",
        signups=[_signup("a", first_success=60 * 24 * 45)],
        as_of=_at(60 * 24 * 60),
    )

    assert conversion(cohort).rate == 0.0


def test_an_empty_cohort_has_no_rate_rather_than_zero():
    """Zero converted of zero people is not a zero per cent conversion rate."""
    assert conversion(Cohort(name="c", signups=[], as_of=_at(60 * 24 * 40))).rate is None


# ── The delay, as a distribution ──────────────────────────────────────────────


def test_the_delay_is_measured_in_minutes_from_signing_up():
    distribution = delay_distribution([_signup("a", first_success=90.0)])

    assert distribution.median == 90.0


def test_it_is_published_as_a_distribution_and_not_a_mean():
    """One person converting after 29 days drags an average past usefulness. The quartiles
    say what happened to people."""
    signups = [_signup(f"p{i}", first_success=float(i)) for i in range(1, 101)]

    distribution = delay_distribution(signups)

    assert distribution.median == 50.0
    assert distribution.p25 == 25.0
    assert distribution.p75 == 75.0
    assert distribution.p90 == 90.0


def test_the_shape_it_publishes_is_the_one_that_was_asked_for():
    assert set(Delay.__dataclass_fields__) >= {"median", "p25", "p75", "p90", "count"}


def test_a_distribution_of_nobody_is_empty_rather_than_zero():
    distribution = delay_distribution([])

    assert distribution.count == 0
    assert distribution.median is None


# ── A refused card is not a refusal to buy ────────────────────────────────────


def test_the_delay_runs_to_the_first_success_not_the_first_attempt():
    signup = _signup("a", first_success=200.0, failures=3)

    assert delay_distribution([signup]).median == 200.0


def test_failed_attempts_are_counted_separately():
    """A declined card is a bank's decision, not a person's. Folding failures into the
    conversion rate would read a payment problem as a lack of interest."""
    cohort = Cohort(
        name="c",
        signups=[_signup("a", first_success=200.0, failures=3), _signup("b", failures=2)],
        as_of=_at(60 * 24 * 40),
    )

    result = conversion(cohort)

    assert result.failed_attempts == 5
    assert result.rate == pytest.approx(0.5)


def test_somebody_who_only_ever_failed_did_not_convert():
    cohort = Cohort(name="c", signups=[_signup("a", failures=4)], as_of=_at(60 * 24 * 40))

    assert conversion(cohort).rate == 0.0
    assert conversion(cohort).failed_attempts == 4


def test_an_empty_cohort_cannot_be_compared_either():
    """It has no rate, and treating a missing rate as zero would report a cohort nobody
    joined as the worst-performing one there has ever been."""
    empty = conversion(Cohort(name="empty", signups=[], as_of=_at(60 * 24 * 40)))
    real = conversion(
        Cohort(name="real", signups=[_signup("a", first_success=1.0)], as_of=_at(60 * 24 * 40))
    )

    with pytest.raises(ValueError) as raised:
        real.compare(empty)

    assert "no members" in str(raised.value)
