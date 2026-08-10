"""Tests for the invitation endpoints (Story 2.2)."""
import uuid
from unittest.mock import patch

import pytest

from src.models.salon import Salon
from src.models.user import User
from src.services.jwt_service import issue_token


# ─── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def host(db):
    u = User(email="15141111111@example.com", phone_number="+15141111111")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u, issue_token(str(u.id))


@pytest.fixture
def guest_user(db):
    """A registered Salon user who can receive in-app invitations."""
    u = User(email="15142222222@example.com", phone_number="+15142222222")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


@pytest.fixture
def active_salon(db, host):
    host_user, _ = host
    sess = Salon(
        host_user_id=host_user.id,
        livekit_room_name="salon-test-room",
        source_type="url",
        source_url="https://example.com",
        source_content="content",
        status="active",
    )
    db.add(sess)
    db.commit()
    db.refresh(sess)
    return sess


# ─── Auth guard ──────────────────────────────────────────────────────────────

def test_invite_requires_auth(client, active_salon):
    resp = client.post(
        f"/salons/{active_salon.id}/invitations",
        json={"guestEmail": "15143333333@example.com"},
    )
    assert resp.status_code == 401


def test_list_invitations_requires_auth(client):
    resp = client.get("/me/invitations")
    assert resp.status_code == 401


# ─── Phone validation ────────────────────────────────────────────────────────

