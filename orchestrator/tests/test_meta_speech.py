"""The order several interpreter utterances come out in when they are ready together (FR62).

The problem this solves is not fairness, it is reproducibility. Four things can become ready
during one long intervention, and if the sequence they emerge in depends on which coroutine
happened to resume first, then the same scenario produces different audio twice and no test
can pin any of it down.

So the order is a property of the queue rather than of the event loop, and it sequences
without arbitrating: nothing is dropped and nothing waits forever. Everything ready comes
out, one after another, in an order somebody chose on purpose.

Two kinds of speech deliberately stay outside it. A participant's introduction and their
history are said as they enter the room, before they are in the conversation at all, so they
never compete with any of this. And the sentence announcing a condensation belongs to the
summary it introduces — separating them would leave "while you were listening, three people
spoke" stranded next to something else entirely.
"""
import pytest

from src.interprete import Annonce
from src.salon.meta_speech import MetaSpeechQueue, Urgency


def _annonce(text: str) -> Annonce:
    return Annonce(text=text, language="fr")


def _texts(queue: MetaSpeechQueue) -> list[str]:
    return [annonce.text for annonce in queue.drain()]


# ── The order ─────────────────────────────────────────────────────────────────


def test_the_busy_signal_comes_first():
    """It is the one that says the conversation is running away from them. Anything said
    before it is said to somebody who does not yet know why they are lost."""
    queue = MetaSpeechQueue()
    queue.add(_annonce("advert"), urgency=Urgency.ADVERT)
    queue.add(_annonce("busy"), urgency=Urgency.BUSY)

    assert _texts(queue)[0] == "busy"


def test_a_balance_alert_comes_before_an_advertisement():
    """Being told the Salon is about to end matters more than anything being sold, and an
    advertisement that pushed it later could push it past the end itself."""
    queue = MetaSpeechQueue()
    queue.add(_annonce("advert"), urgency=Urgency.ADVERT)
    queue.add(_annonce("balance"), urgency=Urgency.BALANCE)

    assert _texts(queue) == ["balance", "advert"]


def test_the_whole_order_holds_at_once():
    queue = MetaSpeechQueue()
    queue.add(_annonce("advert"), urgency=Urgency.ADVERT)
    queue.add(_annonce("notice"), urgency=Urgency.NOTICE)
    queue.add(_annonce("balance"), urgency=Urgency.BALANCE)
    queue.add(_annonce("busy"), urgency=Urgency.BUSY)

    assert _texts(queue) == ["busy", "balance", "notice", "advert"]


def test_an_advertisement_is_always_last():
    """Whatever else is waiting. It is the only one of these that serves somebody other than
    the person listening."""
    queue = MetaSpeechQueue()
    queue.add(_annonce("advert"), urgency=Urgency.ADVERT)
    for urgency in (Urgency.BUSY, Urgency.BALANCE, Urgency.NOTICE):
        queue.add(_annonce(urgency.name), urgency=urgency)

    assert _texts(queue)[-1] == "advert"


def test_the_ranks_are_ordered_the_way_the_specification_lists_them():
    assert Urgency.BUSY.rank < Urgency.BALANCE.rank < Urgency.ADVERT.rank


def test_an_ordinary_notice_never_lets_an_advertisement_go_first():
    """Arrivals and microphone changes are not in the specification's list. Putting them
    ahead of advertising is the reading that keeps the three ranked kinds in exactly the
    order given while refusing to let anything sold jump a fact about the conversation."""
    assert Urgency.NOTICE.rank < Urgency.ADVERT.rank
    assert Urgency.NOTICE.rank > Urgency.BALANCE.rank


# ── It sequences, it does not arbitrate ───────────────────────────────────────


def test_nothing_is_dropped():
    """The order decides who goes first, never who goes at all."""
    queue = MetaSpeechQueue()
    for urgency in Urgency:
        queue.add(_annonce(urgency.name), urgency=urgency)

    assert len(_texts(queue)) == len(list(Urgency))


