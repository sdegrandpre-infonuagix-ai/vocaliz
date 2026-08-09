"""How often each tier is advertised at, and what its adapter is given (FR33 / NFR6).

Base hears one advertisement every five minutes, Mode A one every ten, Modes B and C none at
all. That is what paying more buys on this axis, and it has a second effect worth stating:
reading an advertisement occupies an interpreter, so its cursor advances more slowly and its
lag grows. A listener who hears none falls behind less than one in Mode A, who falls behind
less than one in Base — so they condense less often (FR53) and saturate more rarely (FR49).

The tiers are therefore a quality gradient with a mechanism behind it, not only a price list,
which is why the condensation rate and the saturation count are published per tier (NFR4). The
question those figures answer is whether Base stays *usable* rather than merely being degraded
enough to sell the upgrade.

The model is the other per-tier parameter. Mode C runs a later one than A and B; Base runs no
single model at all, being a chain of three providers. A test reads `src/` to check the names
appear in exactly one file: a model name compiled into the interpretation code would have to
be found in several places the day it changes, and one of them would be missed.
"""
import pathlib

import pytest

from src.interprete import InterpreteFake, Participant
from src.journal import InMemoryJournalStore, SalonLog
from src.salon import InMemoryRoomProvisioner, RegieFake, Salon
from src.settings import DEFAULTS, InvalidSettings, SalonSettings
from src.tiers import MODELS, Tier, advert_interval_seconds, model_for

MARIE = Participant(id="marie", language="fr", name="Marie")
HANS = Participant(id="hans", language="de", name="Hans")
SOFIA = Participant(id="sofia", language="es", name="Sofia")

FIVE_MINUTES = 300.0
TEN_MINUTES = 600.0


async def translate(text, *, source, target):
    return f"{text} [{target}]"


@pytest.fixture
def settings():
    return SalonSettings()


# ── The two frequencies ───────────────────────────────────────────────────────


def test_base_hears_one_every_five_minutes(settings):
    assert advert_interval_seconds(Tier.BASE, settings=settings) == FIVE_MINUTES


def test_mode_a_hears_one_every_ten_minutes(settings):
    assert advert_interval_seconds(Tier.MODE_A, settings=settings) == TEN_MINUTES


@pytest.mark.parametrize("tier", [Tier.MODE_B, Tier.MODE_C])
def test_the_paid_modes_hear_none(tier, settings):
    """`None` is never, and it is not a number somebody can set. Their price is what buys
    the silence, and a configurable interval would put that promise one typo away."""
    assert advert_interval_seconds(tier, settings=settings) is None


@pytest.mark.parametrize("tier", list(Tier))
def test_a_seat_the_host_pays_for_hears_none_at_any_tier(tier, settings):
    """The advertising is how an unpaid seat is paid for. Charging the host and then
    advertising at their guest is charging twice for one seat."""
    assert advert_interval_seconds(tier, settings=settings, covered=True) is None


def test_the_two_frequencies_move_independently(settings):
    """FR54. Two settings rather than one with a multiplier: the gap between the tiers is
    the product decision, and a ratio would move one of them by accident."""
    moved = settings.replace(advert_interval_mode_a_seconds=900.0)

    assert moved.advert_interval_base_seconds == FIVE_MINUTES
    assert moved.advert_interval_mode_a_seconds == 900.0
    assert advert_interval_seconds(Tier.BASE, settings=moved) == FIVE_MINUTES


def test_they_are_persisted_like_every_other_parameter():
    """Both live in `DEFAULTS`, which is what the settings table is built from — a parameter
    is added there and nowhere else."""
    assert DEFAULTS["advert_interval_base_seconds"] == FIVE_MINUTES
    assert DEFAULTS["advert_interval_mode_a_seconds"] == TEN_MINUTES


