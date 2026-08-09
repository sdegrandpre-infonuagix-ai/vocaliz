"""Warning somebody their balance is running out, and closing the Salon when it does (FR55).

A host is warned earlier than a guest, and the reason is courtesy rather than status: other
people's conversation depends on their balance, so they need longer to decide. Their warning
names the consequence — the Salon closes for everybody — because a decision made without
knowing that is not really a decision.

And it is said in their room alone. A host's financial situation never becomes audible to the
people they are hosting: the guests' fifteen-second notice states the fact without the cause,
naming neither the host nor their balance.

The closing sequence itself is free. That is not an inconsistency with "no consumption
without coverage" but the one bounded exemption to it — announcing the end and asking the
satisfaction question are the only things a zero balance may buy, and the moment they are
done the room closes. During them nothing anybody says is ingested: the exemption covers the
interpreter's voice, never a resumption of the conversation.
"""
import pytest

from src.coverage import ALERT_COVERAGE_SECONDS
from src.ending import (
    FINAL_REMINDER_SECONDS,
    GUEST_NOTICE_SECONDS,
    HOST_ALERT_COVERAGE_SECONDS,
    ClosingSequence,
    alert_for,
    guest_notice_text,
    host_alert_text,
    participant_alert_text,
)


# ── A host is warned earlier ──────────────────────────────────────────────────


def test_a_guest_is_warned_at_three_minutes():
    assert ALERT_COVERAGE_SECONDS == 180


def test_a_host_is_warned_at_five():
    """Earlier, out of courtesy to the people they are hosting: their conversation depends on
    this balance, so the host needs longer to decide what to do about it."""
    assert HOST_ALERT_COVERAGE_SECONDS == 300
    assert HOST_ALERT_COVERAGE_SECONDS > ALERT_COVERAGE_SECONDS


def test_a_host_with_four_minutes_left_is_warned_and_a_guest_is_not():
    assert alert_for(remaining_seconds=240, is_host=True).due is True
    assert alert_for(remaining_seconds=240, is_host=False).due is False


def test_a_comfortable_balance_warns_nobody():
    assert alert_for(remaining_seconds=3600, is_host=True).due is False


# ── Said once, then once more near the end ────────────────────────────────────


def test_the_warning_is_not_repeated_on_every_tick():
    """A message repeated twelve times a minute is a message somebody learns to ignore."""
    assert alert_for(remaining_seconds=150, is_host=False, already_alerted=True).due is False


def test_a_last_reminder_comes_at_sixty_seconds():
    """One more, and only one. The first warning may have been three minutes ago, and by now
    somebody may reasonably have forgotten it."""
    assert FINAL_REMINDER_SECONDS == 60

    alert = alert_for(remaining_seconds=55, is_host=False, already_alerted=True)

    assert alert.due is True
    assert alert.final is True


def test_the_last_reminder_is_itself_given_only_once():
    alert = alert_for(
        remaining_seconds=55, is_host=False, already_alerted=True, final_given=True
    )

    assert alert.due is False


def test_the_first_warning_is_not_marked_final():
    assert alert_for(remaining_seconds=150, is_host=False).final is False


# ── What each of them says ────────────────────────────────────────────────────


def test_a_guest_is_told_how_long_is_left_and_offered_a_top_up():
    text = participant_alert_text(remaining_seconds=150)

    assert "2" in text or "150" in text
    assert "top up" in text.lower()


def test_a_host_is_told_what_happens_to_everybody_else():
    """The consequence, explicitly. A host deciding whether to top up is deciding on behalf
    of the people in the room, and cannot do that without being told so."""
    text = host_alert_text(remaining_seconds=240, guests=3)

    assert "close" in text.lower()
    assert "3" in text


def test_a_hosts_warning_is_not_the_same_text_as_a_guests():
    assert host_alert_text(remaining_seconds=240, guests=2) != participant_alert_text(
        remaining_seconds=240
    )


def test_neither_warning_reproaches_anybody():
    """Running out of money is not a fault, and a notice that reads as one makes somebody
    less likely to fix it."""
    for text in (participant_alert_text(remaining_seconds=100), host_alert_text(
        remaining_seconds=100, guests=1
    )):
        for scolding in ("should have", "failed", "warning:", "you did not"):
            assert scolding not in text.lower()


