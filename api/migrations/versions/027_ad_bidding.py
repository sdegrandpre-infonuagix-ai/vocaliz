"""What an ad is willing to pay, so broadcasts can be auctioned.

An ad now carries a maximum. For a given salon its bid is distributed across two dimensions
by configurable coefficients — how well the ad's regions match where the participants are, and
how well its topic matches what the salon is about — and the highest resulting score wins the
right to be spoken.

SECOND PRICE, not first. The winner pays the least it would have taken to beat the runner-up,
never its full bid. A first-price auction is played rather than bid: everyone shades their
offer downwards guessing at the others, and the ranking stops reflecting who actually values
the salon most. This is why AdWords works the way it does.

ad_broadcast_rate_cents becomes the reserve — the floor charged when nobody was outbid.

Revision ID: 027
Revises: 026
Create Date: 2026-08-03
"""
from alembic import op
import sqlalchemy as sa

revision = "027"
down_revision = "026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Zero means "do not bid": an ad may exist, be paid for by broadcast count, and sit out of
    # the auction entirely. Server default zero so existing ads do not silently start bidding.
    op.add_column(
        "ads", sa.Column("bid_cents", sa.Integer(), nullable=False, server_default="0")
    )
    op.create_check_constraint("ck_ads_bid_not_negative", "ads", "bid_cents >= 0")
    # The auction reads this on every candidate, discarding anything that cannot outbid the
    # reserve before it computes a single score.
    op.create_index("ix_ads_bid_cents", "ads", ["bid_cents"])


def downgrade() -> None:
    op.drop_index("ix_ads_bid_cents", table_name="ads")
    op.drop_constraint("ck_ads_bid_not_negative", "ads", type_="check")
    op.drop_column("ads", "bid_cents")
