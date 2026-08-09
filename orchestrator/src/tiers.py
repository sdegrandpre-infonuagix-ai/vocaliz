"""What each interpretation tier costs a listener, in interruptions and in model (FR33 / NFR6).

Two things vary by tier here, and neither is a property of the conversation.

**How often advertising interrupts.** Base hears one advertisement every five minutes, Mode A
one every ten, and Modes B and C hear none. That is the whole of what paying more buys on this
axis, and it has a second-order effect worth naming: reading an advertisement occupies an
interpreter, so its cursor advances more slowly and its lag grows. A listener who hears none
accumulates less lag than one in Mode A, who accumulates less than one in Base — so they
condense less often (FR53) and saturate more rarely (FR49). The tiers are not only a price
list; they are a quality gradient with a mechanism behind it, which is why the condensation
rate and the saturation count are instrumented per tier (NFR4). The point of measuring is to
find out whether Base stays *usable* rather than merely being degraded.

**Which model the adapter is given.** Mode C runs on a later model than Modes A and B. It is a
per-tier adapter parameter and never a product constant: a model name compiled into the
interpretation code would have to be found in several places the day it changes, and one of
them would be missed. A test asserts these strings appear nowhere else in `src/`.

Base has no entry in that table, and its absence is not an omission. It is not one realtime
model at all — it is speech to text, then text, then speech, three providers in a chain — so
there is no single model name to give it.
"""
from __future__ import annotations

from enum import Enum

from src.settings import SalonSettings


class Tier(Enum):
    """The interpretation tiers, cheapest first.

    Named rather than inferred from the adapter class: figures are published per tier, and a
    label that moved when somebody renamed a class would break the comparison over time.
    """

    BASE = "Base"
    MODE_A = "Mode A"
    MODE_B = "Mode B"
    MODE_C = "Mode C"


# The one place a model name is written down. Mode C's is later than the one A and B share;
# Base is absent because it is a chain of three providers rather than a single model.
MODELS: dict[Tier, str] = {
    Tier.MODE_A: "grok-voice-think-fast-1.0",
    Tier.MODE_B: "grok-voice-think-fast-1.0",
    Tier.MODE_C: "grok-voice-think-fast-2.0",
}


def model_for(tier: Tier) -> str | None:
    """The realtime model an adapter at this tier is given, or `None` where there is none.

    `None` for Base is a fact about the tier and not a missing configuration: nothing there
    is one model, so nothing there has one name.
    """
    return MODELS.get(tier)


def advert_interval_seconds(
    tier: Tier, *, settings: SalonSettings, covered: bool = False
) -> float | None:
    """How often this listener hears an advertisement, or `None` for never.

    `covered` is the host paying for everybody (FR32). Somebody whose participation has been
    paid for hears no advertising whatever tier their interpreter runs at — the advertising is
    how an unpaid seat is paid for, and charging twice for one seat is what this prevents.

    The two intervals are separate settings so they can be moved independently (FR54). Modes B
    and C return `None` for the same reason they always will: their price is what buys the
    silence, and making that a number somebody could set to five minutes would put the promise
    one typo away from being broken.
    """
    if covered:
        return None
    if tier is Tier.BASE:
        return settings.advert_interval_base_seconds
    if tier is Tier.MODE_A:
        return settings.advert_interval_mode_a_seconds
    return None
