"""What a Salon is measured by (NFR4), in test and in production alike.

Two families of number here, and they answer different questions.

The first is whether the system is coping: the lag of each cursor, the worst of them, the
latency at the median and at the tail, how much content had to be summarised, and how often
and how long somebody was blocked. The worst lag rather than the average, because one room
in trouble is the thing that matters and a mean would hide it behind forty rooms that are
fine. And p95 as well as p50, because the median says what usually happens while the tail is
where somebody is actually having a bad time.

The second is the meta-speech ratio: how much of what a participant hears was said by
nobody in the room. It is the tax the architecture charges for existing, and it is broken
down by tier because the cheapest tier interrupts most — a single number averaged over all
four would hide exactly the trade the tiers are there to make.
"""
from __future__ import annotations

from math import ceil

from dataclasses import dataclass, field

from src.tiers import Tier


# Re-exported, not redefined. The tiers decide how often somebody is advertised at and which
# model their adapter is given (Story 9.4), so they belong to the product rather than to the
# harness that measures it — and two enums with the same members would compare unequal.
__all__ = ["SalonMetrics", "Tier"]


def _percentile(values: list[float], fraction: float) -> float:
    """Nearest-rank, which needs no interpolation and no assumption about the distribution.

    Zero for an empty sample. A latency of nothing is the honest answer when nothing was
    delivered, and it is never mistaken for a good one because the report also carries how
    many samples there were.
    """
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = max(1, min(len(ordered), ceil(fraction * len(ordered))))
    return ordered[rank - 1]


@dataclass
class _Speech:
    """Seconds spoken at one tier, split the three ways the ratio needs."""

    journal: float = 0.0
    meta: float = 0.0
    condensed: float = 0.0


