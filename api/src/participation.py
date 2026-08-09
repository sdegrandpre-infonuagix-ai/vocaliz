"""Settling one participant's options as they join (FR35 / FR42).

The whole point of the epic is that a Salon does not have a mode — the people in it do. Three
participants hold three independent sets of choices and nothing about one reaches another.
The host picking Mode C obliges nobody.

The single exception is the host offering to pay, and it is shaped by two rules that pull in
the same direction. The guest is not *asked* to choose, because asking somebody to pick a
budget they are not spending is a question with no meaning. And the override only ever moves
**upward**: one able to lower an existing choice would be a host quietly downgrading a guest,
which is exactly what this epic exists to make impossible.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from src.credit import Tier, balance
from src.models.participant_options import ParticipantOptions
from src.tiers import covers_minutes

# Where a guest lands when the host is paying. Mode B rather than Mode A, and the difference
# is not the price: somebody whose participation is a gift should not also be the product
# being sold to.
HOST_PAYS_TIER = Tier.MODE_B

# Cheapest first, which is what makes "only upward" a comparison rather than a special case.
_ORDER: tuple[Tier, ...] = (Tier.BASE, Tier.MODE_A, Tier.MODE_B, Tier.MODE_C)


def _at_least(chosen: Tier, floor: Tier) -> Tier:
    """The higher of the two. How "always upward" is enforced, in one place."""
    return chosen if _ORDER.index(chosen) >= _ORDER.index(floor) else floor


@dataclass(frozen=True)
class JoinOptions:
    """What was settled, and what the join screen should therefore do."""

    salon_id: uuid.UUID
    user_id: uuid.UUID
    tier: str
    video: bool
    top_up_cents: int | None
    # `None` when there is no credit to speak of — the rate stands alone rather than
    # advertising a duration of zero.
    covered_by_credit_minutes: int | None
    # Whether the screen asks for money now. False when the host is paying, when credit
    # covers it, or when they have already asked to top up.
    payment_required: bool
    # Whether the tier choice is presented at all.
    choice_offered: bool


def join_options(
    db: Session,
    *,
    salon_id: uuid.UUID,
    user_id: uuid.UUID,
    chosen_tier: Tier | None = None,
    video: bool = False,
    top_up_cents: int | None = None,
    host_pays: bool = False,
    now: datetime | None = None,
) -> JoinOptions:
    """Settle one participant's options and record them.

    Rejoining replaces rather than duplicates: a second row for the same pair would leave two
    answers to "what did they choose?", and nothing to say which is current.
    """
    tier = chosen_tier or Tier.BASE
    if host_pays:
        tier = _at_least(tier, HOST_PAYS_TIER)

    remaining = max(0, balance(db, user_id).gifted_cents)
    minutes = covers_minutes(remaining, tier) or None

    db.flush()
    row = (
        db.query(ParticipantOptions)
        .filter(
            ParticipantOptions.salon_id == salon_id,
            ParticipantOptions.user_id == user_id,
        )
        .one_or_none()
    )
    if row is None:
        row = ParticipantOptions(salon_id=salon_id, user_id=user_id, tier=tier.value)
        db.add(row)
    row.tier = tier.value
    row.video = video
    row.top_up_cents = top_up_cents
    if now is not None:
        row.chosen_at = now

    return JoinOptions(
        salon_id=salon_id,
        user_id=user_id,
        tier=tier.value,
        video=video,
        top_up_cents=top_up_cents,
        covered_by_credit_minutes=minutes,
        # The welcome credit is applied before anything is asked for: requesting payment
        # while five unspent dollars of theirs sit there is asking for money not yet needed.
        payment_required=not (host_pays or minutes or top_up_cents),
        choice_offered=not host_pays,
    )
