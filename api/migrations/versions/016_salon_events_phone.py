"""A participant is identified by an email or a phone number, and must have one.

Guests can now be invited by text message alone, so an address is no longer guaranteed.
The identity in salon_events therefore becomes two columns instead of one, and both join
the primary key.

Neither can be NULL — a primary key column cannot be — so the absent one is stored as an
empty string. That is a real cost and worth naming: to the database '' is a value like
any other, so every query about "has an email" must test <> '' and not IS NOT NULL, and a
single lapse would silently create a second row for the same person. A CHECK makes the
one thing that must never happen impossible: both empty at once, a row identifying nobody.

The consequence to expect: someone invited by email to one salon and by text to another
is two identities, not one. Reconciling them would need a rule for deciding that an
address and a number belong to the same person, and there is none.

Revision ID: 016
Revises: 015
Create Date: 2026-08-03
"""
from alembic import op
import sqlalchemy as sa

revision = "016"
down_revision = "015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Added with a default so the rows already there — recorded when email was the only
    # identity — become valid under the new key without being touched.
    op.add_column(
        "salon_events",
        sa.Column("phone", sa.String(16), nullable=False, server_default=""),
    )

    op.drop_constraint("salon_events_pkey", "salon_events", type_="primary")
    op.create_primary_key(
        "salon_events_pkey",
        "salon_events",
        ["email", "phone", "user_type", "salon_name"],
    )

    # The one state that must never exist: a participation attached to nobody.
    op.create_check_constraint(
        "ck_salon_events_identified",
        "salon_events",
        "email <> '' OR phone <> ''",
    )

    # Finding every salon one person took part in is the query behind both the admin
    # listing and is_first_salon, and neither can use a composite key that leads with a
    # column they may not have.
    op.create_index("ix_salon_events_email", "salon_events", ["email"])
    op.create_index("ix_salon_events_phone", "salon_events", ["phone"])

    # ── invitations, on the same convention ───────────────────────────────────
    # guest_email was already NOT NULL, so '' needs no change there. guest_phone was
    # nullable, which would have left one table using '' for "absent" and the other NULL —
    # two conventions for one idea, in code that reads both in the same breath.
    op.execute("UPDATE invitations SET guest_phone = '' WHERE guest_phone IS NULL")
    op.alter_column(
        "invitations",
        "guest_phone",
        existing_type=sa.String(20),
        nullable=False,
        server_default="",
    )
    op.create_check_constraint(
        "ck_invitations_contact",
        "invitations",
        "guest_email <> '' OR guest_phone <> ''",
    )


def downgrade() -> None:
    op.drop_constraint("ck_invitations_contact", "invitations", type_="check")
    op.alter_column(
        "invitations",
        "guest_phone",
        existing_type=sa.String(20),
        nullable=True,
        server_default=None,
    )

    op.drop_index("ix_salon_events_phone", table_name="salon_events")
    op.drop_index("ix_salon_events_email", table_name="salon_events")
    op.drop_constraint("ck_salon_events_identified", "salon_events", type_="check")
    op.drop_constraint("salon_events_pkey", "salon_events", type_="primary")
    # Rows identified only by a phone number cannot be represented by the old key, and
    # would collide on ('', user_type, salon_name). Dropping them is the honest reversal:
    # the alternative is a primary key violation halfway through the downgrade.
    op.execute("DELETE FROM salon_events WHERE email = ''")
    op.create_primary_key(
        "salon_events_pkey", "salon_events", ["email", "user_type", "salon_name"]
    )
    op.drop_column("salon_events", "phone")