@dataclass
class SalonMetrics:
    """Everything one Salon run is judged by."""

    _lags: dict[str, float] = field(default_factory=dict)
    _latencies: list[float] = field(default_factory=list)
    _content_seconds: float = 0.0
    _condensed_seconds: float = 0.0
    _blocks_open: dict[str, float] = field(default_factory=dict)
    _block_count: int = 0
    _block_seconds: float = 0.0
    _speech: dict[Tier, _Speech] = field(default_factory=dict)
    # Story 9.4. The same content and condensation figures, kept per tier as well as in
    # total. Advertising slows a cursor down, so Base condenses more often than Mode A and
    # Mode A more often than a tier that hears none — and the totals, which mix the tiers
    # together, are exactly where that gradient disappears.
    _content_by_tier: dict[Tier, float] = field(default_factory=dict)
    _condensed_by_tier: dict[Tier, float] = field(default_factory=dict)
    _blocks_by_tier: dict[Tier, int] = field(default_factory=dict)

    # ── Recording ─────────────────────────────────────────────────────────────

    def record_lag(self, participant_id: str, seconds: float) -> None:
        """Keep the worst this cursor ever reached, not the last thing it happened to be.

        Sampled at the end of a run, a lag reads as zero whenever condensation has just
        fired — which is precisely the moment somebody was furthest behind. The peak is the
        number that says whether the Salon coped.
        """
        self._lags[participant_id] = max(self._lags.get(participant_id, 0.0), seconds)

    def record_latency(self, seconds: float) -> None:
        self._latencies.append(seconds)

    def record_content(self, seconds: float, *, tier: Tier | None = None) -> None:
        """Content that reached the journal, whatever became of it afterwards."""
        self._content_seconds += seconds
        if tier is not None:
            self._content_by_tier[tier] = self._content_by_tier.get(tier, 0.0) + seconds

    def record_condensed(self, seconds: float, *, tier: Tier | None = None) -> None:
        """Content that was summarised rather than delivered in full."""
        self._condensed_seconds += seconds
        if tier is not None:
            self._condensed_by_tier[tier] = self._condensed_by_tier.get(tier, 0.0) + seconds

    def record_block(
        self, participant_id: str, *, at: float, tier: Tier | None = None
    ) -> None:
        if participant_id in self._blocks_open:
            return
        self._blocks_open[participant_id] = at
        self._block_count += 1
        if tier is not None:
            self._blocks_by_tier[tier] = self._blocks_by_tier.get(tier, 0) + 1

    def record_unblock(self, participant_id: str, *, at: float) -> None:
        started = self._blocks_open.pop(participant_id, None)
        if started is None:
            # Never blocked, or already released. Counting it would invent a block.
            return
        self._block_seconds += at - started

    def close(self, *, at: float) -> None:
        """End the run, charging any block still open up to this moment.

        Without it the worst run imaginable — blocked and never released — would report no
        blocked time at all, which is the one result nobody should be able to get.
        """
        for participant_id in list(self._blocks_open):
            self.record_unblock(participant_id, at=at)

    def record_spoken(
        self,
        tier: Tier,
        *,
        seconds: float,
        meta: bool,
        condensed: bool = False,
        announces_condensation: bool = False,
    ) -> None:
        """One thing said to one participant, filed by what kind of speech it was.

        `condensed` content is set aside from both sides of the ratio: it is neither the
        journal spoken faithfully nor the system talking about itself. The sentence that
        *announces* a condensation is the opposite — it is the system talking about itself,
        and it is precisely the interruption the ratio exists to make visible.
        """
        speech = self._speech.setdefault(tier, _Speech())
        if condensed and not announces_condensation:
            speech.condensed += seconds
        elif meta:
            speech.meta += seconds
        else:
            speech.journal += seconds

    # ── Reading ───────────────────────────────────────────────────────────────

    def lag_of(self, participant_id: str) -> float:
        return self._lags.get(participant_id, 0.0)

    @property
    def max_lag_seconds(self) -> float:
        return max(self._lags.values(), default=0.0)

    @property
    def latency_p50(self) -> float:
        return _percentile(self._latencies, 0.5)

    @property
    def latency_p95(self) -> float:
        return _percentile(self._latencies, 0.95)

    @property
    def latency_samples(self) -> int:
        return len(self._latencies)

    @property
    def condensed_ratio(self) -> float:
        """The share of content that was summarised rather than delivered in full."""
        if self._content_seconds <= 0:
            return 0.0
        return self._condensed_seconds / self._content_seconds

    @property
    def block_count(self) -> int:
        return self._block_count

    @property
    def block_seconds(self) -> float:
        return self._block_seconds

    def meta_speech_ratio(self, tier: Tier | None = None) -> float | None:
        """Speech that came from nobody in the room, over all speech that was not a summary.

        `None` rather than zero when nothing was said at all: a silent Salon has no ratio,
        and reporting 0.0 would read as a system that never interrupts.
        """
        if tier is None:
            speeches = list(self._speech.values())
        else:
            speech = self._speech.get(tier)
            speeches = [speech] if speech else []

        meta = sum(one.meta for one in speeches)
        journal = sum(one.journal for one in speeches)
        if meta + journal <= 0:
            return None
        return meta / (meta + journal)

    def condensed_ratio_of(self, tier: Tier) -> float | None:
        """The share of this tier's content that was summarised, or `None` if it never ran.

        `None` rather than zero, for the same reason the meta-speech ratio uses it: a tier
        that never ran and a tier that never once had to condense are opposite findings, and
        this figure exists to tell somebody whether Base is usable or merely degraded.
        """
        content = self._content_by_tier.get(tier, 0.0)
        if content <= 0:
            return None
        return self._condensed_by_tier.get(tier, 0.0) / content

    def condensed_by_tier(self) -> dict[Tier, float | None]:
        """Every tier, including the ones that never ran (NFR4)."""
        return {tier: self.condensed_ratio_of(tier) for tier in Tier}

    def blocks_by_tier(self) -> dict[Tier, int]:
        """How often a room at each tier saturated (FR49).

        Zero rather than `None` here: a saturation is a count of events, and none having
        happened is a real answer, where a *ratio* over no content is not.
        """
        return {tier: self._blocks_by_tier.get(tier, 0) for tier in Tier}

    def meta_speech_by_tier(self) -> dict[Tier, float | None]:
        """Every tier, including the ones that never ran.

        A missing row reads as "no interruptions" when what it means is "never ran", and
        those are opposite conclusions about a tier somebody is deciding whether to ship.
        """
        return {tier: self.meta_speech_ratio(tier) for tier in Tier}
