"""Simulated speakers and the load harness (FR58 / NFR4).

The point of this is a decision. Raising the participant ceiling from 3 to 50 is either a
measurement or a bet, and the only way to make it a measurement is to be able to run 50
participants without paying a provider for any of them. So the simulated speaker generates
its own turns — at a cadence, a length and a language somebody chooses — and does it
deterministically, because a load result that changes between runs measures the generator
rather than the system.

`InterpreteFake` was already reactive: you queue what its human says. What was missing is
something that decides *when* and *what* on its own, which is what a scenario needs.
"""
import pytest

from src.interprete import Participant
from src.load import (
    PASS_CONDENSED_RATIO,
    PASS_LATENCY_SECONDS,
    Report,
    SalonMetrics,
    SimulatedSpeaker,
    Tier,
    TierPrice,
)

MARIE = Participant(id="marie", language="fr", name="Marie")
HANS = Participant(id="hans", language="de", name="Hans")


# ── The simulated speaker ─────────────────────────────────────────────────────


def test_it_speaks_at_the_cadence_it_was_given():
    speaker = SimulatedSpeaker(participant=MARIE, cadence_seconds=20.0)

    turns = speaker.turns_until(100.0)

    assert [at for at, _ in turns] == [20.0, 40.0, 60.0, 80.0, 100.0]


def test_a_faster_cadence_produces_more_turns():
    slow = SimulatedSpeaker(participant=MARIE, cadence_seconds=20.0)
    fast = SimulatedSpeaker(participant=MARIE, cadence_seconds=5.0)

    assert len(fast.turns_until(100.0)) > len(slow.turns_until(100.0))


def test_the_length_is_what_was_asked_for():
    speaker = SimulatedSpeaker(participant=MARIE, words_per_turn=40)

    _, text = speaker.turns_until(20.0)[0]

    assert len(text.split()) == 40


def test_the_language_is_what_was_asked_for():
    speaker = SimulatedSpeaker(participant=HANS, language="de")

    assert speaker.language == "de"


def test_the_language_defaults_to_the_participants_own():
    """Somebody speaking a language they do not speak is a scenario nobody meant to write."""
    speaker = SimulatedSpeaker(participant=HANS)

    assert speaker.language == "de"


def test_the_same_seed_gives_the_same_words():
    """A load result that changes between runs measures the generator, not the system."""
    first = SimulatedSpeaker(participant=MARIE, seed=7).turns_until(100.0)
    second = SimulatedSpeaker(participant=MARIE, seed=7).turns_until(100.0)

    assert first == second


def test_a_different_seed_gives_different_words():
    first = SimulatedSpeaker(participant=MARIE, seed=1).turns_until(100.0)
    second = SimulatedSpeaker(participant=MARIE, seed=2).turns_until(100.0)

    assert first != second


def test_two_speakers_in_one_scenario_do_not_say_the_same_thing():
    """Fifty participants all emitting identical text would make the translation cache do
    the work the load test is supposed to be measuring."""
    marie = SimulatedSpeaker(participant=MARIE, seed=1).turns_until(60.0)
    hans = SimulatedSpeaker(participant=HANS, seed=1).turns_until(60.0)

    assert [text for _, text in marie] != [text for _, text in hans]


def test_the_words_survive_the_cleaner():
    """Story 6.11 collapses repeated short words. A generator that produced them would be
    measuring a system that had thrown most of its input away."""
    from src.journal import clean

    _, text = SimulatedSpeaker(participant=MARIE, words_per_turn=40).turns_until(20.0)[0]

    assert len(clean(text).split()) == 40


def test_it_calls_no_provider_at_all():
    """The whole reason it exists. Fifty simulated participants must cost nothing."""
    speaker = SimulatedSpeaker(participant=MARIE)

    assert speaker.provider_calls == 0
    speaker.turns_until(3600.0)
    assert speaker.provider_calls == 0


# ── What a run measures ───────────────────────────────────────────────────────


