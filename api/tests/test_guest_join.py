"""Tests for GET /invitations/guest-join/{join_token} (Story 3.1)."""
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from src.models.invitation import Invitation
from src.models.salon import Salon
from src.models.user import User
from src.services.jwt_service import issue_token


# ─── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def host(db):
    u = User(email="15145550001@example.com", phone_number="+15145550001")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u, issue_token(str(u.id))


@pytest.fixture
def active_salon(db, host):
    host_user, _ = host
    sess = Salon(
        host_user_id=host_user.id,
        livekit_room_name="salon-guest-room",
        source_type="url",
        source_url="https://example.com",
        source_content="content",
        status="active",
    )
    db.add(sess)
    db.commit()
    db.refresh(sess)
    return sess


def _make_invitation(db, host_user, salon, *, status="pending", expired=False, token=None):
    expires = (
        datetime.now(tz=timezone.utc) - timedelta(hours=1)
        if expired
        else datetime.now(tz=timezone.utc) + timedelta(hours=24)
    )
    inv = Invitation(
        salon_id=salon.id,
        host_user_id=host_user.id,
        guest_email="15145559999@example.com",
        guest_user_id=None,
        invitation_type="email_contact",
        join_token=token or secrets.token_urlsafe(32),
        status=status,
        expires_at=expires,
    )
    db.add(inv)
    db.commit()
    db.refresh(inv)
    return inv


# ─── Success case ─────────────────────────────────────────────────────────────

def test_guest_join_returns_livekit_credentials(client, db, host, active_salon):
    """Valid pending token returns LiveKit credentials — for the guest's own room, not the
    host's. One human, one interpreter, one room; the host's room is now theirs alone."""
    host_user, _ = host
    inv = _make_invitation(db, host_user, active_salon)
    resp = client.get(f"/invitations/guest-join/{inv.join_token}")
    assert resp.status_code == 200
    body = resp.json()
    assert "participantToken" in body
    assert body["participantToken"]
    assert body["livekitRoomName"] != active_salon.livekit_room_name
    assert "livekitUrl" in body
    assert body["salonId"] == str(active_salon.id)


def test_guest_join_provisions_a_room_and_dispatches_one_agent(client, db, host, active_salon):
    """One room, one dispatch, for the one successful open a single-use link ever gets."""
    from unittest.mock import AsyncMock, patch

    host_user, _ = host
    inv = _make_invitation(db, host_user, active_salon)

    with (
        patch(
            "src.routers.invitations.livekit_service.create_room", new_callable=AsyncMock
        ) as create_room,
        patch(
            "src.routers.invitations.livekit_service.dispatch_agent", new_callable=AsyncMock
        ) as dispatch,
    ):
        resp = client.get(f"/invitations/guest-join/{inv.join_token}")

    create_room.assert_awaited_once()
    dispatch.assert_awaited_once()
    assert dispatch.await_args.kwargs["participant_id"] == resp.json()["participantIdentity"]
    assert dispatch.await_args.kwargs["salon_id"] == str(active_salon.id)


def test_the_guests_room_holds_exactly_the_guest_and_their_agent(
    client, db, host, active_salon
):
    from unittest.mock import AsyncMock, patch

    host_user, _ = host
    inv = _make_invitation(db, host_user, active_salon)

    with patch(
        "src.routers.invitations.livekit_service.create_room", new_callable=AsyncMock
    ) as create_room:
        client.get(f"/invitations/guest-join/{inv.join_token}")

    assert create_room.await_args.kwargs["max_participants"] == 2


def test_guest_join_requires_no_authentication(client, db, host, active_salon):
    """Endpoint must be accessible without any Authorization header."""
    host_user, _ = host
    inv = _make_invitation(db, host_user, active_salon)
    resp = client.get(f"/invitations/guest-join/{inv.join_token}")
    assert resp.status_code == 200


# ─── One-time use ─────────────────────────────────────────────────────────────
#
# The token survives the fetch on purpose: it is spent at confirm, once the guest's
# microphone is genuinely working. A guest whose first browser cannot reach a microphone —
# a mail app's embedded webview, typically — reopens the same link elsewhere instead of
# asking the host for a fresh one.