def test_base_may_not_be_advertised_at_less_often_than_mode_a(settings):
    """Upgrading would buy the same advertising or more of it, and the tier somebody paid
    for would be worse than the one they left — silently, since nothing else would fail."""
    with pytest.raises(InvalidSettings) as raised:
        settings.replace(advert_interval_base_seconds=1200.0)

    assert "advert_interval_base_seconds" in str(raised.value)
    assert "1200" in str(raised.value)


# ── The model per tier ────────────────────────────────────────────────────────


def test_mode_c_runs_a_later_model_than_a_and_b():
    assert model_for(Tier.MODE_C) == "grok-voice-think-fast-2.0"
    assert model_for(Tier.MODE_A) == "grok-voice-think-fast-1.0"
    assert model_for(Tier.MODE_B) == "grok-voice-think-fast-1.0"


def test_base_has_no_single_model():
    """Not an omission. Base is speech to text, then text, then speech — three providers in
    a chain, so there is no one model name to give it."""
    assert model_for(Tier.BASE) is None


def test_a_model_name_is_written_in_exactly_one_file():
    """NFR6: a per-tier adapter parameter and never a product constant. A name compiled into
    the interpretation code would have to be found in several places the day it changes."""
    root = pathlib.Path(__file__).resolve().parents[1] / "src"
    naming = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*.py")
        for model in set(MODELS.values())
        if model in path.read_text(encoding="utf-8")
    }

    assert naming == {"tiers.py"}


# ── The clock that makes a broadcast due ──────────────────────────────────────


def _salon(regie, **kwargs):
    return Salon(
        log=SalonLog(salon_id="s", store=InMemoryJournalStore(), translate=translate),
        rooms=InMemoryRoomProvisioner(),
        regie=regie,
        max_message_characters=100_000,
        **kwargs,
    )


async def _join(salon, participant, **kwargs):
    return await salon.join(participant, InterpreteFake(participant=participant), **kwargs)


async def _conversation(salon):
    """Two messages from two different people, which is where an advertisement may go."""
    await salon.ingest(MARIE.id, "Bonjour à tous.", language="fr")
    await salon.ingest(SOFIA.id, "Buenas tardes.", language="es")


def _heard(salon, participant_id, regie) -> int:
    return sum(
        1 for line in salon.interpreter_of(participant_id).spoken if regie.pitch in line.text
    )


@pytest.fixture
def regie():
    return RegieFake(pitch="Chez Rivard.")


async def test_base_becomes_due_after_five_minutes(regie):
    salon = _salon(regie)
    await _join(salon, MARIE, tier=Tier.BASE)
    await _join(salon, HANS, tier=Tier.BASE)
    await _join(salon, SOFIA, tier=Tier.BASE)
    await _conversation(salon)

    salon.advertising_tick(FIVE_MINUTES)
    await salon.deliver(HANS.id)

    assert _heard(salon, HANS.id, regie) == 1


async def test_base_is_not_due_before_that(regie):
    salon = _salon(regie)
    await _join(salon, MARIE, tier=Tier.BASE)
    await _join(salon, HANS, tier=Tier.BASE)
    await _join(salon, SOFIA, tier=Tier.BASE)
    await _conversation(salon)

    salon.advertising_tick(FIVE_MINUTES - 1)
    await salon.deliver(HANS.id)

    assert _heard(salon, HANS.id, regie) == 0


async def test_mode_a_is_still_silent_when_base_has_already_heard_one(regie):
    """The whole of what the upgrade buys on this axis, in one assertion."""
    salon = _salon(regie)
    await _join(salon, MARIE, tier=Tier.BASE)
    await _join(salon, HANS, tier=Tier.BASE)
    await _join(salon, SOFIA, tier=Tier.MODE_A)
    await _conversation(salon)
    await salon.ingest(HANS.id, "Guten Tag.", language="de")

    salon.advertising_tick(FIVE_MINUTES)
    await salon.deliver_all()

    assert _heard(salon, HANS.id, regie) == 1
    assert _heard(salon, SOFIA.id, regie) == 0


