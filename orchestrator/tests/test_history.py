"""What a late arrival is given of the conversation they missed.

Three decisions, and they are genuinely separate. The host decides whether somebody gets
the history at all, in the same breath as the invitation. Where that puts their reading
position follows mechanically. And whether what they get is replayed or summarised is
decided by nothing but the volume — a Salon two minutes old has nothing to summarise.

The one that is easy to forget is the last acceptance criterion: everybody already in the
room is told. What they said before this person arrived is about to be said to them, and
nobody should learn that afterwards.
"""
import pytest

from src.interprete import InterpreteFake, Participant
from src.journal import InMemoryJournalStore, SalonLog
from src.salon import (
    DEFAULT_HISTORY_FOR_ARRIVALS,
    HistoryAccess,
    InMemoryRoomProvisioner,
    Salon,
    grants_history,
    history_from_invitation,
)

MARIE = Participant(id="marie", language="fr", name="Marie")
HANS = Participant(id="hans", language="de", name="Hans")
RHYS = Participant(id="rhys", language="cy", name="Rhys")


async def translate(text, *, source, target):
    return f"{text} [{target}]"


def _salon(**kwargs):
    log = SalonLog(salon_id="salon-1", store=InMemoryJournalStore(), translate=translate)
    return Salon(log=log, rooms=InMemoryRoomProvisioner(), **kwargs)


@pytest.fixture
def salon():
    return _salon()


async def _join(salon, participant, **kwargs):
    return await salon.join(participant, InterpreteFake(participant=participant), **kwargs)


def _tours(salon, participant_id):
    return [line for line in salon.interpreter_of(participant_id).spoken if line.kind == "tour"]


def _annonces(salon, participant_id):
    return [line.text for line in salon.interpreter_of(participant_id).spoken if line.kind == "annonce"]


# ── What the host said when they invited ──────────────────────────────────────


def test_the_host_can_grant_the_history_in_the_invitation():
    assert history_from_invitation("invite Marie, avec l'historique") is HistoryAccess.GRANTED


def test_the_host_can_refuse_it_in_the_same_breath():
    assert history_from_invitation("invite Marie, sans l'historique") is HistoryAccess.REFUSED


def test_an_invitation_that_says_nothing_leaves_it_unspecified():
    """Not a refusal. The default decides, and the default is a product decision rather than
    a reading of what the host meant."""
    assert history_from_invitation("invite Marie") is HistoryAccess.UNSPECIFIED


def test_the_refusal_is_recognised_before_the_grant():
    """"sans l'historique" contains "l'historique". Matching the grant first would turn
    every refusal into permission, which is the one error worth designing against."""
    assert history_from_invitation("Sans l'historique s'il te plaît") is HistoryAccess.REFUSED


@pytest.mark.parametrize(
    ("said", "expected"),
    [
        ("invite Hans with the history", HistoryAccess.GRANTED),
        ("invite Hans without the history", HistoryAccess.REFUSED),
        ("invita a Ana con el historial", HistoryAccess.GRANTED),
        ("invita a Ana sin el historial", HistoryAccess.REFUSED),
        ("lade Hans mit Verlauf ein", HistoryAccess.GRANTED),
        ("lade Hans ohne Verlauf ein", HistoryAccess.REFUSED),
    ],
)
def test_the_host_is_understood_in_their_own_language(said, expected):
    """The host speaks whatever they speak. Recognising this only in French would make it a
    French-only feature in a product whose whole point is that it is not."""
    assert history_from_invitation(said) is expected


def test_nothing_at_all_is_unspecified():
    assert history_from_invitation("") is HistoryAccess.UNSPECIFIED
    assert history_from_invitation(None) is HistoryAccess.UNSPECIFIED


def test_the_default_is_to_grant_it():
    """The host has to refuse explicitly. Somebody invited into a conversation is being
    invited into what it has been about."""
    assert DEFAULT_HISTORY_FOR_ARRIVALS is True
    assert grants_history(HistoryAccess.UNSPECIFIED) is True


def test_an_explicit_decision_beats_the_default():
    assert grants_history(HistoryAccess.GRANTED) is True
    assert grants_history(HistoryAccess.REFUSED) is False


# ── Where that puts their reading position ────────────────────────────────────


async def test_granting_the_history_starts_them_at_the_beginning(salon):
    """No mechanism of its own: a position at zero, and the ordinary rules do the rest."""
    await _join(salon, MARIE)
    await salon.ingest(MARIE.id, "un", language="fr")
    await salon.ingest(MARIE.id, "deux", language="fr")

    await _join(salon, HANS, history=HistoryAccess.GRANTED)

    assert len(salon.pending_for(HANS.id)) == 2