def test_fetching_credentials_does_not_spend_the_token(client, db, host, active_salon):
    """Opening the page must not burn the link — only a working microphone does."""
    host_user, _ = host
    inv = _make_invitation(db, host_user, active_salon)
    client.get(f"/invitations/guest-join/{inv.join_token}")
    db.expire(inv)
    db.refresh(inv)
    assert inv.status == "pending"


def test_confirm_spends_the_token(client, db, host, active_salon):
    """The confirm call is what the page makes once the microphone is live."""
    host_user, _ = host
    inv = _make_invitation(db, host_user, active_salon)
    client.get(f"/invitations/guest-join/{inv.join_token}")
    resp = client.post(f"/invitations/guest-join/{inv.join_token}/confirm")
    assert resp.status_code == 200
    db.expire(inv)
    db.refresh(inv)
    assert inv.status == "accepted"

    # And the link is spent for good.
    assert client.get(f"/invitations/guest-join/{inv.join_token}").status_code == 410


def test_confirm_returns_a_token_the_guest_can_act_on_the_salon_with(
    client, db, host, active_salon
):
    """The account `register` creates for this guest is real, so its own JWT is what lets
    them add a source or pause the agent the same way the host does — no second credential
    type, the very check every one of those routes already made, just widened."""
    host_user, _ = host
    inv = _make_invitation(db, host_user, active_salon)
    client.get(f"/invitations/guest-join/{inv.join_token}")

    resp = client.post(f"/invitations/guest-join/{inv.join_token}/confirm")

    guest_token = resp.json()["guestToken"]
    assert guest_token

    with patch(
        "src.services.livekit_service.agent_is_present", new_callable=AsyncMock
    ) as present:
        present.return_value = True
        agent_state = client.get(
            f"/salons/{active_salon.id}/agent",
            headers={"Authorization": f"Bearer {guest_token}"},
        )
    assert agent_state.status_code == 200


def test_confirm_links_this_invitation_to_the_account_it_creates(
    client, db, host, active_salon
):
    """`register` finds or creates a person keyed by identifier, but knows nothing of which
    invitation brought them here — without writing it back, the guest-parity check on every
    other route would find no accepted guest to match against, however real the account is."""
    host_user, _ = host
    inv = _make_invitation(db, host_user, active_salon)
    client.get(f"/invitations/guest-join/{inv.join_token}")

    client.post(f"/invitations/guest-join/{inv.join_token}/confirm")

    db.expire(inv)
    db.refresh(inv)
    assert inv.guest_user_id is not None


def test_confirm_is_idempotent(client, db, host, active_salon):
    """A retry or a duplicated call must not throw a connected guest out."""
    host_user, _ = host
    inv = _make_invitation(db, host_user, active_salon)
    client.post(f"/invitations/guest-join/{inv.join_token}/confirm")
    resp = client.post(f"/invitations/guest-join/{inv.join_token}/confirm")
    assert resp.status_code == 200
    assert resp.json()["status"] == "accepted"


def test_link_survives_a_failed_microphone(client, db, host, active_salon):
    """The whole point: no confirm, so the link still opens elsewhere — and comes back to
    the same room and the same agent, not a second pair nobody asked for."""
    from unittest.mock import AsyncMock, patch

    host_user, _ = host
    inv = _make_invitation(db, host_user, active_salon)

    with (
        patch(
            "src.routers.invitations.livekit_service.create_room", new_callable=AsyncMock
        ) as create_room,
        patch(
            "src.routers.invitations.livekit_service.dispatch_agent", new_callable=AsyncMock
        ) as dispatch,
    ):
        # First attempt: page opens, microphone never works, nothing is confirmed.
        first = client.get(f"/invitations/guest-join/{inv.join_token}")
        # Reopened in a real browser — still valid.
        second = client.get(f"/invitations/guest-join/{inv.join_token}")

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["livekitRoomName"] == second.json()["livekitRoomName"]
    create_room.assert_awaited_once()
    dispatch.assert_awaited_once()


def test_guest_join_second_use_returns_410(client, db, host, active_salon):
    """Attempting to reuse an already-used token returns 410 Gone."""
    host_user, _ = host
    inv = _make_invitation(db, host_user, active_salon, status="accepted")
    resp = client.get(f"/invitations/guest-join/{inv.join_token}")
    assert resp.status_code == 410
    assert "already been used" in resp.json()["detail"]