def test_a_low_priority_utterance_is_not_postponed_for_ever():
    """It goes last in its round, not into a round that never comes. Starving the last rank
    would be arbitration by another name."""
    queue = MetaSpeechQueue()
    queue.add(_annonce("advert"), urgency=Urgency.ADVERT)
    queue.add(_annonce("busy"), urgency=Urgency.BUSY)

    assert "advert" in _texts(queue)


def test_draining_empties_the_queue():
    queue = MetaSpeechQueue()
    queue.add(_annonce("busy"), urgency=Urgency.BUSY)

    queue.drain()

    assert queue.waiting == 0
    assert queue.drain() == ()


def test_something_added_after_a_drain_comes_out_next_time():
    queue = MetaSpeechQueue()
    queue.add(_annonce("busy"), urgency=Urgency.BUSY)
    queue.drain()

    queue.add(_annonce("advert"), urgency=Urgency.ADVERT)

    assert _texts(queue) == ["advert"]


# ── Deterministic, whatever the event loop did ────────────────────────────────


def test_two_of_the_same_rank_keep_the_order_they_arrived_in():
    """Within a rank the tie is broken by arrival and never by object identity or hash
    order, either of which would vary between runs."""
    queue = MetaSpeechQueue()
    queue.add(_annonce("first"), urgency=Urgency.NOTICE)
    queue.add(_annonce("second"), urgency=Urgency.NOTICE)

    assert _texts(queue) == ["first", "second"]


def test_the_same_arrivals_always_produce_the_same_sequence():
    """The property the story exists for: run it twice, get the same audio."""
    def build():
        queue = MetaSpeechQueue()
        for urgency in (Urgency.ADVERT, Urgency.BUSY, Urgency.NOTICE, Urgency.BALANCE):
            queue.add(_annonce(f"{urgency.name}-1"), urgency=urgency)
            queue.add(_annonce(f"{urgency.name}-2"), urgency=urgency)
        return _texts(queue)

    assert build() == build()


def test_identical_utterances_do_not_collapse_into_one():
    """Two identical sentences are two things that happened, and a queue that deduplicated
    them would be arbitrating."""
    queue = MetaSpeechQueue()
    queue.add(_annonce("same"), urgency=Urgency.NOTICE)
    queue.add(_annonce("same"), urgency=Urgency.NOTICE)

    assert _texts(queue) == ["same", "same"]


def test_the_queue_reports_how_much_is_waiting():
    queue = MetaSpeechQueue()
    queue.add(_annonce("a"), urgency=Urgency.BUSY)
    queue.add(_annonce("b"), urgency=Urgency.ADVERT)

    assert queue.waiting == 2


def test_an_empty_queue_drains_to_nothing():
    assert MetaSpeechQueue().drain() == ()


# ── Wired into a Salon ────────────────────────────────────────────────────────

from src.interprete import InterpreteFake, Participant  # noqa: E402
from src.journal import InMemoryJournalStore, SalonLog  # noqa: E402
from src.salon import InMemoryRoomProvisioner, Salon  # noqa: E402

MARIE = Participant(id="marie", language="fr", name="Marie")
HANS = Participant(id="hans", language="de", name="Hans")


async def _translate(text, *, source, target):
    return text


@pytest.fixture
def salon():
    log = SalonLog(salon_id="s", store=InMemoryJournalStore(), translate=_translate)
    return Salon(log=log, rooms=InMemoryRoomProvisioner(), max_message_characters=40)


async def _held_salon(salon):
    """A Salon with Hans part-way through hearing one of Marie's interventions.

    Mid-run is the only state in which any of this matters: it is the one moment several
    utterances can pile up with no slot to come out of.
    """
    await salon.join(MARIE, InterpreteFake(participant=MARIE))
    await salon.join(HANS, InterpreteFake(participant=HANS))
    await salon.ingest(
        MARIE.id,
        "Premiere phrase assez longue pour compter. Deuxieme phrase egalement longue ici. "
        "Troisieme phrase pour faire bonne mesure.",
        language="fr",
    )
    await salon.deliver_upto(HANS.id, salon.log.head - 1)
    return salon