def test_the_lag_of_each_cursor_is_reported():
    metrics = SalonMetrics()
    metrics.record_lag("marie", 12.0)
    metrics.record_lag("hans", 40.0)

    assert metrics.lag_of("marie") == 12.0
    assert metrics.lag_of("hans") == 40.0


def test_the_worst_lag_in_the_salon_is_reported():
    """One number for whether the Salon is coping, since one room in trouble is the thing
    that matters and an average would hide it behind forty rooms that are fine."""
    metrics = SalonMetrics()
    metrics.record_lag("marie", 12.0)
    metrics.record_lag("hans", 40.0)

    assert metrics.max_lag_seconds == 40.0


def test_the_worst_lag_of_nothing_is_nothing():
    assert SalonMetrics().max_lag_seconds == 0.0


def test_latency_is_reported_at_the_median_and_the_tail():
    """p95 and not just p50: the median says what usually happens, and the tail is where
    somebody is actually having a bad time."""
    metrics = SalonMetrics()
    for value in (1.0, 2.0, 3.0, 4.0, 100.0):
        metrics.record_latency(value)

    assert metrics.latency_p50 == 3.0
    assert metrics.latency_p95 == 100.0


def test_latency_percentiles_of_nothing_are_nothing():
    assert SalonMetrics().latency_p50 == 0.0
    assert SalonMetrics().latency_p95 == 0.0


def test_the_condensation_rate_is_the_share_of_content_summarised():
    """`record_content` is everything that reached the journal, and what was condensed is a
    part of it — not a separate pile to be added on."""
    metrics = SalonMetrics()
    metrics.record_content(1000.0)
    metrics.record_condensed(200.0)

    assert metrics.condensed_ratio == pytest.approx(0.2)


def test_nothing_condensed_is_a_rate_of_zero():
    metrics = SalonMetrics()
    metrics.record_content(800.0)

    assert metrics.condensed_ratio == 0.0


def test_a_silent_salon_has_no_condensation_rate_rather_than_a_division_by_zero():
    assert SalonMetrics().condensed_ratio == 0.0


def test_blocks_are_counted_and_timed():
    """Both, because they answer different questions: how often the system gave up, and for
    how long somebody could not speak."""
    metrics = SalonMetrics()
    metrics.record_block("hans", at=100.0)
    metrics.record_unblock("hans", at=160.0)
    metrics.record_block("hans", at=300.0)
    metrics.record_unblock("hans", at=310.0)

    assert metrics.block_count == 2
    assert metrics.block_seconds == 70.0


def test_a_block_still_open_at_the_end_counts_up_to_the_end():
    """Otherwise the worst run imaginable — blocked and never released — reports no blocked
    time at all."""
    metrics = SalonMetrics()
    metrics.record_block("hans", at=100.0)

    metrics.close(at=400.0)

    assert metrics.block_count == 1
    assert metrics.block_seconds == 300.0


def test_unblocking_something_that_was_not_blocked_is_ignored():
    metrics = SalonMetrics()

    metrics.record_unblock("hans", at=160.0)

    assert metrics.block_count == 0


# ── The meta-speech ratio ─────────────────────────────────────────────────────


def test_it_reports_speech_that_came_from_nobody_in_the_room():
    """Announcements, introductions, notices. Everything the participant hears that no
    participant said — which is the tax the architecture charges for existing."""
    metrics = SalonMetrics()
    metrics.record_spoken(Tier.BASE, seconds=90.0, meta=False)
    metrics.record_spoken(Tier.BASE, seconds=10.0, meta=True)

    assert metrics.meta_speech_ratio() == pytest.approx(0.1)


def test_condensed_content_is_left_out_of_both_sides():
    """It is neither the journal spoken faithfully nor the system talking about itself, and
    counting it either way would make the ratio say something it does not mean."""
    metrics = SalonMetrics()
    metrics.record_spoken(Tier.BASE, seconds=90.0, meta=False)
    metrics.record_spoken(Tier.BASE, seconds=10.0, meta=True)
    metrics.record_spoken(Tier.BASE, seconds=500.0, meta=False, condensed=True)

    assert metrics.meta_speech_ratio() == pytest.approx(0.1)