def test_invite_rejects_invalid_phone(client, host, active_salon):
    _, token = host
    resp = client.post(
        f"/salons/{active_salon.id}/invitations",
        json={"guestEmail": "not-an-email"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


# ─── Salon ownership ───────────────────────────────────────────────────────

def test_invite_wrong_salon_returns_404(client, db, host):
    _, token = host
    resp = client.post(
        f"/salons/{uuid.uuid4()}/invitations",
        json={"guestEmail": "15143333333@example.com"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


# ─── A host cannot invite themselves ─────────────────────────────────────────
#
# An invitation addressed to the host's own email or phone resolves, on the guest's side,
# to the host's own account UUID (`livekit_service.identity_for`) — the identity the host's
# own room already registered with the orchestrator. `Salon.join()` treats a second join
# under it as that same seat reconnecting, not a new participant: no seat, no script, no
# journal entry ever reaches the "guest", who is really just the host's own room a second
# time. Reported live as "the guest can't send to the salon" and "the guest can't hear the
# agent" — both true, since there was never a second room to deliver either into.

def test_inviting_the_hosts_own_email_is_refused(client, host, active_salon):
    host_user, token = host
    resp = client.post(
        f"/salons/{active_salon.id}/invitations",
        json={"guestEmail": host_user.email},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400
    assert "own" in resp.json()["detail"].lower()


def test_inviting_the_hosts_own_email_case_insensitively_is_refused(client, host, active_salon):
    host_user, token = host
    resp = client.post(
        f"/salons/{active_salon.id}/invitations",
        json={"guestEmail": host_user.email.upper()},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400


def test_inviting_the_hosts_own_phone_is_refused(client, host, active_salon):
    host_user, token = host
    resp = client.post(
        f"/salons/{active_salon.id}/invitations",
        json={"guestPhone": host_user.phone_number},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400


@patch("src.services.invitation_service._send_invitation_email")
def test_a_genuinely_different_guest_is_still_accepted(mock_send, client, host, active_salon):
    """The check must not become so broad it refuses an ordinary invitation."""
    _, token = host
    resp = client.post(
        f"/salons/{active_salon.id}/invitations",
        json={"guestEmail": "someoneelse@example.com"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201


# ─── SMS contact (unregistered phone) ────────────────────────────────────────

@patch("src.services.invitation_service._send_invitation_email")
def test_invite_sms_contact(mock_sms, client, host, active_salon):
    _, token = host
    resp = client.post(
        f"/salons/{active_salon.id}/invitations",
        json={"guestEmail": "15149999999@example.com"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["invitationType"] == "email_contact"
    assert data["status"] == "pending"
    assert data["joinLink"] is not None
    assert "/join/" in data["joinLink"]
    mock_sms.assert_called_once()


# ─── Salon friend (registered user) ──────────────────────────────────────────

@patch("src.services.invitation_service._send_invitation_email")
def test_invite_salon_friend(mock_sms, client, host, active_salon, guest_user):
    _, token = host
    resp = client.post(
        f"/salons/{active_salon.id}/invitations",
        json={"guestEmail": guest_user.email},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["invitationType"] == "salon_friend"
    # A registered friend still gets a link: the token works for browser join whatever the
    # type, and the host may well need to share it — the in-app notification is an extra
    # channel, not a reason to withhold the link.
    assert "/join/" in data["joinLink"]
    # And an email, like everyone else. This test previously asserted the opposite. The
    # in-app notification only reaches a member who opens the app, which is no way to
    # reach someone about a conversation happening right now.
    mock_sms.assert_called_once()
    assert data["emailSent"] is True


@patch("src.services.invitation_service._send_invitation_email")
def test_email_can_be_resent_to_salon_friend(mock_send, client, host, active_salon, guest_user):
    """Resending to a registered member used to be refused with a 409."""
    _, token = host
    headers = {"Authorization": f"Bearer {token}"}

    created = client.post(
        f"/salons/{active_salon.id}/invitations",
        json={"guestEmail": guest_user.email},
        headers=headers,
    ).json()
    assert created["invitationType"] == "salon_friend"

    mock_send.reset_mock()
    resp = client.post(
        f"/salons/{active_salon.id}/invitations/{created['invitationId']}/email",
        headers=headers,
    )
    assert resp.status_code == 200
    mock_send.assert_called_once()


# ─── Idempotency ─────────────────────────────────────────────────────────────

@patch("src.services.invitation_service._send_invitation_email")
def test_invite_idempotent_within_5_min(mock_sms, client, host, active_salon):
    _, token = host
    payload = {"guestEmail": "15149999999@example.com"}
    headers = {"Authorization": f"Bearer {token}"}

    r1 = client.post(f"/salons/{active_salon.id}/invitations", json=payload, headers=headers)
    r2 = client.post(f"/salons/{active_salon.id}/invitations", json=payload, headers=headers)

    assert r1.status_code == 201
    assert r2.status_code == 201
    # Idempotent on the token: no second invitation, no second one-time link.
    assert r1.json()["invitationId"] == r2.json()["invitationId"]
    assert r1.json()["joinLink"] == r2.json()["joinLink"]
    # But the email goes out again — repeating the invitation is how a host says the
    # first one never arrived. This previously asserted a single send.
    assert mock_sms.call_count == 2
    assert r2.json()["emailSent"] is True


# ─── A failed send keeps the invitation ──────────────────────────────────────

@patch("src.services.invitation_service._send_invitation_email", side_effect=__import__('fastapi').HTTPException(503, "SES unavailable"))
def test_invite_keeps_invitation_when_email_fails(mock_send, client, host, active_salon, db):
    """This test previously asserted the opposite — a 503 and no invitation row.

    Rolling back was wrong: the join link works over any channel, so discarding it
    because one channel failed left the host with nothing to share. The invitation is
    kept, the link is returned, and emailSent reports the failure.
    """
    from src.models.invitation import Invitation
    _, token = host
    resp = client.post(
        f"/salons/{active_salon.id}/invitations",
        json={"guestEmail": "15149999999@example.com"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    assert resp.json()["emailSent"] is False
    assert resp.json()["joinLink"]
    assert db.query(Invitation).count() == 1


# ─── GET /me/invitations ─────────────────────────────────────────────────────

@patch("src.services.invitation_service._send_invitation_email")
def test_list_invitations_returns_salon_friend_invites(mock_sms, client, host, active_salon, guest_user, db):
    host_user, host_token = host
    guest_token = issue_token(str(guest_user.id))

    # Host invites the registered Salon user
    resp = client.post(
        f"/salons/{active_salon.id}/invitations",
        json={"guestEmail": guest_user.email},
        headers={"Authorization": f"Bearer {host_token}"},
    )
    assert resp.status_code == 201

    # Guest polls their pending invitations
    list_resp = client.get("/me/invitations", headers={"Authorization": f"Bearer {guest_token}"})
    assert list_resp.status_code == 200
    invitations = list_resp.json()
    assert len(invitations) == 1
    inv = invitations[0]
    assert inv["livekitRoomName"] == "salon-test-room"
    assert inv["hostPhone"] == host_user.phone_number


@patch("src.services.invitation_service._send_invitation_email")
def test_list_invitations_empty_for_unrelated_user(mock_sms, client, db, host, active_salon, guest_user):
    _, host_token = host
    # Invite the guest
    client.post(
        f"/salons/{active_salon.id}/invitations",
        json={"guestEmail": guest_user.email},
        headers={"Authorization": f"Bearer {host_token}"},
    )
    # A third user sees nothing
    other = User(email="15148888888@example.com", phone_number="+15148888888")
    db.add(other)
    db.commit()
    db.refresh(other)
    other_token = issue_token(str(other.id))

    resp = client.get("/me/invitations", headers={"Authorization": f"Bearer {other_token}"})
    assert resp.status_code == 200
    assert resp.json() == []


# ─── The link must survive a failed email ────────────────────────────────────

@patch("src.services.invitation_service._send_invitation_email")
def test_invitation_survives_failed_email(mock_send, client, host, active_salon):
    """A failed send must still yield the link: the host can then share it by hand.

    Rolling the invitation back destroyed the join link at the exact moment it was most
    needed — and the link works over any channel, not just email.
    """
    from fastapi import HTTPException

    mock_send.side_effect = HTTPException(status_code=503, detail="SES indisponible")
    _, token = host

    resp = client.post(
        f"/salons/{active_salon.id}/invitations",
        json={"guestEmail": "unreachable@example.com"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["joinLink"]
    assert body["emailSent"] is False


@patch("src.services.invitation_service._send_invitation_email")
def test_invitation_reports_successful_delivery(mock_send, client, host, active_salon):
    """emailSent tells the host whether they still need to share the link themselves."""
    _, token = host
    resp = client.post(
        f"/salons/{active_salon.id}/invitations",
        json={"guestEmail": "reachable@example.com"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.json()["emailSent"] is True


@patch("src.services.invitation_service._send_invitation_email")
def test_email_can_be_sent_afterwards(mock_send, client, host, active_salon):
    """Sending is a separate step, and reuses the same token rather than minting one."""
    _, token = host
    headers = {"Authorization": f"Bearer {token}"}

    created = client.post(
        f"/salons/{active_salon.id}/invitations",
        json={"guestEmail": "later@example.com"},
        headers=headers,
    ).json()

    mock_send.reset_mock()
    resp = client.post(
        f"/salons/{active_salon.id}/invitations/{created['invitationId']}/email",
        headers=headers,
    )
    assert resp.status_code == 200
    mock_send.assert_called_once()
    # Same one-time token as the link already shown to the host.
    assert created["joinLink"].endswith(mock_send.call_args.args[1].split("/")[-1])


# ─── Addressable guests ───────────────────────────────────────────────────────

@patch("src.services.invitation_service._send_invitation_email")
def test_invitation_exposes_the_identity_the_guest_will_join_under(
    mock_send, client, host, active_salon
):
    """The whole point: the host holds the guest's room identity before they connect.

    Previously the identity was minted at join time and stored nowhere, so a message
    could only ever be broadcast to the entire room.
    """
    _, token = host
    created = client.post(
        f"/salons/{active_salon.id}/invitations",
        json={"guestEmail": "addressable@example.com"},
        headers={"Authorization": f"Bearer {token}"},
    ).json()

    assert created["participantIdentity"] == f"guest-{created['invitationId']}"

    # And it is the identity actually used when the link is redeemed — the property that
    # makes it addressable. Asserting both ends guards against the format drifting apart.
    join_token = created["joinLink"].rsplit("/", 1)[-1]
    redeemed = client.get(f"/invitations/guest-join/{join_token}")
    assert redeemed.status_code == 200
    assert redeemed.json()["participantIdentity"] == created["participantIdentity"]


@patch("src.services.invitation_service._send_invitation_email")
def test_guest_identity_is_stable_and_distinct_per_invitation(
    mock_send, client, host, active_salon
):
    """Two guests must not collide, and one guest must not change identity."""
    _, token = host
    headers = {"Authorization": f"Bearer {token}"}

    a = client.post(
        f"/salons/{active_salon.id}/invitations",
        json={"guestEmail": "one@example.com"},
        headers=headers,
    ).json()
    b = client.post(
        f"/salons/{active_salon.id}/invitations",
        json={"guestEmail": "two@example.com"},
        headers=headers,
    ).json()

    assert a["participantIdentity"] != b["participantIdentity"]

    # Re-inviting the same address inside the idempotency window reuses the invitation,
    # so the identity the host was given first must not move under them.
    again = client.post(
        f"/salons/{active_salon.id}/invitations",
        json={"guestEmail": "one@example.com"},
        headers=headers,
    ).json()
    assert again["participantIdentity"] == a["participantIdentity"]


@patch("src.services.invitation_service._send_invitation_email")
def test_guest_label_shows_the_identifier_never_the_email(
    mock_send, client, host, active_salon
):
    """A guest is invited by address; that address is not the room's business."""
    _, token = host
    email = "private.person@example.com"
    created = client.post(
        f"/salons/{active_salon.id}/invitations",
        json={"guestEmail": email},
        headers={"Authorization": f"Bearer {token}"},
    ).json()

    label = created["participantName"]
    short = created["invitationId"].replace("-", "")[:4].upper()
    assert label == f"Guest {short}"

    # The label must leak nothing of the address — neither the whole thing nor the part
    # before the @, which is often a real name.
    assert email not in label
    assert email.split("@")[0] not in label.lower()

    # And it is the label actually carried into the room, not just an advertised one.
    join_token = created["joinLink"].rsplit("/", 1)[-1]
    redeemed = client.get(f"/invitations/guest-join/{join_token}").json()
    assert redeemed["participantName"] == label


@patch("src.services.invitation_service._send_invitation_email")
def test_two_guests_get_distinguishable_labels(mock_send, client, host, active_salon):
    """The point of the change: one fixed label told two guests apart from nobody."""
    _, token = host
    headers = {"Authorization": f"Bearer {token}"}
    a = client.post(
        f"/salons/{active_salon.id}/invitations",
        json={"guestEmail": "a@example.com"}, headers=headers,
    ).json()
    b = client.post(
        f"/salons/{active_salon.id}/invitations",
        json={"guestEmail": "b@example.com"}, headers=headers,
    ).json()
    assert a["participantName"] != b["participantName"]


# ─── Transcription notice in the invitation ──────────────────────────────────

@patch("src.services.invitation_service._send_email")
def test_invitation_email_warns_that_speech_is_kept(mock_send):
    """The invitation is the only moment a guest can decline by simply not coming.

    The agent repeats it in the room for anyone who joined without reading, but a notice
    that first appears once you are already talking is not much of a notice.
    """
    from src.services import invitation_service

    invitation_service._send_invitation_email("guest@example.com", "https://x/join/tok")
    body = mock_send.call_args.args[2]
    assert "transcribed and kept" in body
    assert "transcrit et conservé" in body


@patch("src.services.invitation_service._send_email")
def test_the_notice_comes_after_the_link_not_before(mock_send):
    """The link is what the recipient must act on; a legal preamble above it buries it."""
    from src.services import invitation_service

    invitation_service._send_invitation_email("guest@example.com", "https://x/join/tok")
    body = mock_send.call_args.args[2]
    assert body.index("https://x/join/tok") < body.index("transcribed and kept")
