"""Target languages, verbatim substitutions, and the removal of the third geography.

The inherited exchange keeps its auction, its billing and its proof of delivery. What the
multi-rooms topology needs on top is the other half of the targeting: an ad already names the
cells it may be heard in, and now names the languages too — a criterion about the humans it
will be read to, not a property of the text, which is translated for whoever is listening.

Rows rather than lists, matching `ads_regions`: one ad addresses several regions and several
languages with no row per combination. Empty on a dimension means unrestricted there; empty on
both is what makes an ad generic, and generic is the fallback served when nothing matches.

`ads_substitutions` holds wording an advertiser requires word for word in one language — a
brand form or a legal order. One language only; the others carry on being translated from the
canonical creative.

And the third way of saying where an ad may be heard goes. `advertisers.target_countries`,
`target_regions` and the circle never had data behind them and never could: `salon_events`
stores a grid cell, not a political boundary, and naming the country a cell falls in needs
reverse geocoding that does not exist here. The circle failed twice over — a position is a
cell about five and a half kilometres across, so a radius under that could never have been
served honestly. Two ways remain, both resolving to strings comparable as strings:
`ads_regions` on the ad, and `advertisers_regions` through the advertiser.

Irreversible in substance rather than in form: the downgrade recreates the columns empty,
which is the truthful restoration precisely because they never held anything.

Revision ID: 051
Revises: 050
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "051"
down_revision = "050"
branch_labels = None
depends_on = None

StringList = sa.JSON().with_variant(JSONB(), "postgresql")

SALES_PITCH_MAX = 2000


def upgrade() -> None:
    op.create_table(
        "ads_languages",
        sa.Column(
            "ad_id",
            UUID(as_uuid=True),
            sa.ForeignKey("ads.ad_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("language", sa.String(10), primary_key=True),
        sa.CheckConstraint("trim(language) <> ''", name="ck_ads_languages_not_blank"),
    )

    op.create_table(
        "ads_substitutions",
        sa.Column(
            "ad_id",
            UUID(as_uuid=True),
            sa.ForeignKey("ads.ad_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("language", sa.String(10), primary_key=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "trim(language) <> ''", name="ck_ads_substitutions_language_not_blank"
        ),
        sa.CheckConstraint("trim(text) <> ''", name="ck_ads_substitutions_text_not_blank"),
        sa.CheckConstraint(
            f"length(text) BETWEEN 1 AND {SALES_PITCH_MAX}",
            name="ck_ads_substitutions_text_length",
        ),
    )

    # Indicative and never contractual. Zero means nobody estimated it.
    op.add_column(
        "ads",
        sa.Column(
            "indicative_seconds",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.create_check_constraint(
        "ck_ads_indicative_seconds_not_negative", "ads", "indicative_seconds >= 0"
    )

    # The circle's constraints go before its columns: on Postgres the DROP COLUMN would take
    # them along, but naming them here says what is being removed rather than leaving it to
    # a cascade nobody reads.
    for name in ("ck_advertisers_circle_complete", "ck_advertisers_radius_positive"):
        op.drop_constraint(name, "advertisers", type_="check")

    for column in (
        "target_countries",
        "target_regions",
        "target_latitude",
        "target_longitude",
        "target_radius_km",
    ):
        op.drop_column("advertisers", column)


def downgrade() -> None:
    op.add_column(
        "advertisers",
        sa.Column(
            "target_countries", StringList, nullable=False, server_default=sa.text("'[]'")
        ),
    )
    op.add_column(
        "advertisers",
        sa.Column(
            "target_regions", StringList, nullable=False, server_default=sa.text("'[]'")
        ),
    )
    op.add_column("advertisers", sa.Column("target_latitude", sa.Numeric(8, 6), nullable=True))
    op.add_column(
        "advertisers", sa.Column("target_longitude", sa.Numeric(9, 6), nullable=True)
    )
    op.add_column(
        "advertisers", sa.Column("target_radius_km", sa.Numeric(7, 2), nullable=True)
    )
    op.create_check_constraint(
        "ck_advertisers_circle_complete",
        "advertisers",
        "(target_latitude IS NULL AND target_longitude IS NULL "
        " AND target_radius_km IS NULL) OR "
        "(target_latitude IS NOT NULL AND target_longitude IS NOT NULL "
        " AND target_radius_km IS NOT NULL)",
    )
    op.create_check_constraint(
        "ck_advertisers_radius_positive",
        "advertisers",
        "target_radius_km IS NULL OR target_radius_km > 0",
    )

    op.drop_constraint("ck_ads_indicative_seconds_not_negative", "ads", type_="check")
    op.drop_column("ads", "indicative_seconds")
    op.drop_table("ads_substitutions")
    op.drop_table("ads_languages")
