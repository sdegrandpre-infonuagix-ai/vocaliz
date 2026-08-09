"""Everything settled before a telephone rings (Story 10.5 / FR5, FR56).

The dialling itself does not exist here and cannot: there is no SIP trunk and no dispatch rule,
which the front-desk endpoint already says out loud. What this module holds is the part with
the decisions in it — which number, at whose word, at which tier, at whose expense, and whether
there is even a seat — so that when a trunk arrives, none of that has to be invented under it.

**The confirmation is the careful part.** Recognising a number from speech is guesswork, and a
wrong guess here does not produce a failed action: it produces a telephone ringing in a
stranger's house, charged to a host who never asked for it. Nothing else in Vocaliz reaches out
and touches somebody who was not already involved. So the number is read back and a plain yes
is required — an unclear answer asks again rather than counting either way.

**A telephone participant is always at the host's charge.** They chose nothing, signed up for
nothing, and must therefore spend nothing — not their credit, not their free minutes. The same
reasoning makes the payment check independent of FR42's "the host pays all": that option is
about the *other* participants, and it being off says nothing about somebody the host
personally caused to be telephoned.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from src.credit import TIER_RATES_CENTS_PER_HOUR, Tier

SECONDS_PER_HOUR = 3600

# What the telephone adds on top of the tier: the SIP minutes and the PSTN termination, which
# do not get cheaper because the interpreter got better.
TELEPHONE_SUPPLEMENT_CENTS_PER_HOUR = 100

# Base is not offered by telephone. The host pays the supplement and the interpreter either
# way, so the cheapest tier saves them nothing while costing the person on the line a worse
# conversation — the one participant who had no say in any of it.
TELEPHONE_TIERS: tuple[Tier, ...] = (Tier.MODE_A, Tier.MODE_B, Tier.MODE_C)

# Where a call lands when the host names no tier. Mode B rather than the cheapest on offer:
# somebody telephoned into a conversation they did not choose should not also be advertised at.
DEFAULT_TELEPHONE_TIER = Tier.MODE_B

# Shorter than this is a year, a street number or an amount — not a telephone number. Ten is
# the shortest that dials anywhere in the NANP, and dialling four digits still dials something.
_SHORTEST_NUMBER = 10
_LONGEST_NUMBER = 15  # E.164's own limit.

_YES = ("oui", "yes", "ouais", "c'est ça", "c'est ca", "exact", "exactement", "correct", "ok")
_NO = ("non", "no", "pas du tout", "faux", "incorrect", "nope")


def recognise_number(spoken: str) -> str | None:
    """The telephone number in a spoken invitation, in E.164, or `None`.

    `None` is an ordinary outcome and the reason this returns rather than guesses: the agent
    has to be able to say it did not catch a number. Anything else would dial on a maybe.
    """
    digits = re.sub(r"[^\d+]", "", spoken or "")
    keeps_country = digits.startswith("+")
    digits = re.sub(r"\D", "", digits)

    if not (_SHORTEST_NUMBER <= len(digits) <= _LONGEST_NUMBER):
        return None
    if keeps_country:
        return f"+{digits}"
    # No country code spoken. Assumed North American, which is where the front desk and the
    # only numbers anybody has dialled here live. Worth writing down rather than leaving
    # implicit: it is wrong the first time somebody invites a French number without saying
    # "plus thirty-three", and the confirmation read-back is what catches that.
    return f"+1{digits}" if len(digits) == 10 else f"+{digits}"


def confirmation_prompt(number: str) -> str:
    """What the agent says back before anything is dialled.

    In small groups, because that is how somebody checks a number against the one in their
    head. Eleven digits in a single run cannot be followed, and a host who cannot follow it
    will say yes to be polite.
    """
    return f"I heard {_grouped(number)}. Shall I call that number?"


def _grouped(number: str) -> str:
    """`+15145550123` as `+1 514 555 0123`."""
    country, rest = (number[:2], number[2:]) if number.startswith("+1") else (number[:3], number[3:])
    if not number.startswith("+"):
        country, rest = "", number
    pieces = [rest[i:i + 3] for i in range(0, max(0, len(rest) - 4), 3)]
    pieces.append(rest[sum(len(p) for p in pieces):])
    return " ".join(filter(None, [country, *pieces]))


def heard_confirmation(answer: str) -> bool | None:
    """Yes, no, or neither.

    `None` means ask again, and it is deliberately not `False`. Treating an unclear answer as
    a refusal makes the agent give up on a host who coughed; treating it as consent dials a
    stranger. Neither is available, so the only honest third answer is to ask.
    """
    said = (answer or "").strip().lower()
    if not said:
        return None
    if any(re.search(rf"\b{re.escape(word)}\b", said) for word in _NO):
        return False
    if any(re.search(rf"\b{re.escape(word)}\b", said) for word in _YES):
        return True
    return None


def tier_from(spoken: str) -> Tier:
    """The tier named in the invitation, or the default.

    A tier that is not on offer by telephone — Base — falls to the **default** rather than to
    the floor. The host asked for something not available here, and what they get is the
    offer, not the cheapest thing that exists elsewhere.
    """
    said = (spoken or "").lower()
    for tier in TELEPHONE_TIERS:
        if tier.value.lower() in said:
            return tier
    return DEFAULT_TELEPHONE_TIER


@dataclass(frozen=True)
class Refusal:
    """Why no call is being placed, in words the host hears.

    Spoken rather than displayed: the host is in the middle of a conversation and not looking
    at a screen (NFR3). A call that simply never happens is the failure this exists to avoid.
    """

    spoken: str


def may_dial(
    *,
    payment_method: bool,
    present: int,
    cap: int,
    host_pays_all: bool = False,
) -> Refusal | None:
    """Whether a number may be called at all. `None` means go ahead.

    The seat is checked before the payment method, and the order is the point: a host whose
    Salon is full does not need to be told to add a card for a call that could not happen
    either way. One refusal, and it is the one actually in the way.

    `host_pays_all` is accepted and deliberately not consulted for the payment check. FR42 is
    about the other participants; a telephone participant is at the host's charge whatever
    that option says, so the card is required either way.
    """
    if present >= cap:
        return Refusal(
            spoken=(
                f"This Salon is full — it was opened for {cap} "
                f"{'person' if cap == 1 else 'people'}, so I cannot call anybody else."
            )
        )
    if not payment_method:
        return Refusal(
            spoken=(
                "I need a payment method on your account before I can call anybody. "
                "A telephone guest is always charged to you, whoever else is paying."
            )
        )
    return None


def cost_cents(tier: Tier, seconds: int) -> int:
    """What a telephone participant costs the host, prorated to the second.

    The tier's own rate plus the supplement, as one number: the interpreter, the SIP minutes
    and the PSTN termination are all the host's, and splitting them across two figures would
    invite one of them to be forgotten.

    Rounded down once, at the end. Rounding each half separately loses a cent twice on a
    figure that is already small, and a bill should never exceed the thing it is for.
    """
    if seconds <= 0:
        return 0
    per_hour = TIER_RATES_CENTS_PER_HOUR[tier] + TELEPHONE_SUPPLEMENT_CENTS_PER_HOUR
    return per_hour * seconds // SECONDS_PER_HOUR


def spends_own_quota() -> bool:
    """Whether a telephone participant's own free allowance is touched. It is not.

    They decided nothing, so they spend nothing. Somebody whose telephone rang did not choose
    a tier, did not sign up, and did not agree to a price — charging their ten free minutes
    for a conversation they were called into would make the one participant with no say the
    one paying for everybody's convenience.

    A function rather than a comment, because a rule that lives only in prose is one the next
    person to touch the metering will not know about.
    """
    return False


def charged_to(*, host_id, participant_id):
    """Whose account a telephone participant's cost lands on. Always the host's.

    All of it — the interpreter, the SIP minutes, the PSTN termination and the supplement.
    Splitting the bill would mean asking somebody to hold an account they never made, and it
    is the host who caused the telephone to ring.

    `participant_id` is accepted and deliberately unused: a signature that did not take it
    would make the rule look like an oversight rather than a decision, and the first person
    to add per-participant billing would not find this.
    """
    return host_id
