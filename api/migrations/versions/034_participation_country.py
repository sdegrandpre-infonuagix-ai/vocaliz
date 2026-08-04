"""Roughly where a participation came from, as a country and nothing finer.

There was no source for this at all. The position column holds a neighbourhood-scale Plus Code,
but nothing ever fills it: no page asks the browser for a location, so plus_code is empty for
every web participant. And the API is served through a regional API Gateway domain rather than
CloudFront — a deliberate choice, so the certificate can stay in this region — which means no
viewer-country header reaches the application either.

So the country is taken from the browser's own locale, the region subtag of navigator.language:
"fr-CA" gives CA. Self-reported and easily wrong — somebody travelling, or running an English
system in Montreal, reports whatever their device says. That is the honest ceiling of a signal
that costs no new service, stores no IP address, and asks the participant for nothing.

Two characters, uppercase, empty when the browser offered no region. Not NULL: the sibling
columns on this table use the empty string for absent, and one column behaving differently in
every query costs more than the ambiguity it would resolve.

Revision ID: 034
Revises: 033
Create Date: 2026-08-04
"""
from alembic import op
import sqlalchemy as sa

revision = "034"
down_revision = "033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "salon_events",
        sa.Column("country", sa.String(2), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_column("salon_events", "country")
