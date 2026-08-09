"""Whether somebody's whereabouts may be used to choose their advertising (FR50).

The storage side was already careful before this story: `salon_events.plus_code` holds a
six-digit Open Location Code cell — about five and a half kilometres — encoded at ingestion,
so precise coordinates never reach the disk, and there is deliberately no IP fallback. What
was missing is the *question*: a recorded decision, and the machinery to honour it.

Three states, not two. **Never asked** is not the same as **refused**. Somebody who has not
seen the screen has made no decision, and reading that silence either way puts words in their
mouth — one way by targeting them, the other by recording a refusal they never gave. So the
column is nullable and the absence means exactly what it looks like.

Refusing costs nothing but the targeting. They keep the whole product and still hear
advertising, chosen generically instead of locally: a refusal that degraded the service would
make the consent a purchase, and a purchased consent is not consent.

Withdrawal is immediate. Not at the next Salon, not once a cache expires — a permission that
outlives its revocation by even a little was never really revocable, and the thing that stops
at once is the *recording*, not merely the use.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum

# Asked once, on one screen, naming the purpose. A permission granted for an unstated purpose
# is one somebody can reasonably say they did not understand.
CONSENT_QUESTION = (
    "May Vocaliz use your approximate location — an area of about five kilometres, never "
    "your exact position — to choose which advertisements you hear? You can change this at "
    "any time, and saying no changes nothing else."
)

# Six digits of Open Location Code, about 5.5 km. Longer would be a point, and a point invites
# being treated as one — the reasoning the inherited model already wrote down.
CELL_DIGITS = 6


class AdKind(Enum):
    """What kind of advertising somebody hears. Never *whether* they hear any."""

    TARGETED = "targeted"
    GENERIC = "generic"


def should_ask(person) -> bool:
    """Whether the consent screen still has a question to put.

    Once somebody has answered — either way — it is not asked again. Re-asking a refusal
    until it becomes a yes is how a choice turns into an attrition exercise.
    """
    return person.location_consent is None


def record_location_consent(person, *, granted: bool, now: datetime) -> None:
    """Write down what they said, and when.

    A refusal is recorded as deliberately as a consent: it is what stops the question being
    asked again next week.
    """
    person.location_consent = granted
    person.location_consent_at = now


def withdraw_location_consent(person, *, now: datetime) -> None:
    """Take it back, effective immediately.

    Harmless if they never consented — the outcome is the same either way, and refusing to
    process a withdrawal because there was nothing to withdraw would be a strange thing to
    explain to somebody trying to opt out.
    """
    record_location_consent(person, granted=False, now=now)


def targeting_allowed(person) -> bool:
    """Whether advertising may be chosen from where this person is.

    Only an explicit yes counts. Never-asked and refused both come out false, for the same
    reason: neither is permission.
    """
    return person.location_consent is True


def ad_kind_for(person) -> AdKind:
    """What they hear. Everybody in an advertising tier hears something."""
    return AdKind.TARGETED if targeting_allowed(person) else AdKind.GENERIC


def location_cell_for(person, *, cell: str) -> str:
    """The cell to store against an event, or the empty string.

    Empty without consent, which is what the inherited schema already expects. This is where
    withdrawal actually bites: after it, nothing further is written down about where somebody
    is, rather than merely being ignored at reading time.

    Truncated to `CELL_DIGITS` even when consent was given, so a caller handing over a finer
    code cannot accidentally store a point.
    """
    if not targeting_allowed(person):
        return ""
    return cell[:CELL_DIGITS]