def test_but_the_sentence_that_announces_a_condensation_counts():
    """"While you were listening, three people spoke" is the system talking about itself. It
    is exactly the interruption this ratio exists to make visible."""
    metrics = SalonMetrics()
    metrics.record_spoken(Tier.BASE, seconds=90.0, meta=False)
    metrics.record_spoken(Tier.BASE, seconds=10.0, meta=True, announces_condensation=True)

    assert metrics.meta_speech_ratio() == pytest.approx(0.1)


def test_a_condensation_announcement_is_not_treated_as_condensed_content():
    metrics = SalonMetrics()
    metrics.record_spoken(Tier.BASE, seconds=100.0, meta=True, announces_condensation=True)

    assert metrics.meta_speech_ratio() == 1.0


def test_the_ratio_is_broken_down_by_tier():
    """The cheapest tier interrupts most, and a single number averaged over all four would
    hide exactly that. The breakdown is what makes the trade visible before it is priced."""
    metrics = SalonMetrics()
    metrics.record_spoken(Tier.BASE, seconds=80.0, meta=False)
    metrics.record_spoken(Tier.BASE, seconds=20.0, meta=True)
    metrics.record_spoken(Tier.MODE_C, seconds=99.0, meta=False)
    metrics.record_spoken(Tier.MODE_C, seconds=1.0, meta=True)

    assert metrics.meta_speech_ratio(Tier.BASE) == pytest.approx(0.2)
    assert metrics.meta_speech_ratio(Tier.MODE_C) == pytest.approx(0.01)


def test_every_tier_is_reported_even_when_it_said_nothing():
    """A missing row reads as "no interruptions" when it means "never ran"."""
    metrics = SalonMetrics()
    metrics.record_spoken(Tier.BASE, seconds=100.0, meta=False)

    breakdown = metrics.meta_speech_by_tier()

    assert set(breakdown) == set(Tier)
    assert breakdown[Tier.MODE_B] is None


def test_a_tier_that_spoke_reports_a_number():
    metrics = SalonMetrics()
    metrics.record_spoken(Tier.MODE_A, seconds=100.0, meta=False)

    assert metrics.meta_speech_by_tier()[Tier.MODE_A] == 0.0


def test_a_ratio_for_a_silent_salon_is_nothing_rather_than_a_division_by_zero():
    assert SalonMetrics().meta_speech_ratio() is None


# ── The report, and the criteria for raising the ceiling ──────────────────────


def _passing_metrics() -> SalonMetrics:
    metrics = SalonMetrics()
    for _ in range(20):
        metrics.record_latency(4.0)
    metrics.record_content(1000.0)
    metrics.record_condensed(50.0)
    metrics.record_spoken(Tier.BASE, seconds=1000.0, meta=False)
    metrics.record_spoken(Tier.BASE, seconds=50.0, meta=True)
    return metrics


def test_a_healthy_run_passes():
    report = Report.of(
        _passing_metrics(),
        participants=50,
        duration_seconds=3600.0,
        cost=TierPrice(cost_per_participant=0.40, price_per_participant=1.00),
    )

    assert report.passed is True


def test_the_thresholds_are_the_ones_the_decision_was_stated_with():
    assert PASS_LATENCY_SECONDS == 10.0
    assert PASS_CONDENSED_RATIO == 0.2


def test_a_slow_run_fails_and_says_why():
    metrics = _passing_metrics()
    for _ in range(40):
        metrics.record_latency(30.0)

    report = Report.of(metrics, participants=50, duration_seconds=3600.0)

    assert report.passed is False
    assert "latency" in " ".join(report.failures).lower()


def test_too_much_condensation_fails():
    metrics = _passing_metrics()
    metrics.record_condensed(500.0)

    report = Report.of(metrics, participants=50, duration_seconds=3600.0)

    assert report.passed is False
    assert "condens" in " ".join(report.failures).lower()