async def test_mode_a_becomes_due_at_ten_minutes(regie):
    salon = _salon(regie)
    await _join(salon, MARIE, tier=Tier.MODE_A)
    await _join(salon, HANS, tier=Tier.MODE_A)
    await _join(salon, SOFIA, tier=Tier.MODE_A)
    await _conversation(salon)

    salon.advertising_tick(TEN_MINUTES)
    await salon.deliver(HANS.id)

    assert _heard(salon, HANS.id, regie) == 1


@pytest.mark.parametrize("tier", [Tier.MODE_B, Tier.MODE_C])
async def test_the_paid_modes_are_never_due(tier, regie):
    salon = _salon(regie)
    await _join(salon, MARIE, tier=tier)
    await _join(salon, HANS, tier=tier)
    await _join(salon, SOFIA, tier=tier)
    await _conversation(salon)

    salon.advertising_tick(TEN_MINUTES * 10)
    await salon.deliver(HANS.id)

    assert _heard(salon, HANS.id, regie) == 0
    assert regie.draws == []


async def test_a_covered_seat_is_never_due(regie):
    """FR32. The host is paying for this one."""
    salon = _salon(regie)
    await _join(salon, MARIE, tier=Tier.BASE)
    await _join(salon, HANS, tier=Tier.BASE, covered=True)
    await _join(salon, SOFIA, tier=Tier.BASE)
    await _conversation(salon)

    salon.advertising_tick(FIVE_MINUTES * 4)
    await salon.deliver(HANS.id)

    assert _heard(salon, HANS.id, regie) == 0


async def test_the_frequency_is_a_ceiling_rather_than_a_quota(regie):
    """A slot still looking for a placement is not joined by a second. Two advertisements
    back to back would be the tier taking back with interest what a shortage of placements
    had cost it."""
    salon = _salon(regie)
    await _join(salon, MARIE, tier=Tier.BASE)
    await _join(salon, HANS, tier=Tier.BASE)
    await _join(salon, SOFIA, tier=Tier.BASE)
    await _conversation(salon)

    salon.advertising_tick(FIVE_MINUTES)
    salon.advertising_tick(FIVE_MINUTES)
    salon.advertising_tick(FIVE_MINUTES)
    await salon.deliver(HANS.id)

    assert _heard(salon, HANS.id, regie) == 1


async def test_the_schedule_restarts_rather_than_carrying_the_remainder(regie):
    """A tick longer than the interval does not owe several. Nobody hears four minutes of
    advertising because a worker was slow."""
    salon = _salon(regie)
    await _join(salon, MARIE, tier=Tier.BASE)
    await _join(salon, HANS, tier=Tier.BASE)
    await _join(salon, SOFIA, tier=Tier.BASE)
    await _conversation(salon)
    salon.advertising_tick(FIVE_MINUTES * 3)
    await salon.deliver(HANS.id)

    await salon.ingest(MARIE.id, "Encore une chose.", language="fr")
    salon.advertising_tick(FIVE_MINUTES - 1)
    await salon.deliver(HANS.id)

    assert _heard(salon, HANS.id, regie) == 1


async def test_a_salon_reports_the_interval_of_each_seat(regie):
    salon = _salon(regie)
    await _join(salon, MARIE, tier=Tier.BASE)
    await _join(salon, HANS, tier=Tier.MODE_A)
    await _join(salon, SOFIA, tier=Tier.MODE_C)

    assert salon.advert_interval_of(MARIE.id) == FIVE_MINUTES
    assert salon.advert_interval_of(HANS.id) == TEN_MINUTES
    assert salon.advert_interval_of(SOFIA.id) is None
    assert salon.tier_of(HANS.id) is Tier.MODE_A


async def test_a_participant_who_never_joined_has_no_tier(regie):
    salon = _salon(regie)

    assert salon.tier_of("nobody") is None
    assert salon.advert_interval_of("nobody") is None


