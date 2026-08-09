"""Which address or number belongs to which person, and an account may have only one of them.

Story 10.1. The signup identifier becomes the key to the ten-minute lifetime quota, and this
table is what makes it one: keyed to an account, the allowance resets for the price of a second
signup; keyed to the identifier, there is nothing about a new account, a new Salon or a change
of role that could return any of it.

The identifier is the primary key, which is the guarantee rather than a convenience — two rows
for one address would be two quotas for one person, found in whichever order a query happened
to return them. CASCADE from the user: an identifier whose person is gone belongs to nobody.
What must not come back is the welcome *credit*, and `burned_identifiers` holds that
separately, with no foreign key, on purpose.

`users.email` becomes nullable at the same time, with a CHECK that one of the two columns is
present. Somebody invited by telephone has a number and no address, and demanding one anyway
would be demanding a second identifier to prove the first. The CHECK is what keeps "either"
from becoming "neither" — which is the anonymous access this story exists to remove.

**The downgrade will fail once anybody has signed up by telephone alone**, and that is a
property of the change rather than a defect in the reversal: `SET NOT NULL` cannot succeed
while rows hold a NULL address. Reversing it means deciding what becomes of those accounts,
which is not a decision a migration should make silently — so it raises rather than inventing
an address for them.

Revision ID: 052
Revises: 051
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "052"
down_revision = "051"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "participant_identifiers",
        sa.Column("identifier", sa.String(320), primary_key=True),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "added_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    # Every account that already exists keeps what it has spent. Backfilled rather than left
    # to the next signup: an account whose identifier is not in the registry would be found
    # by the fallback on `users.email` today and by nothing at all once that goes.
    op.execute(
        """
        INSERT INTO participant_identifiers (identifier, user_id)
        SELECT lower(email), id FROM users WHERE email IS NOT NULL
        """
    )
    op.execute(
        """
        INSERT INTO participant_identifiers (identifier, user_id)
        SELECT phone_number, id FROM users
        WHERE phone_number IS NOT NULL AND phone_number <> ''
        """
    )

    with op.batch_alter_table("users") as batch:
        batch.alter_column("email", existing_type=sa.String(320), nullable=True)
        batch.create_check_constraint(
            "ck_users_one_identifier", "email IS NOT NULL OR phone_number IS NOT NULL"
        )


def downgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.drop_constraint("ck_users_one_identifier", type_="check")
        batch.alter_column("email", existing_type=sa.String(320), nullable=False)
    op.drop_table("participant_identifiers")