async def test_refusing_it_starts_them_at_the_head(salon):
    """They get the introductions and join the conversation live, with no access at all to
    what was said before them."""
    await _join(salon, MARIE)
    await salon.ingest(MARIE.id, "un", language="fr")

    await _join(salon, HANS, history=HistoryAccess.REFUSED)

    assert salon.pending_for(HANS.id) == ()


async def test_saying_nothing_grants_it(salon):
    await _join(salon, MARIE)
    await salon.ingest(MARIE.id, "un", language="fr")

    await _join(salon, HANS)

    assert len(salon.pending_for(HANS.id)) == 1


async def test_arriving_into_a_salon_nobody_has_spoken_in_gets_nothing_either_way(salon):
    """The journal is empty, so there is nothing to grant and nothing to refuse."""
    await _join(salon, MARIE)

    await _join(salon, HANS, history=HistoryAccess.GRANTED)

    assert salon.pending_for(HANS.id) == ()
    assert _tours(salon, HANS.id) == []


# ── Everybody already here is told ────────────────────────────────────────────


async def test_the_others_are_told_when_an_arrival_is_given_the_history(salon):
    """The acceptance criterion that is easy to forget. What they said before this person
    arrived is about to be said to them, and nobody should find that out afterwards."""
    await _join(salon, MARIE)
    await salon.ingest(MARIE.id, "quelque chose", language="fr")

    await _join(salon, HANS, history=HistoryAccess.GRANTED)

    assert len(_annonces(salon, MARIE.id)) == 1


async def test_nobody_is_told_when_the_history_is_refused(salon):
    """There is nothing to disclose: what they said stays where it was."""
    await _join(salon, MARIE)
    await salon.ingest(MARIE.id, "quelque chose", language="fr")

    await _join(salon, HANS, history=HistoryAccess.REFUSED)

    assert _annonces(salon, MARIE.id) == []


async def test_nobody_is_told_when_there_is_no_history_to_give(salon):
    """Granting access to an empty journal discloses nothing, and saying so would worry
    people about a disclosure that did not happen."""
    await _join(salon, MARIE)

    await _join(salon, HANS, history=HistoryAccess.GRANTED)

    assert _annonces(salon, MARIE.id) == []


async def test_the_notice_is_in_each_listeners_own_language(salon):
    await _join(salon, MARIE)
    await _join(salon, RHYS)
    await salon.ingest(MARIE.id, "quelque chose", language="fr")

    await _join(salon, HANS, history=HistoryAccess.GRANTED)

    assert [
        line.language
        for line in salon.interpreter_of(RHYS.id).spoken
        if line.kind == "annonce"
    ][-1] == "cy"


async def test_the_arrival_is_not_told_about_themselves(salon):
    await _join(salon, MARIE)
    await salon.ingest(MARIE.id, "quelque chose", language="fr")

    await _join(salon, HANS, history=HistoryAccess.GRANTED)

    # Their own announcement is the introduction of who is here, not a disclosure notice.
    assert len(_annonces(salon, HANS.id)) == 1


# ── Replayed, or condensed ────────────────────────────────────────────────────


async def test_a_young_salon_is_replayed_message_by_message(salon):
    """Nothing to summarise. Two minutes of conversation is not a backlog."""
    await _join(salon, MARIE)
    for text in ("un", "deux", "trois"):
        await salon.ingest(MARIE.id, text, language="fr", duration_seconds=1.0)

    await _join(salon, HANS, history=HistoryAccess.GRANTED)
    await salon.deliver(HANS.id)

    assert [line.text for line in _tours(salon, HANS.id)] == ["un", "deux", "trois"]


async def test_a_long_backlog_is_condensed_instead(salon):
    """Above the threshold the interval is said in substance. Replaying twenty minutes to
    somebody who has just arrived would leave them twenty minutes behind for good."""
    tight = _salon(condensation_threshold_seconds=10.0)
    await tight.join(MARIE, InterpreteFake(participant=MARIE))
    for text in ("un", "deux", "trois"):
        await tight.ingest(MARIE.id, text, language="fr", duration_seconds=30.0)

    await tight.join(
        HANS, InterpreteFake(participant=HANS), history=HistoryAccess.GRANTED
    )
    await tight.deliver(HANS.id)

    spoken = tight.interpreter_of(HANS.id).spoken
    assert [line.kind for line in spoken if line.kind in ("tour", "condense")] == ["condense"]


