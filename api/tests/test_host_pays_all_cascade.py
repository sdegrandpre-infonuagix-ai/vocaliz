"""When the host leaves, who else goes with them.

By default each participant pays for themselves, so a host ending their own Salon touches
only their own room — a guest under the per-participant topology has a separate room and
keeps it. `host_pays_all` (FR42) changes that: the host is paying for everyone's metered
time, so their departure has to end everyone's, not just their own. `finalize_salon` names
which guest rooms qualify; it never deletes them itself — that stays the caller's job, the
same as it already was for the host's own room.
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from src.models.invitation import Invitation
from src.models.salon import Salon
from src.models.user import User
from src.services import salon_lifecycle
from src.services.jwt_service import issue_token


@pytest.fixture
def host(db):
    u = User(email="cascadehost@example.com")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u, issue_token(str(u.id))


def _salon(db, host_user, *, host_pays_all: bool) -> Salon:
    s = Salon(
        host_user_id=host_user.id,
        livekit_room_name="room-cascade-host",
        source_type="url",
        source_url="https://example.com",
        source_content="c",
        status="active",
        host_pays_all=host_pays_all,
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def _accepted_guest(db, salon, host_user, *, room_name="room-cascade-guest"):
    guest = User(email=f"cascadeguest-{room_name}@example.com")
    db.add(guest)
    db.commit()
    db.refresh(guest)
    db.add(
        Invitation(
            salon_id=salon.id,
            host_user_id=host_user.id,
            guest_email=guest.email,
            guest_user_id=guest.id,
            invitation_type="email_contact",
            join_token=f"tok-{guest.id}",
            status="accepted",
            livekit_room_name=room_name,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
    )
    db.commit()
    return guest


def _pending_guest(db, salon, host_user):
    guest = User(email="cascadepending@example.com")
    db.add(guest)
    db.commit()
    db.refresh(guest)
    db.add(
        Invitation(
            salon_id=salon.id,
            host_user_id=host_user.id,
            guest_email=guest.email,
            guest_user_id=guest.id,
            invitation_type="email_contact",
            join_token="tok-cascade-pending",
            status="pending",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
    )
    db.commit()


# ─── finalize_salon's own answer ────────────────────────────────────────────────

def test_by_default_a_guests_room_is_left_alone(db, host):
    host_user, _ = host
    salon = _salon(db, host_user, host_pays_all=False)
    _accepted_guest(db, salon, host_user)

    _, guest_rooms = salon_lifecycle.finalize_salon(salon, db)

    assert guest_rooms == []


def test_when_the_host_pays_all_the_guests_room_is_named(db, host):
    host_user, _ = host
    salon = _salon(db, host_user, host_pays_all=True)
    _accepted_guest(db, salon, host_user, room_name="room-cascade-g1")

    _, guest_rooms = salon_lifecycle.finalize_salon(salon, db)

    assert guest_rooms == ["room-cascade-g1"]


def test_a_pending_guest_is_never_named(db, host):
    """Invited is not the same as arrived — the same line the presence endpoint and the
    agent controls both already draw."""
    host_user, _ = host
    salon = _salon(db, host_user, host_pays_all=True)
    _pending_guest(db, salon, host_user)

    _, guest_rooms = salon_lifecycle.finalize_salon(salon, db)

    assert guest_rooms == []


def test_an_accepted_guest_with_no_room_yet_is_never_named(db, host):
    """Accepted an invitation but never actually joined — there is no room to tear down,
    and naming one that does not exist would only make the teardown fail later."""
    host_user, _ = host
    salon = _salon(db, host_user, host_pays_all=True)
    guest = User(email="cascade-noroom@example.com")
    db.add(guest)
    db.commit()
    db.refresh(guest)
    db.add(
        Invitation(
            salon_id=salon.id,
            host_user_id=host_user.id,
            guest_email=guest.email,
            guest_user_id=guest.id,
            invitation_type="email_contact",
            join_token="tok-cascade-noroom",
            status="accepted",
            livekit_room_name=None,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
    )
    db.commit()

    _, guest_rooms = salon_lifecycle.finalize_salon(salon, db)

    assert guest_rooms == []


def test_multiple_accepted_guests_are_all_named(db, host):
    host_user, _ = host
    salon = _salon(db, host_user, host_pays_all=True)
    _accepted_guest(db, salon, host_user, room_name="room-cascade-g1")
    _accepted_guest(db, salon, host_user, room_name="room-cascade-g2")

    _, guest_rooms = salon_lifecycle.finalize_salon(salon, db)

    assert sorted(guest_rooms) == ["room-cascade-g1", "room-cascade-g2"]


# ─── close_guest_rooms: best-effort, one failure does not stop the rest ────────

@pytest.mark.asyncio
async def test_one_failing_room_does_not_block_the_others():
    with patch(
        "src.services.livekit_service.delete_room",
        new_callable=AsyncMock,
        side_effect=[Exception("boom"), None],
    ) as delete_room:
        await salon_lifecycle.close_guest_rooms(["room-a", "room-b"])
    assert delete_room.await_count == 2


# ─── End to end, through the endpoint ───────────────────────────────────────────

def test_ending_the_salon_deletes_the_guests_room_too_when_host_pays_all(client, db, host):
    host_user, token = host
    salon = _salon(db, host_user, host_pays_all=True)
    _accepted_guest(db, salon, host_user, room_name="room-cascade-e2e")

    with patch(
        "src.services.livekit_service.delete_room", new_callable=AsyncMock
    ) as delete_room:
        resp = client.post(
            f"/salons/{salon.id}/end", headers={"Authorization": f"Bearer {token}"}
        )

    assert resp.status_code == 200
    deleted = {call.args[0] for call in delete_room.await_args_list}
    assert deleted == {"room-cascade-host", "room-cascade-e2e"}


def test_ending_the_salon_leaves_the_guests_room_alone_by_default(client, db, host):
    host_user, token = host
    salon = _salon(db, host_user, host_pays_all=False)
    _accepted_guest(db, salon, host_user, room_name="room-cascade-e2e-solo")

    with patch(
        "src.services.livekit_service.delete_room", new_callable=AsyncMock
    ) as delete_room:
        resp = client.post(
            f"/salons/{salon.id}/end", headers={"Authorization": f"Bearer {token}"}
        )

    assert resp.status_code == 200
    deleted = {call.args[0] for call in delete_room.await_args_list}
    assert deleted == {"room-cascade-host"}