# ── The guests' notice says the fact, not the cause ───────────────────────────


def test_guests_are_given_fifteen_seconds():
    assert GUEST_NOTICE_SECONDS == 15


def test_the_notice_states_the_fact():
    text = guest_notice_text()

    assert "15" in text or "fifteen" in text.lower()
    assert "clos" in text.lower()


def test_the_notice_never_names_the_host_or_their_money():
    """A host's financial situation does not become audible to the people they are hosting.
    The guests are told the Salon is closing, and nothing about why."""
    text = guest_notice_text().lower()

    for leak in ("balance", "host", "credit", "paid", "money", "budget"):
        assert leak not in text


def test_the_notice_gives_them_time_to_say_goodbye():
    """Which is the whole reason for a notice rather than a sudden disconnection."""
    assert GUEST_NOTICE_SECONDS > 0


# ── The closing sequence is free, and bounded ─────────────────────────────────


def test_the_closing_sequence_is_never_billed():
    """The one exemption to "no consumption without coverage". Announcing the end and asking
    the satisfaction question are what a zero balance may still buy."""
    closing = ClosingSequence()

    assert closing.billable is False


def test_the_satisfaction_question_is_asked_as_it_is_for_any_other_ending():
    """Ending for want of money is still an ending, and treating it differently would single
    somebody out for having run out."""
    assert ClosingSequence().asks_satisfaction is True


def test_nothing_said_during_the_closing_is_ingested():
    """The exemption covers the interpreter's voice, never a resumption of the conversation.
    Otherwise a free closing sequence would be a free Salon."""
    closing = ClosingSequence()

    assert closing.accepts_speech is False


def test_the_exemption_ends_with_the_sequence():
    closing = ClosingSequence().finished()

    assert closing.room_open is False
    assert closing.accepts_speech is False


def test_the_room_is_open_for_the_duration_of_the_sequence():
    assert ClosingSequence().room_open is True


# ── When the host is the one who runs out ─────────────────────────────────────


def test_a_hosts_exhaustion_closes_the_salon_for_everybody():
    closing = ClosingSequence(host_exhausted=True)

    assert closing.closes_whole_salon is True


def test_a_guests_exhaustion_ends_only_their_own(db=None):
    closing = ClosingSequence(host_exhausted=False)

    assert closing.closes_whole_salon is False


def test_everybody_is_told_by_their_own_interpreter():
    """Each in their own language, in their own room — the same path everything else takes."""
    closing = ClosingSequence(host_exhausted=True)

    assert closing.notifies_each_participant is True


def test_others_stop_being_billed_the_moment_the_salon_closes():
    """Somebody paying for their own experience loses nothing because the host ran out. They
    stop being charged at that instant and keep every cent of their balance."""
    closing = ClosingSequence(host_exhausted=True)

    assert closing.stops_billing_others is True


def test_there_is_no_free_tier_to_fall_back_to():
    """Every tier is paid, so an exhausted balance has nowhere to land. Ending is not a
    choice among options — it is the only one there is."""
    from src.credit import TIER_RATES_CENTS_PER_HOUR

    assert all(rate > 0 for rate in TIER_RATES_CENTS_PER_HOUR.values())


# ── Topping up in time ────────────────────────────────────────────────────────


def test_a_top_up_before_exhaustion_interrupts_nothing():
    """They never left their mode, so there is nothing to announce and nothing to restore."""
    alert = alert_for(remaining_seconds=3600, is_host=False, already_alerted=True)

    assert alert.due is False


def test_the_alert_is_rearmed_once_the_balance_recovers():
    """So the next time it runs low they are warned again, rather than the first warning
    having spent the only one they get."""
    assert alert_for(remaining_seconds=3600, is_host=False).rearm is True


def test_a_balance_still_low_does_not_rearm():
    assert alert_for(remaining_seconds=100, is_host=False).rearm is False


def test_a_negative_remaining_time_is_refused_rather_than_treated_as_plenty():
    with pytest.raises(ValueError):
        alert_for(remaining_seconds=-1, is_host=False)
