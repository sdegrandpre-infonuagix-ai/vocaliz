"""A participation is keyed on the LiveKit identity, so a guest with no address has one.

Anonymous invitations carry no email and no phone number. The old key was
(email, phone, user_type, salon_name) with a CHECK forbidding both identity columns empty, so an
anonymous guest could not be recorded at all — and was not. They joined salons, spoke, left, and
appeared nowhere. The report could not show them because there was nothing to show.

The LiveKit identity is the natural key and was already being minted for everybody: a host joins
as their account UUID, a guest as "guest-<invitation id>". It exists before the participant
connects, it is what every message in the room is addressed to, and it is present whether or not
anybody knows who the person is.

Consequences worth stating plainly:

  * email and phone become ordinary columns. They still say who somebody is when that is known,
    and are empty when it is not, but they no longer decide row identity.
  * user_type leaves the key. One identity is one participant in one salon; a host cannot also
    be a guest of the same salon under the same identity.
  * a guest invited twice to the same salon has two invitations and therefore two identities.
    That is one row each, which is what the room saw.

The backfill reconstructs identities rather than discarding history. Hosts resolve through their
address to their account UUID. Guests resolve through their address and the room to the
invitation that let them in. Anything left over keeps a "legacy:" identity built from the old key,
so no row is lost and none can collide.

Revision ID: 036
Revises: 035
Create Date: 2026-08-04
"""
from alembic import op
import sqlalchemy as sa

revision = "036"
down_revision = "035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "salon_events",
        sa.Column(
            "participant_identity", sa.String(200), nullable=False, server_default=""
        ),
    )

    # A host joins LiveKit as their account UUID — see generate_participant_token at the
    # session-join endpoint, which passes str(current_user.id).
    op.execute(
        """
        UPDATE salon_events AS se
           SET participant_identity = u.id::text
          FROM users AS u
         WHERE se.user_type = 'host'
           AND se.email <> ''
           AND se.email = u.email
        """
    )

    # A guest joins as "guest-<invitation id>". The invitation is found through the address it
    # was sent to and the room it was for, which together are effectively unique: two
    # invitations to one address for one salon would be the same person invited twice.
    op.execute(
        """
        UPDATE salon_events AS se
           SET participant_identity = 'guest-' || i.id::text
          FROM invitations AS i
          JOIN sessions AS s ON s.id = i.session_id
         WHERE se.user_type = 'guest'
           AND se.email <> ''
           AND se.email = i.guest_email
           AND se.salon_name = s.livekit_room_name
        """
    )

    # Whatever is left — a guest reached only by text, a room since renamed, an invitation
    # deleted. Built from the old key so it stays unique, and prefixed so it is obvious in a
    # report that this identity was reconstructed rather than observed.
    op.execute(
        """
        UPDATE salon_events
           SET participant_identity =
               'legacy:' || user_type || ':' || email || ':' || phone || ':' || salon_name
         WHERE participant_identity = ''
        """
    )

    op.drop_constraint("salon_events_pkey", "salon_events", type_="primary")
    op.create_primary_key(
        "salon_events_pkey", "salon_events", ["participant_identity", "salon_name"]
    )

    # The old rule said a participation must be attached to somebody reachable. The new one says
    # it must be attached to somebody who was in the room, which is both weaker about contact
    # details and stronger about presence.
    op.drop_constraint("ck_salon_events_identified", "salon_events", type_="check")
    op.create_check_constraint(
        "ck_salon_events_identified", "salon_events", "participant_identity <> ''"
    )


def downgrade() -> None:
    # Anonymous participations cannot exist under the old key, and there is no address to invent
    # for them. Deleted rather than given a fake one: a made-up identity would be worse than an
    # absence, because it would be counted.
    op.execute("DELETE FROM salon_events WHERE email = '' AND phone = ''")

    op.drop_constraint("ck_salon_events_identified", "salon_events", type_="check")
    op.drop_constraint("salon_events_pkey", "salon_events", type_="primary")
    op.create_primary_key(
        "salon_events_pkey",
        "salon_events",
        ["email", "phone", "user_type", "salon_name"],
    )
    op.create_check_constraint(
        "ck_salon_events_identified", "salon_events", "email <> '' OR phone <> ''"
    )
    op.drop_column("salon_events", "participant_identity")
