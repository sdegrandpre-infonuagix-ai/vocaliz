"""The four tiers as they are offered on screen, and what a credit buys in each (FR69).

Two things this exists to get right, and both are about what somebody can work out from the
screen in front of them.

Each tier adds exactly **one** thing to the one below: a natural voice, then the absence of
advertising, then a premium model. A price gap corresponding to two changes at once is a gap
nobody can evaluate — they cannot tell which half they are paying for, so they cannot tell
whether it is worth it. `differences_from` is not a convenience here; it is the invariant,
and a test walks every neighbouring pair to hold it.

And a rate per hour is not what somebody holding credit wants to know. "7.50 an hour" and
"your credit covers 40 minutes here" are the same fact, and only the second answers the
question being asked. It is always computed on what is *left*: a screen still quoting the
original five dollars after half of them are gone is quoting a number that stopped being
true.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session

from src.credit import TIER_RATES_CENTS_PER_HOUR, Tier, balance

# The three the host configures. Base is the floor rather than a fourth option: it is what
# applies when nothing is chosen, and offering it as a choice beside the others would make
# "cheapest" look like a decision somebody has to defend.
HOST_CONFIGURABLE_TIERS: tuple[Tier, ...] = (Tier.MODE_A, Tier.MODE_B, Tier.MODE_C)

# Whatever the context, in every tier. A capability that appears and disappears depending on
# circumstances is one nobody learns to rely on, and the interpretation model is the product.
SPEECH_TO_SPEECH_ALWAYS_OFFERED = True


def covers_minutes(cents: int, tier: Tier) -> int:
    """How many whole minutes `cents` buys at this tier's rate.

    Rounded **down**. A few seconds shown as "1 min" promises something the money does not
    actually buy, and the person finds out at the moment it runs out.
    """
    if cents <= 0:
        return 0
    return int(cents / TIER_RATES_CENTS_PER_HOUR[tier] * 60)


@dataclass(frozen=True)
class TierOffer:
    """One tier as it appears on the creation screen."""

    tier: Tier
    cents_per_hour: int
    natural_voice: bool
    advertising: bool
    premium_voice: bool
    # `None` when there is no credit to speak of, and the rate stands on its own. Not zero:
    # "your credit covers 0 minutes" is a sentence that advertises a disappointment.
    covers_minutes: int | None = None

    @classmethod
    def of(cls, tier: Tier, *, remaining_cents: int = 0) -> TierOffer:
        minutes = covers_minutes(remaining_cents, tier)
        return cls(
            tier=tier,
            cents_per_hour=TIER_RATES_CENTS_PER_HOUR[tier],
            natural_voice=tier is not Tier.BASE,
            advertising=tier in (Tier.BASE, Tier.MODE_A),
            premium_voice=tier is Tier.MODE_C,
            covers_minutes=minutes or None,
        )

    @property
    def rate_label(self) -> str:
        return f"{self.cents_per_hour / 100:.2f}/h"

    def differences_from(self, other: TierOffer) -> tuple[str, ...]:
        """Which features differ between two tiers, ignoring the price.

        The price is left out on purpose: it differs between every pair, and including it
        would make the one-difference invariant impossible to state.
        """
        return tuple(
            name
            for name in ("natural_voice", "advertising", "premium_voice")
            if getattr(self, name) != getattr(other, name)
        )


def offer_for(db: Session, subject_id: uuid.UUID) -> list[TierOffer]:
    """Every tier, priced, and — if this person has credit left — timed.

    The catalogue is the same for everybody; what is personal is the credit. Two people
    looking at this screen differ in how long their money lasts, never in which tiers exist.
    """
    remaining = max(0, balance(db, subject_id).gifted_cents)
    return [TierOffer.of(tier, remaining_cents=remaining) for tier in Tier]
