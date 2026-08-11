"""Who is currently in the salon — read live from LiveKit, not from a column.

Under the per-participant topology a room holds exactly one human, so there is no single
room to list. This endpoint aggregates over the host's room and every accepted guest's own
room, the same way get_agent_state already does for one room at a time.
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from src.models.invitation import Invitation
from src.models.salon import Salon
from src.models.user import User
from src.services.jwt_service import issue_token


@pytest.fixture
def host(db):
    u = User(email="presencehost@example.com", display_name="Marie")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u, issue_token(str(u.id))


@pytest.fixture
def salon(db, host):
    host_user, _ = host
    s = Salon(
        host_user_id=host_user.id,
        livekit_room_name="room-presence-host",
        source_type="url",
        source_url="https://example.com",
        source_content="c",
        status="active",
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _accepted_guest(db, salon, host_user, *, room_name="room-presence-guest", display_name=None):
    guest = User(email=f"presenceguest-{room_name}@example.com", display_name=display_name)
    db.add(guest)
    db.commit()
    db.refresh(guest)
    invitation = Invitation(
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
    db.add(invitation)
    db.commit()
    return guest, invitation, issue_token(str(guest.id))


def _pending_guest(db, salon, host_user):
    guest = User(email="presencepending@example.com")
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
            join_token="tok-pending-presence",
            status="pending",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
    )
    db.commit()
    return guest


# ─── The host, always ──────────────────────────────────────────────────────────

def test_the_host_always_appears(client, salon, host):
    _, token = host
    with patch(
        "src.services.livekit_service.human_is_present", new_callable=AsyncMock
    ) as present:
        present.return_value = True
        body = client.get(f"/salons/{salon.id}/presence", headers=_auth(token)).json()
    assert body["participants"] == [{"name": "Marie", "role": "host", "connected": True}]


def test_a_disconnected_host_is_reported_as_such(client, salon, host):
    _, token = host
    with patch(
        "src.services.livekit_service.human_is_present", new_callable=AsyncMock
    ) as present:
        present.return_value = False
        body = client.get(f"/salons/{salon.id}/presence", headers=_auth(token)).json()
    assert body["participants"][0]["connected"] is False


# ─── Accepted guests ────────────────────────────────────────────────────────────

def test_an_accepted_guest_with_a_room_is_checked_for_presence(client, salon, host, db):
    host_user, token = host
    _accepted_guest(db, salon, host_user, room_name="room-presence-g1", display_name="Marc")

    with patch(
        "src.services.livekit_service.human_is_present", new_callable=AsyncMock
    ) as present:
        present.return_value = True
        body = client.get(f"/salons/{salon.id}/presence", headers=_auth(token)).json()

    guest_entry = next(p for p in body["participants"] if p["role"] == "guest")
    assert guest_entry == {"name": "Marc", "role": "guest", "connected": True}
    assert present.await_count == 2  # host's room and the guest's room


def test_a_guest_with_no_name_is_labelled_the_same_way_captions_do(client, salon, host, db):
    """No given_name at join time, so no display_name — the anonymised guest label, not
    the guest's own account email."""
    host_user, token = host
    _, invitation, _ = _accepted_guest(
        db, salon, host_user, room_name="room-presence-g2", display_name=None
    )

    with patch(
        "src.services.livekit_service.human_is_present", new_callable=AsyncMock
    ) as present:
        present.return_value = False
        body = client.get(f"/salons/{salon.id}/presence", headers=_auth(token)).json()

    from src.services import livekit_service

    guest_entry = next(p for p in body["participants"] if p["role"] == "guest")
    assert guest_entry["name"] == livekit_service.guest_display_name(invitation.id)


def test_an_accepted_guest_with_no_room_yet_is_not_connected(client, salon, host, db):
    """Accepted an invitation but never actually joined — no room exists to ask LiveKit
    about, so this is known without a call rather than guessed from a failed lookup."""
    host_user, token = host
    guest = User(email="presence-noroom@example.com")
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
            join_token="tok-noroom",
            status="accepted",
            livekit_room_name=None,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
    )
    db.commit()

    with patch(
        "src.services.livekit_service.human_is_present", new_callable=AsyncMock
    ) as present:
        present.return_value = True
        body = client.get(f"/salons/{salon.id}/presence", headers=_auth(token)).json()

    guest_entry = next(p for p in body["participants"] if p["role"] == "guest")
    assert guest_entry["connected"] is False
    # Only the host's own room was ever asked about — the guest has none yet.
    present.assert_awaited_once()


def test_a_pending_guest_is_not_listed_at_all(client, salon, host, db):
    """Invited is not the same as arrived — the same line the agent controls draw."""
    host_user, token = host
    _pending_guest(db, salon, host_user)

    with patch(
        "src.services.livekit_service.human_is_present", new_callable=AsyncMock
    ) as present:
        present.return_value = True
        body = client.get(f"/salons/{salon.id}/presence", headers=_auth(token)).json()

    assert len(body["participants"]) == 1
    assert body["participants"][0]["role"] == "host"


# ─── Who may read this ──────────────────────────────────────────────────────────

def test_a_stranger_is_refused(client, salon):
    resp = client.get(f"/salons/{salon.id}/presence")
    assert resp.status_code in (401, 403)


def test_another_host_cannot_see_this_salons_presence(client, salon, db):
    other = User(email="other-presence-host@example.com")
    db.add(other)
    db.commit()
    db.refresh(other)
    resp = client.get(
        f"/salons/{salon.id}/presence", headers=_auth(issue_token(str(other.id)))
    )
    assert resp.status_code == 404


def test_an_accepted_guest_can_read_presence(client, salon, host, db):
    host_user, _ = host
    _, _, guest_token = _accepted_guest(db, salon, host_user)

    with patch(
        "src.services.livekit_service.human_is_present", new_callable=AsyncMock
    ) as present:
        present.return_value = True
        resp = client.get(f"/salons/{salon.id}/presence", headers=_auth(guest_token))

    assert resp.status_code == 200


def test_a_pending_guest_cannot_read_presence(client, salon, host, db):
    host_user, _ = host
    guest = _pending_guest(db, salon, host_user)
    resp = client.get(
        f"/salons/{salon.id}/presence", headers=_auth(issue_token(str(guest.id)))
    )
    assert resp.status_code == 404


def test_an_unknown_salon_is_not_found(client, host):
    _, token = host
    import uuid

    resp = client.get(f"/salons/{uuid.uuid4()}/presence", headers=_auth(token))
    assert resp.status_code == 404
