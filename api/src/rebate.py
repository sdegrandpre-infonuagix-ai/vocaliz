"""More balance for a top-up taken outside the app stores (FR70).

Arithmetic before strategy. A store takes between 5 % and 30 % of every purchase made through
it; a browser payment avoids that entirely. Handing part of the saving back costs Vocaliz
nothing it was going to keep, and moves people to the cheaper channel by making it the better
one for them as well.

Five per cent is the default because it is covered in **every** combination, including the
least favourable — Android in the United States under a million dollars of revenue, where
only 5 % is avoided. A rebate that worked on average and lost money in the worst case would
be a promotion that punished success, and a test walks every combination to hold it.

The rate is adjustable per platform and region without a deploy (FR54), because the
commissions themselves move: the litigation is unsettled until 2027, and crossing a million
dollars of annual revenue doubles them overnight — the gap between store and browser goes
from fifteen points to thirty, and the web channel stops being an optimisation.

And the extra balance is never a receipt. Stripe took one amount and the payer received a
larger one; the difference is a commercial charge, which is why it reaches the paid-balance
journal as its own movement rather than as collection.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

# The default. Covered even where only 5 % is avoided.
WEB_REBATE_RATE = 0.05

# Above this, the stores' reduced small-business rates end and their commissions double.
SMALL_BUSINESS_CEILING_CENTS = 1_000_000_00


class Platform(Enum):
    """Where a top-up was taken. Only the web avoids a commission."""

    WEB = "web"
    IOS = "ios"
    ANDROID = "android"


def _platform(value: Platform | str) -> Platform:
    """Refuse anything unrecognised rather than defaulting it.

    Defaulting an unknown client to the web rate would let anybody claim the rebate by
    sending a string nobody recognises.
    """
    if isinstance(value, Platform):
        return value
    raise ValueError(
        f"unknown platform {value!r}. It is one of "
        f"{', '.join(one.value for one in Platform)}."
    )


def store_commission_rate(
    *, platform: Platform, region: str, annual_revenue_cents: int
) -> float:
    """What the store takes, and therefore what a browser payment avoids.

    The web avoids nothing of its own — there is no store in the path. Everywhere else the
    rate doubles once annual revenue passes the small-business ceiling, and Apple outside the
    United States is the dearest corner of the table.
    """
    if platform is Platform.WEB:
        return 0.0

    small = annual_revenue_cents <= SMALL_BUSINESS_CEILING_CENTS
    if platform is Platform.IOS and region != "US":
        return 0.15 if small else 0.30
    if platform is Platform.IOS:
        return 0.15 if small else 0.30
    return 0.05 if small else 0.15


@dataclass(frozen=True)
class RebatePolicy:
    """What is handed back, by platform and region.

    A mapping rather than a constant so that a commission change is a configuration change.
    An unconfigured combination falls back to the default, and the app stores are always
    zero however the web is configured — there is no commission avoided there to share.
    """

    rates: dict[tuple[Platform, str], float] = field(default_factory=dict)

    def rate_for(self, *, platform: Platform | str, region: str) -> float:
        platform = _platform(platform)
        if platform is not Platform.WEB:
            return 0.0
        return self.rates.get((platform, region), WEB_REBATE_RATE)

    def warnings(self, *, region: str, annual_revenue_cents: int) -> list[str]:
        """Flag a rebate larger than the commission it is funded by.

        Accepted, never refused — somebody may well decide a 20 % rebate is worth paying for.
        But accepting it *silently* would let money be spent by typing a number, and this is
        an acquisition decision rather than a setting.
        """
        rate = self.rate_for(platform=Platform.WEB, region=region)
        worst_avoided = min(
            store_commission_rate(
                platform=platform, region=region, annual_revenue_cents=annual_revenue_cents
            )
            for platform in (Platform.IOS, Platform.ANDROID)
        )
        if rate <= worst_avoided:
            return []
        return [
            f"the web rebate of {rate:.0%} in {region} is above the {worst_avoided:.0%} "
            "commission a browser payment actually avoids there. That is an acquisition "
            "decision, not a saving — it is applied, but it costs money."
        ]


_DEFAULT_POLICY = RebatePolicy()


def rebate_cents(
    paid_cents: int, *, platform: Platform | str, region: str = "US", policy: RebatePolicy | None = None
) -> int:
    """The extra balance a payment earns, rounded **down**.

    Down because a rebate is a gift, and rounding a gift up spends money nobody decided to
    spend.
    """
    rate = (policy or _DEFAULT_POLICY).rate_for(platform=platform, region=region)
    return int(max(0, paid_cents) * rate)


def credited_cents(
    paid_cents: int, *, platform: Platform | str, region: str = "US", policy: RebatePolicy | None = None
) -> int:
    """What lands in the balance: what was paid, plus whatever the channel earned."""
    return paid_cents + rebate_cents(
        paid_cents, platform=platform, region=region, policy=policy
    )


def channel_offer_text(
    paid_cents: int, *, platform: Platform | str, region: str = "US", policy: RebatePolicy | None = None
) -> str:
    """What the payer is shown when choosing where to pay.

    Explicitly, in money. A rebate nobody knows about steers nobody — it is simply a cost
    absorbed for no change in behaviour at all, which is the one outcome that makes the whole
    thing pointless.
    """
    credited = credited_cents(paid_cents, platform=platform, region=region, policy=policy)
    if credited == paid_cents:
        return f"Pay {paid_cents / 100:.2f} and receive {paid_cents / 100:.2f} of balance."
    return (
        f"Pay {paid_cents / 100:.2f} in your browser and receive "
        f"{credited / 100:.2f} of balance — {(credited - paid_cents) / 100:.2f} more than "
        "paying in the app."
    )