def test_a_single_block_in_an_hour_fails():
    """Zero over an hour, not few. A block is somebody being told to stop talking, and the
    criterion for raising the ceiling is that it does not happen at all."""
    metrics = _passing_metrics()
    metrics.record_block("hans", at=10.0)
    metrics.record_unblock("hans", at=11.0)

    report = Report.of(metrics, participants=50, duration_seconds=3600.0)

    assert report.passed is False
    assert "block" in " ".join(report.failures).lower()


def test_a_block_in_a_run_shorter_than_an_hour_is_still_a_failure():
    """A ten-minute run that blocked is not evidence of an hour without blocking. Scaling
    the criterion to the run length would turn a short run into a free pass."""
    metrics = _passing_metrics()
    metrics.record_block("hans", at=10.0)
    metrics.record_unblock("hans", at=11.0)

    report = Report.of(metrics, participants=50, duration_seconds=600.0)

    assert report.passed is False


def test_a_run_shorter_than_an_hour_cannot_prove_the_criterion():
    """Zero blocks in ten minutes says nothing about an hour, so the report says so rather
    than quietly reporting a pass it has not earned."""
    report = Report.of(_passing_metrics(), participants=50, duration_seconds=600.0)

    assert report.passed is False
    assert any("hour" in note.lower() for note in report.failures)


def test_costing_more_than_half_the_price_fails():
    report = Report.of(
        _passing_metrics(),
        participants=50,
        duration_seconds=3600.0,
        cost=TierPrice(cost_per_participant=0.60, price_per_participant=1.00),
    )

    assert report.passed is False
    assert "cost" in " ".join(report.failures).lower()


def test_exactly_half_the_price_fails_because_the_criterion_is_below():
    report = Report.of(
        _passing_metrics(),
        participants=50,
        duration_seconds=3600.0,
        cost=TierPrice(cost_per_participant=0.50, price_per_participant=1.00),
    )

    assert report.passed is False


def test_without_cost_figures_the_report_says_so_rather_than_assuming():
    """No prices supplied is not the same as the cost criterion being met, and a report that
    conflated them would sign off a ceiling raise on three criteria out of four."""
    report = Report.of(_passing_metrics(), participants=50, duration_seconds=3600.0)

    assert report.passed is False
    assert any("cost" in note.lower() for note in report.failures)


def test_the_report_carries_the_numbers_and_not_only_the_verdict():
    """Somebody deciding whether to raise a ceiling needs to see how close it was."""
    report = Report.of(
        _passing_metrics(),
        participants=50,
        duration_seconds=3600.0,
        cost=TierPrice(cost_per_participant=0.40, price_per_participant=1.00),
    )

    assert report.latency_p50 == 4.0
    assert report.participants == 50
    assert report.condensed_ratio == pytest.approx(0.05)
    assert report.block_count == 0


def test_blocking_an_already_blocked_room_does_not_count_twice():
    """Saturation is reviewed repeatedly while it holds. Counting each review would report a
    room that never recovered as hundreds of separate failures."""
    metrics = SalonMetrics()
    metrics.record_block("hans", at=100.0)

    metrics.record_block("hans", at=110.0)
    metrics.record_unblock("hans", at=160.0)

    assert metrics.block_count == 1
    assert metrics.block_seconds == 60.0


def test_a_mode_with_no_price_cannot_have_a_cost_below_half_of_it():
    """Dividing by a price of zero would make the criterion arithmetically undefined rather
    than failed, and an undefined criterion is one nobody notices was never checked."""
    report = Report.of(
        _passing_metrics(),
        participants=50,
        duration_seconds=3600.0,
        cost=TierPrice(cost_per_participant=0.10, price_per_participant=0.0),
    )

    assert report.passed is False
    assert "cost" in " ".join(report.failures).lower()


def test_a_run_that_delivered_nothing_cannot_pass_on_latency():
    """A silent run has a median latency of zero, which is the best possible number and
    means nothing at all. Passing on it would be the easiest way to fake a good result."""
    metrics = SalonMetrics()
    metrics.record_content(1000.0)

    report = Report.of(metrics, participants=50, duration_seconds=3600.0)

    assert report.passed is False
    assert "nothing was delivered" in " ".join(report.failures)
