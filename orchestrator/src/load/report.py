"""The verdict on a load run, against the criteria for going from 3 participants to 50.

Four criteria, and the report fails closed on every one of them. A run that did not measure
something has not met it — "no cost figures were supplied" is not the same as "the cost
criterion was met", and a report that conflated the two would sign off a ceiling raise on
three criteria out of four without anybody noticing which one was missing.

The same reasoning applies to the hour. Zero blocks in ten minutes says nothing about an
hour, so a short run is reported as unable to prove the criterion rather than as passing it.
Scaling the requirement to the run length would turn a short run into a free pass.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from src.load.metrics import SalonMetrics, Tier

# The numbers the decision was stated with.
PASS_LATENCY_SECONDS = 10.0
PASS_CONDENSED_RATIO = 0.2
PASS_BLOCK_WINDOW_SECONDS = 3600.0
# The cost of serving a participant must sit below this share of what their mode is sold for.
PASS_COST_SHARE = 0.5


@dataclass(frozen=True)
class TierPrice:
    """What serving one participant costs, against what their mode is sold for."""

    cost_per_participant: float
    price_per_participant: float

    @property
    def share(self) -> float:
        if self.price_per_participant <= 0:
            # A mode with no price cannot have a cost below half of it. Failing here rather
            # than dividing keeps the criterion honest instead of arithmetically undefined.
            return float("inf")
        return self.cost_per_participant / self.price_per_participant


@dataclass(frozen=True)
class Report:
    """What a run measured, and whether it clears the bar."""

    participants: int
    duration_seconds: float
    latency_p50: float
    latency_p95: float
    max_lag_seconds: float
    condensed_ratio: float
    block_count: int
    block_seconds: float
    meta_speech_by_tier: dict[Tier, float | None]
    failures: tuple[str, ...] = field(default=())

    @property
    def passed(self) -> bool:
        return not self.failures

    @classmethod
    def of(
        cls,
        metrics: SalonMetrics,
        *,
        participants: int,
        duration_seconds: float,
        cost: TierPrice | None = None,
    ) -> Report:
        failures: list[str] = []

        if metrics.latency_samples == 0:
            failures.append("latency: nothing was delivered, so there is nothing to judge")
        elif metrics.latency_p50 >= PASS_LATENCY_SECONDS:
            failures.append(
                f"latency: median {metrics.latency_p50:.1f}s is not below "
                f"{PASS_LATENCY_SECONDS:.0f}s"
            )

        if metrics.condensed_ratio >= PASS_CONDENSED_RATIO:
            failures.append(
                f"condensed content: {metrics.condensed_ratio:.1%} is not below "
                f"{PASS_CONDENSED_RATIO:.0%}"
            )

        if metrics.block_count:
            failures.append(
                f"blocks: {metrics.block_count} in this run, and the criterion is none at all"
            )
        elif duration_seconds < PASS_BLOCK_WINDOW_SECONDS:
            failures.append(
                f"blocks: this run lasted {duration_seconds:.0f}s, which cannot show an hour "
                "without one"
            )

        if cost is None:
            failures.append("cost: no cost or price was supplied, so it was not measured")
        elif cost.share >= PASS_COST_SHARE:
            failures.append(
                f"cost: {cost.share:.0%} of the price of the mode is not below "
                f"{PASS_COST_SHARE:.0%}"
            )

        return cls(
            participants=participants,
            duration_seconds=duration_seconds,
            latency_p50=metrics.latency_p50,
            latency_p95=metrics.latency_p95,
            max_lag_seconds=metrics.max_lag_seconds,
            condensed_ratio=metrics.condensed_ratio,
            block_count=metrics.block_count,
            block_seconds=metrics.block_seconds,
            meta_speech_by_tier=metrics.meta_speech_by_tier(),
            failures=tuple(failures),
        )
