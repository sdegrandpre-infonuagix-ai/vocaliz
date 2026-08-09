"""Running N simulated participants against a real Salon and measuring what happens.

The Salon under test is the real one — the real journal, the real cursors, the real
condensation and saturation rules. Only the humans and the interpreters are simulated, which
is the only substitution that keeps the measurement worth anything: replacing the conductor
would measure the harness.

Scenario time is not wall-clock time. An hour-long scenario runs in milliseconds because
every turn carries the moment it was *meant* to happen, and nothing sleeps. A load test that
took an hour to tell you about an hour would never be run.
"""
from __future__ import annotations

from dataclasses import dataclass

from src.interprete import InterpreteFake, Participant
from src.journal import InMemoryJournalStore, SalonLog, content_seconds
from src.load.metrics import SalonMetrics, Tier
from src.load.report import Report, TierPrice
from src.load.speaker import SimulatedSpeaker
from src.salon import InMemoryRoomProvisioner, Salon
from src.settings import SalonSettings

# Enough languages that translation is exercised rather than short-circuited by everybody
# sharing one, and few enough that the cache is still doing its job.
_LANGUAGES = ("fr", "en", "es", "de", "pt", "it")


def cast_of(count: int) -> list[Participant]:
    """`count` participants, spread across the offered languages."""
    return [
        Participant(
            id=f"p{index:03d}",
            language=_LANGUAGES[index % len(_LANGUAGES)],
            name=f"Participant {index}",
        )
        for index in range(count)
    ]


@dataclass(frozen=True)
class Scenario:
    """What to run: how many people, for how long, and how talkative each of them is."""

    participants: int = 50
    duration_seconds: float = 3600.0
    cadence_seconds: float = 60.0
    words_per_turn: int = 40
    tier: Tier = Tier.BASE
    # How fast an interpreter renders, as a multiple of real time. 1.0 means it
    # takes a minute to say a minute of content, which is what a voice does — and
    # modelling it is the only reason anybody in this harness can fall behind.
    render_speed: float = 1.0
    seed: int = 0
    cost: TierPrice | None = None
    # The thresholds to run against. Left out, the shipped defaults apply —
    # supplying them is how a scenario answers what a different tuning would do,
    # which is most of what somebody runs a load harness to find out.
    settings: SalonSettings | None = None


async def run(scenario: Scenario) -> Report:
    """Play the whole scenario and report on it.

    Every turn is ingested at its scheduled moment and every interpreter is given the chance
    to catch up, so the lags, the condensations and the blocks that come out are the real
    ones the conductor produced rather than numbers this module invented.
    """
    cast = cast_of(scenario.participants)
    log = SalonLog(salon_id="load", store=InMemoryJournalStore(), translate=_translate)
    salon = Salon(log=log, rooms=InMemoryRoomProvisioner(), settings=scenario.settings)
    metrics = SalonMetrics()

    for participant in cast:
        await salon.join(participant, InterpreteFake(participant=participant))

    speakers = [
        SimulatedSpeaker(
            participant=participant,
            cadence_seconds=scenario.cadence_seconds,
            words_per_turn=scenario.words_per_turn,
            seed=scenario.seed,
        )
        for participant in cast
    ]

    # One flat timeline, so turns interleave the way they would in a real conversation
    # rather than one participant at a time.
    timeline: list[tuple[float, SimulatedSpeaker, str]] = sorted(
        (
            (at, speaker, text)
            for speaker in speakers
            for at, text in speaker.turns_until(scenario.duration_seconds)
        ),
        # By time, then by who: two people speaking at the same scenario moment need a
        # settled order, and it has to be one that does not depend on object identity or
        # the run stops being reproducible.
        key=lambda scheduled: (scheduled[0], scheduled[1].participant.id),
    )

    blocked: set[str] = set()
    counted: dict[str, int] = {}
    # Seconds of rendering each interpreter has banked but not yet spent. Without this every
    # interpreter would drain its backlog instantly, nobody could ever fall behind, and the
    # harness could only ever confirm that everything is fine.
    budget: dict[str, float] = {participant.id: 0.0 for participant in cast}
    previous = 0.0

    for at, speaker, text in timeline:
        # Releases are reconciled at the top of the step, so a room blocked at one moment and
        # freed by the catch-up that followed is charged for the interval in between rather
        # than for no time at all.
        _note_releases(salon, blocked, metrics, at)

        recorded = await salon.ingest(
            speaker.participant.id, text, language=speaker.language
        )
        for entry in recorded:
            metrics.record_content(content_seconds(entry.text), tier=scenario.tier)

        # A block is recorded where it actually costs somebody something: their turn was
        # refused. Sampling the flag instead would count rooms that were briefly saturated
        # between two deliveries and never stopped anybody from saying anything.
        if not recorded and salon.is_saturated(speaker.participant.id):
            blocked.add(speaker.participant.id)
            metrics.record_block(speaker.participant.id, at=at, tier=scenario.tier)

        # Sampled before the catch-up rather than after it: `record_lag` keeps the peak, and
        # a reading taken afterwards reports zero whenever condensation has just fired —
        # which is exactly the moment somebody was furthest behind.
        for participant in cast:
            metrics.record_lag(participant.id, salon.log.lag_seconds(participant.id))

        elapsed = at - previous
        previous = at
        for participant in cast:
            budget[participant.id] += elapsed * scenario.render_speed
            before = salon.pending_for(participant.id)
            spent = await _catch_up(salon, participant.id, budget[participant.id])
            budget[participant.id] = max(0.0, budget[participant.id] - spent)
            _note_delivery(
                salon, participant, before, metrics, scenario.tier, counted
            )

    _note_releases(salon, blocked, metrics, scenario.duration_seconds)
    metrics.close(at=scenario.duration_seconds)

    return Report.of(
        metrics,
        participants=scenario.participants,
        duration_seconds=scenario.duration_seconds,
        cost=scenario.cost,
    )


