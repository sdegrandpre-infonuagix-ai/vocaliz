"""POST /orchestrator/wake — the one call that goes the other way.

Every other route in `orchestrator_relay.py` forwards an agent's call into the orchestrator;
this is the orchestrator calling in, to say a served participant is owed something. There is
no participant-scoped token for it — the caller is not a participant, it is the one
orchestrator instance holding this Salon — so it is authorised by a shared secret instead,
and every test here is either about that secret or about finding the right room to wake.
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from src.config import settings
from src.models.invitation import Invitation
from src.models.salon import Salon
from src.models.user import User

SECRET = "orchestrator-shared-secret"


@pytest.fixture(autouse=True)
def callback_secret(monkeypatch):
    monkeypatch.setattr(settings, "orchestrator_callback_secret", SECRET)


@pytest.fixture
def host(db):
    person = User(email="wakehost@example.com")
    db.add(person)
    db.commit()
    db.refresh(person)
    return person


@pytest.fixture
def salon(db, host):
    made = Salon(
        host_user_id=host.id,
        livekit_room_name="room-host-abc",
        source_type="none",
    )
    db.add(made)
    db.commit()
    db.refresh(made)
    return made


def _auth(secret=SECRET):
    return {"Authorization": f"Bearer {secret}"}


def _notify_mock():
    return patch(
        "src.routers.orchestrator_relay.livekit_service.notify_room", new_callable=AsyncMock
    )


# ── Authorisation ────────────────────────────────────────────────────────────────


def test_the_right_secret_is_accepted(client, salon):
    with _notify_mock() as notify:
        resp = client.post(
            "/orchestrator/wake",
            json={"salonId": str(salon.id), "participantId": str(salon.host_user_id)},
            headers=_auth(),
        )
    assert resp.status_code == 200
    notify.assert_awaited_once()


def test_the_wrong_secret_is_refused(client, salon):
    resp = client.post(
        "/orchestrator/wake",
        json={"salonId": str(salon.id), "participantId": str(salon.host_user_id)},
        headers=_auth("not-it"),
    )
    assert resp.status_code == 401


def test_no_secret_configured_refuses_every_call(client, salon, monkeypatch):
    """The safe default: a wake nobody can send is a missed shortcut, never a Salon
    anybody can reach into."""
    monkeypatch.setattr(settings, "orchestrator_callback_secret", "")
    resp = client.post(
        "/orchestrator/wake",
        json={"salonId": str(salon.id), "participantId": str(salon.host_user_id)},
        headers=_auth(),
    )
    assert resp.status_code == 503


def test_missing_credentials_are_refused(client, salon):
    resp = client.post(
        "/orchestrator/wake",
        json={"salonId": str(salon.id), "participantId": str(salon.host_user_id)},
    )
    assert resp.status_code in (401, 403)


# ── Finding the right room ────────────────────────────────────────────────────────


def test_the_host_is_woken_in_their_own_room(client, salon):
    with _notify_mock() as notify:
        client.post(
            "/orchestrator/wake",
            json={"salonId": str(salon.id), "participantId": str(salon.host_user_id)},
            headers=_auth(),
        )
    notify.assert_awaited_once_with("room-host-abc", {"action": "journal_wake"})


def test_a_guest_linked_to_an_account_is_woken_in_their_own_room(client, db, salon, host):
    guest = User(email="wakeguest@example.com")
    db.add(guest)
    db.commit()
    db.refresh(guest)
    invitation = Invitation(
        salon_id=salon.id,
        host_user_id=host.id,
        guest_email=guest.email,
        guest_user_id=guest.id,
        invitation_type="email_contact",
        join_token="tok-wake-1",
        status="accepted",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        livekit_room_name="room-guest-linked",
    )
    db.add(invitation)
    db.commit()

    with _notify_mock() as notify:
        resp = client.post(
            "/orchestrator/wake",
            json={"salonId": str(salon.id), "participantId": str(guest.id)},
            headers=_auth(),
        )
    assert resp.status_code == 200
    notify.assert_awaited_once_with("room-guest-linked", {"action": "journal_wake"})


def test_an_anonymous_guest_is_woken_by_their_derived_identity(client, db, salon, host):
    invitation = Invitation(
        salon_id=salon.id,
        host_user_id=host.id,
        guest_email="anon@example.com",
        invitation_type="email_contact",
        join_token="tok-wake-2",
        status="accepted",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        livekit_room_name="room-guest-anon",
    )
    db.add(invitation)
    db.commit()
    db.refresh(invitation)

    with _notify_mock() as notify:
        resp = client.post(
            "/orchestrator/wake",
            json={"salonId": str(salon.id), "participantId": f"guest-{invitation.id}"},
            headers=_auth(),
        )
    assert resp.status_code == 200
    notify.assert_awaited_once_with("room-guest-anon", {"action": "journal_wake"})


def test_an_unknown_participant_is_refused(client, salon):
    with _notify_mock() as notify:
        resp = client.post(
            "/orchestrator/wake",
            json={"salonId": str(salon.id), "participantId": "nobody-here"},
            headers=_auth(),
        )
    assert resp.status_code == 404
    notify.assert_not_awaited()


def test_an_unknown_salon_is_refused(client):
    import uuid

    with _notify_mock() as notify:
        resp = client.post(
            "/orchestrator/wake",
            json={"salonId": str(uuid.uuid4()), "participantId": "anybody"},
            headers=_auth(),
        )
    assert resp.status_code == 404
    notify.assert_not_awaited()
