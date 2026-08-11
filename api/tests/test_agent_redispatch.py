"""Tests for redispatching an agent that left its room on its own.

The scenario this answers: `following.follow`'s own `on_unrecoverable` gives up on a realtime
session that cannot speak at all and has the agent leave (see agent.py) — safe only because
something on the API side sends a replacement. `redispatch_for_room` is that something. It
must find the right room under the per-participant topology (a host's own room named on the
Salon row, a guest's named on their invitation) and must do nothing for a room whose Salon has
already ended, where the agent leaving was the ordinary departure `finalize_salon` causes.
"""
import secrets
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from src.models.invitation import Invitation
from src.models.salon import Salon
from src.models.user import User
from src.services import agent_redispatch
from src.services.jwt_service import issue_token


@pytest.fixture
def host(db):
    u = User(email="15148880001@example.com", phone_number="+15148880001")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u, issue_token(str(u.id))


@pytest.fixture
def active_salon(db, host):
    host_user, _ = host
    salon = Salon(
        host_user_id=host_user.id,
        livekit_room_name="room-host-redispatch",
        source_type="url",
        source_url="https://example.com",
        source_content="content",
        status="active",
    )
    db.add(salon)
    db.commit()
    db.refresh(salon)
    return salon


def _accepted_invitation(db, salon, *, room_name="room-guest-redispatch"):
    inv = Invitation(
        salon_id=salon.id,
        host_user_id=salon.host_user_id,
        guest_email="guest@example.com",
        guest_user_id=None,
        invitation_type="email_contact",
        join_token=secrets.token_urlsafe(32),
        status="accepted",
        livekit_room_name=room_name,
        expires_at=datetime.now(tz=timezone.utc) + timedelta(hours=24),
    )
    db.add(inv)
    db.commit()
    db.refresh(inv)
    return inv


# ─── The host's own room ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_the_hosts_room_is_redispatched_as_the_host(db, host, active_salon):
    host_user, _ = host
    with patch(
        "src.services.agent_redispatch.livekit_service.dispatch_agent", new_callable=AsyncMock
    ) as mock_dispatch:
        sent = await agent_redispatch.redispatch_for_room(db, active_salon.livekit_room_name)

    assert sent is True
    mock_dispatch.assert_called_once()
    kwargs = mock_dispatch.call_args[1]
    assert kwargs["participant_id"] == str(host_user.id)
    assert kwargs["salon_id"] == str(active_salon.id)


@pytest.mark.asyncio
async def test_a_hosts_room_with_no_active_salon_is_not_redispatched(db, host, active_salon):
    active_salon.status = "ended"
    db.commit()

    with patch(
        "src.services.agent_redispatch.livekit_service.dispatch_agent", new_callable=AsyncMock
    ) as mock_dispatch:
        sent = await agent_redispatch.redispatch_for_room(db, active_salon.livekit_room_name)

    assert sent is False
    mock_dispatch.assert_not_called()


# ─── A guest's own room ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_a_guests_room_is_redispatched_as_that_guest(db, host, active_salon):
    invitation = _accepted_invitation(db, active_salon)

    with patch(
        "src.services.agent_redispatch.livekit_service.dispatch_agent", new_callable=AsyncMock
    ) as mock_dispatch:
        sent = await agent_redispatch.redispatch_for_room(db, invitation.livekit_room_name)

    assert sent is True
    kwargs = mock_dispatch.call_args[1]
    assert kwargs["participant_id"] == f"guest-{invitation.id}"
    assert kwargs["salon_id"] == str(active_salon.id)


@pytest.mark.asyncio
async def test_a_guests_room_is_not_redispatched_once_the_salon_has_ended(db, host, active_salon):
    invitation = _accepted_invitation(db, active_salon)
    active_salon.status = "ended"
    db.commit()

    with patch(
        "src.services.agent_redispatch.livekit_service.dispatch_agent", new_callable=AsyncMock
    ) as mock_dispatch:
        sent = await agent_redispatch.redispatch_for_room(db, invitation.livekit_room_name)

    assert sent is False
    mock_dispatch.assert_not_called()


@pytest.mark.asyncio
async def test_a_pending_invitations_room_is_not_redispatched(db, host, active_salon):
    """No `livekit_room_name` is set until the join actually happens — a pending invitation
    was never joined, so there is no room to send an agent into."""
    invitation = _accepted_invitation(db, active_salon, room_name=None)
    invitation.status = "pending"
    db.commit()

    with patch(
        "src.services.agent_redispatch.livekit_service.dispatch_agent", new_callable=AsyncMock
    ) as mock_dispatch:
        sent = await agent_redispatch.redispatch_for_room(db, "room-that-was-never-joined")

    assert sent is False
    mock_dispatch.assert_not_called()


@pytest.mark.asyncio
async def test_an_unrelated_room_name_is_not_redispatched(db):
    with patch(
        "src.services.agent_redispatch.livekit_service.dispatch_agent", new_callable=AsyncMock
    ) as mock_dispatch:
        sent = await agent_redispatch.redispatch_for_room(db, "room-nobody-recognises")

    assert sent is False
    mock_dispatch.assert_not_called()