async def test_base_is_the_tier_of_a_seat_nobody_named(regie):
    """The tier somebody has not paid for is the one they are on."""
    salon = _salon(regie)
    await _join(salon, MARIE)

    assert salon.tier_of(MARIE.id) is Tier.BASE


async def test_the_interval_follows_the_settings(regie):
    """Persisted and adjustable while a Salon is running badly, like every other number in
    `SalonSettings` — the reason they are not in `config.py`."""
    salon = _salon(regie, settings=SalonSettings(advert_interval_base_seconds=60.0))
    await _join(salon, MARIE, tier=Tier.BASE)
    await _join(salon, HANS, tier=Tier.BASE)
    await _join(salon, SOFIA, tier=Tier.BASE)
    await _conversation(salon)

    salon.advertising_tick(60.0)
    await salon.deliver(HANS.id)

    assert _heard(salon, HANS.id, regie) == 1


# ── What the gradient is measured by (NFR4) ───────────────────────────────────


def test_condensation_is_reported_per_tier():
    """Advertising slows a cursor down, so Base condenses more often than Mode A. The total,
    which mixes the tiers, is exactly where that gradient disappears."""
    from src.load.metrics import SalonMetrics

    metrics = SalonMetrics()
    metrics.record_content(100.0, tier=Tier.BASE)
    metrics.record_condensed(40.0, tier=Tier.BASE)
    metrics.record_content(100.0, tier=Tier.MODE_A)
    metrics.record_condensed(10.0, tier=Tier.MODE_A)

    assert metrics.condensed_ratio_of(Tier.BASE) == pytest.approx(0.4)
    assert metrics.condensed_ratio_of(Tier.MODE_A) == pytest.approx(0.1)
    assert metrics.condensed_ratio == pytest.approx(0.25)


def test_a_tier_that_never_ran_has_no_condensation_ratio():
    """`None` rather than zero. A tier that never ran and a tier that never once had to
    condense are opposite findings, and this figure exists to say whether Base is usable or
    merely degraded."""
    from src.load.metrics import SalonMetrics

    metrics = SalonMetrics()
    metrics.record_content(100.0, tier=Tier.BASE)

    assert metrics.condensed_ratio_of(Tier.BASE) == 0.0
    assert metrics.condensed_ratio_of(Tier.MODE_C) is None
    assert set(metrics.condensed_by_tier()) == set(Tier)


def test_saturations_are_counted_per_tier():
    """FR49. A count, so none having happened is a real answer rather than an absence."""
    from src.load.metrics import SalonMetrics

    metrics = SalonMetrics()
    metrics.record_block("marie", at=1.0, tier=Tier.BASE)
    metrics.record_block("hans", at=2.0, tier=Tier.BASE)
    metrics.record_block("sofia", at=3.0, tier=Tier.MODE_A)

    assert metrics.blocks_by_tier() == {
        Tier.BASE: 2, Tier.MODE_A: 1, Tier.MODE_B: 0, Tier.MODE_C: 0
    }
    assert metrics.block_count == 3


def test_the_report_publishes_both_per_tier():
    """Instrumented and then actually published. A figure recorded and never surfaced is a
    figure nobody will look at when deciding whether Base is shippable."""
    from src.load.metrics import SalonMetrics
    from src.load.report import Report

    metrics = SalonMetrics()
    metrics.record_content(100.0, tier=Tier.BASE)
    metrics.record_condensed(40.0, tier=Tier.BASE)
    metrics.record_block("marie", at=1.0, tier=Tier.BASE)

    report = Report.of(metrics, participants=1, duration_seconds=60.0)

    assert report.condensed_by_tier[Tier.BASE] == pytest.approx(0.4)
    assert report.blocks_by_tier[Tier.BASE] == 1
    assert report.condensed_by_tier[Tier.MODE_C] is None


def test_the_tier_is_one_enum_everywhere():
    """Two enums with the same members compare unequal, and the figures are published per
    tier — a second definition would silently split every report in half."""
    from src.load.metrics import Tier as FromMetrics

    assert FromMetrics is Tier