async def test_several_things_held_together_come_out_in_order(salon):
    await _held_salon(salon)

    await salon.announce(HANS.id, Annonce(text="advert", language="de"), urgency=Urgency.ADVERT)
    await salon.announce(HANS.id, Annonce(text="busy", language="de"), urgency=Urgency.BUSY)
    await salon.announce(
        HANS.id, Annonce(text="balance", language="de"), urgency=Urgency.BALANCE
    )
    await salon.deliver(HANS.id)

    said = [line.text for line in salon.interpreter_of(HANS.id).spoken]
    assert [text for text in said if text in {"busy", "balance", "advert"}] == [
        "busy",
        "balance",
        "advert",
    ]


async def test_an_announcement_with_no_urgency_is_an_ordinary_notice(salon):
    """Every existing caller passes no urgency, and none of them should have to."""
    await _held_salon(salon)

    await salon.announce(HANS.id, Annonce(text="advert", language="de"), urgency=Urgency.ADVERT)
    await salon.announce(HANS.id, Annonce(text="arrivee", language="de"))
    await salon.deliver(HANS.id)

    said = [line.text for line in salon.interpreter_of(HANS.id).spoken]
    assert said.index("arrivee") < said.index("advert")


async def test_nothing_held_is_lost_on_the_way_through(salon):
    await _held_salon(salon)

    for urgency in Urgency:
        await salon.announce(
            HANS.id, Annonce(text=urgency.name, language="de"), urgency=urgency
        )
    await salon.deliver(HANS.id)

    said = [line.text for line in salon.interpreter_of(HANS.id).spoken]
    for urgency in Urgency:
        assert urgency.name in said


async def test_the_sequence_is_the_same_every_run(salon):
    """Two runs of the same scenario produce the same audio. The whole point."""
    async def once():
        log = SalonLog(salon_id="s", store=InMemoryJournalStore(), translate=_translate)
        fresh = Salon(log=log, rooms=InMemoryRoomProvisioner(), max_message_characters=40)
        await _held_salon(fresh)
        for urgency in (Urgency.ADVERT, Urgency.BUSY, Urgency.NOTICE, Urgency.BALANCE):
            await fresh.announce(
                HANS.id, Annonce(text=urgency.name, language="de"), urgency=urgency
            )
        await fresh.deliver(HANS.id)
        return [line.text for line in fresh.interpreter_of(HANS.id).spoken]

    assert await once() == await once()


async def test_a_condensation_announcement_stays_with_its_summary(salon):
    """It is not scheduled against any of this. Ordering it would strand "while you were
    listening, three people spoke" next to something else entirely."""
    from src.journal import CHARACTERS_PER_SECOND

    # Distinct words of more than three letters: the stammer rule (Story 6.11) collapses a
    # repeated short one, and the intervention would arrive too small to condense at all.
    words = ("alors", "parce", "quand", "toute", "chose", "avant", "depuis", "encore")
    needed = int(200 * CHARACTERS_PER_SECOND)
    long_text = " ".join(words[i % len(words)] for i in range(needed // 6 + 1))

    log = SalonLog(salon_id="s", store=InMemoryJournalStore(), translate=_translate)
    far_behind = Salon(
        log=log,
        rooms=InMemoryRoomProvisioner(),
        condensation_threshold_seconds=60.0,
        max_message_characters=100_000,
    )
    await far_behind.join(MARIE, InterpreteFake(participant=MARIE))
    await far_behind.join(HANS, InterpreteFake(participant=HANS))
    await far_behind.ingest(MARIE.id, long_text, language="fr")

    await far_behind.deliver(HANS.id)

    kinds = [line.kind for line in far_behind.interpreter_of(HANS.id).spoken]
    # The announcement is immediately followed by the summary it introduces.
    assert kinds[kinds.index("annonce") + 1] == "condense"


async def test_an_introduction_is_not_scheduled_against_any_of_this(salon):
    """It happens as somebody enters the room, before they are in the conversation at all."""
    await salon.join(MARIE, InterpreteFake(participant=MARIE))
    await salon.join(HANS, InterpreteFake(participant=HANS))
    await salon.ingest(MARIE.id, "Bonjour", language="fr")

    await salon.deliver(HANS.id)

    kinds = [line.kind for line in salon.interpreter_of(HANS.id).spoken]
    assert kinds == ["annonce", "tour"]
