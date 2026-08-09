"""Whether a cohort recharges before its credit expires, and how long it takes them to.

Two numbers, and both are easy to publish in a way that misleads.

The conversion rate is a proportion of a *cohort*, and it only means anything once that
cohort's 30-day window has closed. A cohort three days old has had three days to convert and
will look catastrophic beside one that had a month. So a partial cohort is marked as partial
and refuses to be compared — the comparison raises rather than warning, because a caveat
printed next to a number is read by nobody and the number is what gets quoted.

The delay is a distribution and never a mean. One person who came back on day 29 drags an
average past the point of usefulness, while the median and the quartiles say what actually
happened to people.

A declined card is a bank's decision and not a person's, so failures are counted separately
and the delay runs to the first *success*. Folding them together would read a payment
problem as a lack of interest, which is the kind of mistake that gets acted on.
"""
from __future__ import annotations

from math import ceil

from dataclasses import dataclass
from datetime import datetime, timedelta

# How long a new signup's credit lasts. The window the conversion rate is measured over.
EXPIRY_DAYS = 30


@dataclass(frozen=True)
class Signup:
    """One person, and what they did about paying."""

    person_id: str
    signed_up_at: datetime
    # `None` means they never recharged successfully. They are counted against the rate and
    # left out of the delay: they have no delay, and inventing one either way is worse.
    first_successful_recharge_at: datetime | None = None
    failed_attempts: int = 0

    @property
    def minutes_to_first_success(self) -> float | None:
        if self.first_successful_recharge_at is None:
            return None
        return (self.first_successful_recharge_at - self.signed_up_at).total_seconds() / 60.0

    def converted_before_expiry(self) -> bool:
        """Recharged while the credit was still alive.

        Somebody who came back in week six is a different and happier story, and folding
        them in would hide the fact that the credit ran out first.
        """
        minutes = self.minutes_to_first_success
        return minutes is not None and minutes <= EXPIRY_DAYS * 24 * 60


@dataclass(frozen=True)
class Cohort:
    """Everybody who signed up in one period, and the moment it is being looked at."""

    name: str
    signups: list[Signup]
    as_of: datetime

    def closed(self) -> bool:
        """Whether every member has had the full window to convert."""
        if not self.signups:
            return True
        latest = max(signup.signed_up_at for signup in self.signups)
        return self.as_of >= latest + timedelta(days=EXPIRY_DAYS)


@dataclass(frozen=True)
class Conversion:
    """What share of a cohort paid before their credit expired."""

    cohort: str
    # `None` for an empty cohort: nought converted of nobody is not a zero per cent rate.
    rate: float | None
    converted: int
    total: int
    failed_attempts: int
    partial: bool

    def compare(self, other: Conversion) -> float:
        """The difference between two rates, refusing to compute it across a partial one.

        Raising rather than warning. A cohort still inside its window has not had the time
        the other one had, and the comparison is not slightly misleading — it is wrong.
        """
        for side in (self, other):
            if side.partial:
                raise ValueError(
                    f"cohort {side.name_of()} is partial: its 30-day window has not closed, "
                    "so it has not had the time the other cohort had. Wait for it to close "
                    "rather than comparing a weekend with a month."
                )
        if self.rate is None or other.rate is None:
            raise ValueError("a cohort with no members has no rate to compare.")
        return other.rate - self.rate

    def name_of(self) -> str:
        return self.cohort


@dataclass(frozen=True)
class Delay:
    """How long people took to pay, as a shape rather than as one number."""

    count: int
    median: float | None
    p25: float | None
    p75: float | None
    p90: float | None


def _percentile(ordered: list[float], fraction: float) -> float:
    """Nearest-rank, which assumes nothing about the distribution's shape."""
    rank = max(1, min(len(ordered), ceil(fraction * len(ordered))))
    return ordered[rank - 1]


def conversion(cohort: Cohort) -> Conversion:
    """The share of a cohort that recharged before expiry, and whether it can be trusted."""
    total = len(cohort.signups)
    converted = sum(1 for signup in cohort.signups if signup.converted_before_expiry())
    return Conversion(
        cohort=cohort.name,
        rate=(converted / total) if total else None,
        converted=converted,
        total=total,
        failed_attempts=sum(signup.failed_attempts for signup in cohort.signups),
        partial=not cohort.closed(),
    )


def delay_distribution(signups: list[Signup]) -> Delay:
    """How long the people who paid took to do it, in minutes.

    Only the people who paid. Somebody who never recharged has no delay — counting them as
    a large one invents a number, and counting them as zero invents a better one.
    """
    minutes = sorted(
        signup.minutes_to_first_success
        for signup in signups
        if signup.minutes_to_first_success is not None
    )
    if not minutes:
        return Delay(count=0, median=None, p25=None, p75=None, p90=None)

    return Delay(
        count=len(minutes),
        median=_percentile(minutes, 0.5),
        p25=_percentile(minutes, 0.25),
        p75=_percentile(minutes, 0.75),
        p90=_percentile(minutes, 0.9),
    )
