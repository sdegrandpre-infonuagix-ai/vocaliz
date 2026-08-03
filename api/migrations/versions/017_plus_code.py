"""Positions become Plus Codes, and raw addresses stop being kept.

salon_events held a precise latitude and longitude — six decimals, about eleven
centimetres — and the caller's IP address. Neither is needed for what the data is for,
which is knowing roughly where participants come from.

A position is now stored as an Open Location Code at the length configured in
LOCATION_CODE_LENGTH, six by default: a cell about five and a half kilometres across. The
encoding happens at ingestion, so the exact coordinates never reach the disk. Rounding on
the way out would have left them at rest, which is the thing worth avoiding.

A Plus Code rather than rounded decimals because a decimal pair still reads as a point,
and a point invites being treated as one. A Plus Code is a cell; its imprecision is part
of the value instead of a convention someone has to remember.

client_ip goes without replacement. Deriving a location from an address needs a GeoIP
database in the image or a lookup service per join, and neither exists — so keeping the
address meant holding personal data against a plan rather than against a use. A
participant who declines the location prompt now has no recorded location, which is the
honest state.

Revision ID: 017
Revises: 016
Create Date: 2026-08-03
"""
from alembic import op
import sqlalchemy as sa

revision = "017"
down_revision = "016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "salon_events",
        sa.Column("plus_code", sa.String(16), nullable=False, server_default=""),
    )
    # Existing positions are not carried over. Re-encoding them here would mean reading
    # the precise values one last time to write a coarse one, and there are two rows in
    # this table — neither with a position. Correctness is not worth a data migration
    # that touches exactly nothing.
    op.drop_column("salon_events", "gps_latitude")
    op.drop_column("salon_events", "gps_longitude")
    op.drop_column("salon_events", "client_ip")


def downgrade() -> None:
    op.add_column("salon_events", sa.Column("client_ip", sa.String(45), nullable=True))
    op.add_column("salon_events", sa.Column("gps_longitude", sa.Numeric(9, 6), nullable=True))
    op.add_column("salon_events", sa.Column("gps_latitude", sa.Numeric(8, 6), nullable=True))
    # The precise values are gone and cannot be recovered from a cell. Reversing the
    # schema restores the columns empty, which is the only truthful reversal available.
    op.drop_column("salon_events", "plus_code")
