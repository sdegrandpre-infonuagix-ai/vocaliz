"""A random token per browser, so a device that comes back can be recognised as the same one.

The question this answers: which anonymous participants are returning? An anonymous invitation
mints a fresh identity every time, so the same person coming back looks like somebody new. There
was no way to tell one visitor who came five times from five visitors who came once.

What this is not. It is not a MAC address — no browser has ever exposed one, and since iOS 14
and Android 10 phones randomise theirs per Wi-Fi network precisely to prevent this kind of
matching. It is not a browser fingerprint either: canvas and font probing would work without
consent, which is exactly why Law 25 and the GDPR treat it more strictly than a stored value.

It is a random UUID the browser keeps in its own local storage and sends back. First-party,
readable by nobody else, shared with no other site, and deletable by the person holding it —
clearing site data ends it.

Its limits are real and should be stated wherever the number is read. Private browsing, cleared
storage, and a second browser on the same phone each look like a new device. Two people sharing
a laptop look like one. This measures browsers, not humans.

Empty for every row recorded before this migration, and for anyone joining by telephone.

Revision ID: 037
Revises: 036
Create Date: 2026-08-04
"""
from alembic import op
import sqlalchemy as sa

revision = "037"
down_revision = "036"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "salon_events",
        sa.Column("device_token", sa.String(36), nullable=False, server_default=""),
    )
    # Indexed because the only question asked of it is "where else has this token been", which
    # is a lookup by value across the table rather than a scan of one participation.
    op.create_index("ix_salon_events_device_token", "salon_events", ["device_token"])


def downgrade() -> None:
    op.drop_index("ix_salon_events_device_token", table_name="salon_events")
    op.drop_column("salon_events", "device_token")