async def test_a_condensation_covers_the_whole_backlog(salon):
    tight = _salon(condensation_threshold_seconds=10.0)
    await tight.join(MARIE, InterpreteFake(participant=MARIE))
    for text in ("un", "deux", "trois"):
        await tight.ingest(MARIE.id, text, language="fr", duration_seconds=30.0)

    await tight.join(
        HANS, InterpreteFake(participant=HANS), history=HistoryAccess.GRANTED
    )
    await tight.deliver(HANS.id)

    (line,) = [entry for entry in tight.interpreter_of(HANS.id).spoken if entry.kind == "condense"]
    assert [tour.text for tour in line.covers] == ["un", "deux", "trois"]
    assert tight.pending_for(HANS.id) == ()


async def test_what_arrives_during_the_catch_up_is_caught_up_the_same_way(salon):
    """No special case. The next delivery weighs the same threshold against whatever has
    accumulated since, and answers the same question again."""
    tight = _salon(condensation_threshold_seconds=10.0)
    await tight.join(MARIE, InterpreteFake(participant=MARIE))
    for text in ("un", "deux"):
        await tight.ingest(MARIE.id, text, language="fr", duration_seconds=30.0)

    await tight.join(
        HANS, InterpreteFake(participant=HANS), history=HistoryAccess.GRANTED
    )
    await tight.deliver(HANS.id)
    await tight.ingest(MARIE.id, "après", language="fr", duration_seconds=1.0)
    await tight.deliver(HANS.id)

    kinds = [line.kind for line in tight.interpreter_of(HANS.id).spoken if line.kind != "annonce"]
    assert kinds == ["condense", "tour"]


async def test_somebody_at_the_head_is_never_condensed_to(salon):
    """Condensation is about a backlog. Somebody keeping up has none, whatever the
    threshold is set to."""
    tight = _salon(condensation_threshold_seconds=0.5)
    await tight.join(MARIE, InterpreteFake(participant=MARIE))
    await tight.join(HANS, InterpreteFake(participant=HANS))

    await tight.ingest(MARIE.id, "un", language="fr", duration_seconds=0.1)
    await tight.deliver_all()

    assert [line.kind for line in _tours(tight, HANS.id)] == ["tour"]


async def test_a_condensation_that_fails_leaves_the_backlog_where_it_was(salon):
    """Their adapter has told them out loud (NFR3). The position does not move, so what
    they missed is still theirs to catch up on rather than silently skipped."""
    tight = _salon(condensation_threshold_seconds=10.0)
    await tight.join(MARIE, InterpreteFake(participant=MARIE))
    for text in ("un", "deux"):
        await tight.ingest(MARIE.id, text, language="fr", duration_seconds=30.0)
    await tight.join(HANS, InterpreteFake(participant=HANS), history=HistoryAccess.GRANTED)

    tight.interpreter_of(HANS.id).fail_with = ConnectionError("model gone")
    await tight.deliver(HANS.id)

    assert len(tight.pending_for(HANS.id)) == 2
    assert tight.interpreter_of(HANS.id).spoken == []


async def test_a_recovered_interpreter_condenses_the_backlog_it_still_has(salon):
    tight = _salon(condensation_threshold_seconds=10.0)
    await tight.join(MARIE, InterpreteFake(participant=MARIE))
    for text in ("un", "deux"):
        await tight.ingest(MARIE.id, text, language="fr", duration_seconds=30.0)
    await tight.join(HANS, InterpreteFake(participant=HANS), history=HistoryAccess.GRANTED)
    hans = tight.interpreter_of(HANS.id)

    hans.fail_with = ConnectionError("model gone")
    await tight.deliver(HANS.id)
    hans.fail_with = None
    await tight.deliver(HANS.id)

    # The arrival announcement of Story 6.9 came first; what matters here is that the
    # backlog was condensed once and not replayed.
    assert [line.kind for line in hans.spoken if line.kind != "annonce"] == ["condense"]
    assert tight.pending_for(HANS.id) == ()


async def test_a_condensation_that_fails_leaves_the_backlog_where_it_was(salon):
    """Their adapter has told them out loud (NFR3). The position must not move past a
    summary nobody heard — losing twenty minutes silently is worse than hearing it late."""
    tight = _salon(condensation_threshold_seconds=10.0)
    await tight.join(MARIE, InterpreteFake(participant=MARIE))
    for text in ("un", "deux"):
        await tight.ingest(MARIE.id, text, language="fr", duration_seconds=30.0)

    await tight.join(HANS, InterpreteFake(participant=HANS), history=HistoryAccess.GRANTED)
    tight.interpreter_of(HANS.id).fail_with = ConnectionError("model gone")
    await tight.deliver(HANS.id)

    assert len(tight.pending_for(HANS.id)) == 2
