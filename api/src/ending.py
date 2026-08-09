"""Warning that a balance is running out, and closing the Salon when it does (FR55).

A host is warned earlier than a guest, and the reason is courtesy rather than rank: other
people's conversation depends on their balance, so they need longer to decide. Their warning
names the consequence — the Salon closes for everybody — because a decision taken without
knowing that is not really a decision.

It is said in their room alone. A host's financial situation never becomes audible to the
people they are hosting, so the guests' fifteen-second notice states the fact without the
cause, naming neither the host nor their balance.

The closing sequence is free, and that is not a hole in "no consumption without coverage" but
its one bounded exemption: announcing the end and asking the satisfaction question are the
only things a zero balance may still buy. During them nothing anybody says is ingested — the
exemption covers the interpreter's voice, never a resumption of the conversation, because
otherwise a free closing sequence would be a free Salon.
"""
from __future__ import annotations

from dataclasses import dataclass

from src.coverage import ALERT_COVERAGE_SECONDS

# A host is warned at five minutes rather than three. The extra two are for the decision they
# have to make on behalf of everybody else in the room.
HOST_ALERT_COVERAGE_SECONDS = 300

# One more reminder near the end. The first warning may have been minutes ago, and by now
# somebody may quite reasonably have forgotten it.
FINAL_REMINDER_SECONDS = 60

# How long guests get before the room closes — enough to say goodbye, which is the whole
# reason for a notice rather than a sudden disconnection.
GUEST_NOTICE_SECONDS = 15


@dataclass(frozen=True)
class Alert:
    """Whether to say something now, and whether this is the last time."""

    due: bool
    final: bool
    # True once the balance is comfortable again, so the next fall triggers a fresh warning
    # rather than the first one having spent the only warning somebody gets.
    rearm: bool


def alert_for(
    *,
    remaining_seconds: int,
    is_host: bool,
    already_alerted: bool = False,
    final_given: bool = False,
) -> Alert:
    """Decide whether this payer should be warned right now."""
    if remaining_seconds < 0:
        raise ValueError(
            f"remaining_seconds is {remaining_seconds}: a balance cannot cover a negative "
            "duration, and treating it as plenty would silence the alert exactly when it "
            "matters most."
        )

    threshold = HOST_ALERT_COVERAGE_SECONDS if is_host else ALERT_COVERAGE_SECONDS
    low = remaining_seconds < threshold

    if not low:
        return Alert(due=False, final=False, rearm=True)

    if remaining_seconds < FINAL_REMINDER_SECONDS and not final_given:
        return Alert(due=True, final=True, rearm=False)

    return Alert(due=not already_alerted, final=False, rearm=False)


def _minutes(seconds: int) -> str:
    return f"{seconds // 60} min {seconds % 60:02d} s"


def participant_alert_text(*, remaining_seconds: int) -> str:
    """What a guest is told: how long is left, and the offer to top up.

    No reproach anywhere in it. Running out of money is not a fault, and a notice that reads
    as one makes somebody less likely to do anything about it.
    """
    return (
        f"You have about {_minutes(remaining_seconds)} of conversation left. "
        "I can top up your balance now if you like."
    )


def host_alert_text(*, remaining_seconds: int, guests: int) -> str:
    """What a host is told: the same, plus what happens to everybody else.

    The consequence is stated explicitly. A host deciding whether to top up is deciding on
    behalf of the people in the room, and cannot do that without being told so.
    """
    return (
        f"You have about {_minutes(remaining_seconds)} left. When it runs out the Salon will "
        f"close for you and for your {guests} guest(s). I can top up your balance now."
    )


def guest_notice_text() -> str:
    """What guests hear before a Salon closes: the fact, and nothing about the cause.

    Never the host, never a balance. Somebody's financial situation does not become audible
    to the people they invited.
    """
    return f"The Salon will close in {GUEST_NOTICE_SECONDS} seconds."


@dataclass(frozen=True)
class ClosingSequence:
    """The end of a Salon for want of balance — free, bounded, and not a conversation."""

    host_exhausted: bool = False
    over: bool = False

    @property
    def billable(self) -> bool:
        """Never. The one exemption to "no consumption without coverage"."""
        return False

    @property
    def asks_satisfaction(self) -> bool:
        """FR26, as for any other ending. Treating this one differently would single
        somebody out for having run out of money."""
        return True

    @property
    def accepts_speech(self) -> bool:
        """No. The exemption covers the interpreter's voice, never a resumption of the
        conversation — otherwise a free closing sequence would be a free Salon."""
        return False

    @property
    def room_open(self) -> bool:
        """Open for the duration of the sequence and not one moment longer."""
        return not self.over

    @property
    def closes_whole_salon(self) -> bool:
        """Only when it is the host who ran out. A guest's exhaustion ends their own Salon."""
        return self.host_exhausted

    @property
    def notifies_each_participant(self) -> bool:
        """Each by their own interpreter, in their own language — the path everything else
        takes."""
        return self.host_exhausted

    @property
    def stops_billing_others(self) -> bool:
        """The instant the Salon closes. Somebody paying for their own experience loses
        nothing because the host ran out, and keeps every cent of their balance."""
        return self.host_exhausted

    def finished(self) -> ClosingSequence:
        return ClosingSequence(host_exhausted=self.host_exhausted, over=True)