async def _translate(text: str, *, source: str, target: str) -> str:
    """No provider. The load harness must cost nothing to run, which is its entire point."""
    return text


def _note_releases(salon, blocked: set[str], metrics: SalonMetrics, at: float) -> None:
    """Close out every room that has come back under the reopening threshold."""
    for participant_id in list(blocked):
        if not salon.is_saturated(participant_id):
            blocked.discard(participant_id)
            metrics.record_unblock(participant_id, at=at)


def _note_delivery(
    salon,
    participant,
    before,
    metrics: SalonMetrics,
    tier: Tier,
    counted: dict[str, int],
) -> None:
    """Record what this delivery cost the listener, and what kind of speech it was.

    Latency is measured in seconds of content the listener was behind when the delivery
    began, not on a stopwatch. Scenario time is not wall-clock time — an hour-long run takes
    milliseconds — so a clock here would be timing the test runner rather than the system.
    """
    if before:
        metrics.record_latency(sum(content_seconds(entry.text) for entry in before))

    spoken = salon.interpreter_of(participant.id).spoken
    already = counted.get(participant.id, 0)
    for line in spoken[already:]:
        seconds = content_seconds(line.text)
        if line.kind == "condense":
            metrics.record_condensed(seconds, tier=tier)
            metrics.record_spoken(tier, seconds=seconds, meta=False, condensed=True)
        elif line.kind == "annonce":
            # Introductions, arrivals, the busy signal, and the sentence that announces a
            # condensation. All of it is the system talking rather than a participant.
            metrics.record_spoken(tier, seconds=seconds, meta=True)
        else:
            metrics.record_spoken(tier, seconds=seconds, meta=False)
    counted[participant.id] = len(spoken)


async def _catch_up(salon, participant_id: str, allowance: float) -> float:
    """Render as much as this interpreter has had time for, and report what it cost.

    Two paths, and the difference between them is the whole point of condensation. Far
    enough behind and `deliver` summarises the backlog, which moves the cursor faster than
    real time — the only way somebody who has fallen behind ever gets back. Otherwise the
    interpreter renders message by message, and stops when it runs out of the time it has
    actually had.
    """
    pending = salon.pending_for(participant_id)
    if not pending or allowance <= 0:
        # An interpreter with no time renders nothing at all, summaries included. Treating
        # condensation as free would let every room rescue itself on every step, and
        # saturation — which is what happens when condensation cannot keep up — could then
        # never be reached by any scenario.
        return 0.0

    if salon.log.lag_seconds(participant_id) > salon.condensation_threshold_seconds:
        # A summary is quick to say, which is why it is what a lagging interpreter does.
        await salon.deliver(participant_id)
        return allowance

    spent = 0.0
    reached: int | None = None
    for entry in pending:
        cost = content_seconds(entry.text)
        if spent + cost > allowance:
            break
        spent += cost
        reached = entry.sequence

    if reached is None:
        return 0.0
    await salon.deliver_upto(participant_id, reached)
    return spent