def test_second_fetch_blocked_once_confirmed(client, db, host, active_salon):
    """Reuse is refused after confirmation, not before.

    Between fetch and confirm the link stays open, which is what lets a guest retry in
    another browser. Two people getting that far at once is bounded elsewhere: the LiveKit
    identity is derived from the invitation, so the second connection displaces the first.
    """
    host_user, _ = host
    token = secrets.token_urlsafe(32)
    _make_invitation(db, host_user, active_salon, token=token)
    assert client.get(f"/invitations/guest-join/{token}").status_code == 200
    client.post(f"/invitations/guest-join/{token}/confirm")
    assert client.get(f"/invitations/guest-join/{token}").status_code == 410


# ─── Error cases ──────────────────────────────────────────────────────────────

def test_guest_join_unknown_token_returns_404(client):
    """Unknown token returns 404 Not Found."""
    resp = client.get(f"/invitations/guest-join/{secrets.token_urlsafe(32)}")
    assert resp.status_code == 404


def test_guest_join_expired_token_returns_410(client, db, host, active_salon):
    """Expired token returns 410 Gone."""
    host_user, _ = host
    inv = _make_invitation(db, host_user, active_salon, expired=True)
    resp = client.get(f"/invitations/guest-join/{inv.join_token}")
    assert resp.status_code == 410
    assert "expired" in resp.json()["detail"]


def test_guest_join_ended_salon_returns_410(client, db, host):
    """Token for an ended salon returns 410."""
    host_user, _ = host
    sess = Salon(
        host_user_id=host_user.id,
        livekit_room_name="salon-ended-guest",
        source_type="url",
        source_content="content",
        status="ended",
        ended_at=datetime.now(tz=timezone.utc),
    )
    db.add(sess)
    db.commit()
    db.refresh(sess)
    inv = _make_invitation(db, host_user, sess)
    resp = client.get(f"/invitations/guest-join/{inv.join_token}")
    assert resp.status_code == 410
    assert "no longer available" in resp.json()["detail"]


# ─── Web page ─────────────────────────────────────────────────────────────────

def test_guest_web_page_returns_html(client):
    """GET /join/{token} serves the HTML page (no auth, any token value)."""
    resp = client.get(f"/join/{secrets.token_urlsafe(32)}")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]


def test_guest_web_page_contains_badge(client):
    """Served HTML contains the no-install badge, in the default language.

    The markup is English and French comes from the page's own dictionary, so the badge
    that ships in the HTML is the English one. Both are asserted: the French string is
    what a guest sees after using the switch, and losing it would be a silent regression.
    """
    resp = client.get(f"/join/{secrets.token_urlsafe(32)}")
    assert "No install" in resp.text
    assert "Sans installation" in resp.text


def test_guest_web_page_is_responsive(client):
    """HTML contains a responsive viewport meta tag."""
    resp = client.get(f"/join/{secrets.token_urlsafe(32)}")
    assert "viewport" in resp.text
    assert "width=device-width" in resp.text


# ─── Story 3.2: clean disconnect on browser close ─────────────────────────────

def test_guest_web_page_handles_beforeunload(client):
    """HTML registers a beforeunload listener to disconnect cleanly on tab close."""
    resp = client.get(f"/join/{secrets.token_urlsafe(32)}")
    assert "beforeunload" in resp.text


def test_guest_web_page_handles_pagehide(client):
    """HTML registers a pagehide listener (reliable mobile fallback for tab close)."""
    resp = client.get(f"/join/{secrets.token_urlsafe(32)}")
    assert "pagehide" in resp.text


def test_guest_web_page_disconnect_nulls_room(client):
    """Unload handler sets room to null after disconnect to prevent double-disconnect."""
    resp = client.get(f"/join/{secrets.token_urlsafe(32)}")
    # The onPageUnload function should null out the room reference
    assert "room = null" in resp.text


# ─── Host console page ───────────────────────────────────────────────────────

def test_host_console_is_served(client):
    """The host console is the only surface that can add a source mid-salon today."""
    resp = client.get("/host")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "Console hôte" in resp.text
