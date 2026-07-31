"""Tests for follow-up install-link SMS to anonymous guests (Story 3.4)."""
import secrets
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from src.models.invitation import Invitation
from src.models.session import SessionModel
from src.models.user import User
from src.services import invitation_service
from src.services.jwt_service import issue_token


# ─── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def host(db):
    u = User(email="15146660001@example.com", phone_number="+15146660001")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u, issue_token(str(u.id))


@pytest.fixture
def active_session(db, host):
    host_user, _ = host
    sess = SessionModel(
        host_user_id=host_user.id,
        livekit_room_name="salon-followup-room",
        source_type="url",
        source_url="https://example.com",
        source_content="content",
        status="active",
    )
    db.add(sess)
    db.commit()
    db.refresh(sess)
    return sess


def _add_invitation(db, host_user, session, *, inv_type="sms_contact", status="accepted", phone=None):
    inv = Invitation(
        session_id=session.id,
        host_user_id=host_user.id,
        guest_phone=phone or "+15146669999",
        guest_user_id=None,
        invitation_type=inv_type,
        join_token=secrets.token_urlsafe(32),
        status=status,
        expires_at=datetime.now(tz=timezone.utc) + timedelta(hours=24),
    )
    db.add(inv)
    db.commit()
    db.refresh(inv)
    return inv


# ─── send_followup_sms_to_guests unit tests ───────────────────────────────────

def test_followup_sms_sent_to_accepted_sms_contact(db, host, active_session):
    """Accepted sms_contact invitations receive the install-link SMS."""
    host_user, _ = host
    inv = _add_invitation(db, host_user, active_session)

    with patch("src.services.invitation_service.boto3") as mock_boto3:
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client
        count = invitation_service.send_followup_sms_to_guests(str(active_session.id), db)

    assert count == 1
    mock_client.publish.assert_called_once()
    call_kwargs = mock_client.publish.call_args[1]
    assert call_kwargs["PhoneNumber"] == inv.guest_phone
    assert "salon.app/install" in call_kwargs["Message"]


def test_followup_sms_message_contains_install_url(db, host, active_session):
    """The follow-up SMS body contains the install URL."""
    host_user, _ = host
    _add_invitation(db, host_user, active_session)

    with patch("src.services.invitation_service.boto3") as mock_boto3:
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client
        invitation_service.send_followup_sms_to_guests(str(active_session.id), db)

    msg = mock_client.publish.call_args[1]["Message"]
    assert "install" in msg.lower() or "salon.app" in msg


def test_followup_sms_not_sent_to_pending_invitation(db, host, active_session):
    """Pending (unused) invitations do NOT receive follow-up SMS."""
    host_user, _ = host
    _add_invitation(db, host_user, active_session, status="pending")

    with patch("src.services.invitation_service.boto3") as mock_boto3:
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client
        count = invitation_service.send_followup_sms_to_guests(str(active_session.id), db)

    assert count == 0
    mock_client.publish.assert_not_called()


def test_followup_sms_not_sent_to_salon_friend(db, host, active_session):
    """In-app (salon_friend) invitations do NOT receive follow-up SMS."""
    host_user, _ = host
    _add_invitation(db, host_user, active_session, inv_type="salon_friend")

    with patch("src.services.invitation_service.boto3") as mock_boto3:
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client
        count = invitation_service.send_followup_sms_to_guests(str(active_session.id), db)

    assert count == 0
    mock_client.publish.assert_not_called()


def test_followup_sms_returns_zero_for_no_guests(db, host, active_session):
    """Sessions with no accepted sms_contact invitations return count 0."""
    host_user, _ = host
    count = invitation_service.send_followup_sms_to_guests(str(active_session.id), db)
    assert count == 0


def test_followup_sms_individual_failure_does_not_abort(db, host, active_session):
    """An SNS error on one guest does not raise — returns partial count."""
    host_user, _ = host
    _add_invitation(db, host_user, active_session, phone="+15146661111")
    _add_invitation(db, host_user, active_session, phone="+15146662222")

    with patch("src.services.invitation_service.boto3") as mock_boto3:
        mock_client = MagicMock()
        mock_client.publish.side_effect = [Exception("SNS error"), None]
        mock_boto3.client.return_value = mock_client
        count = invitation_service.send_followup_sms_to_guests(str(active_session.id), db)

    # One failed, one succeeded
    assert count == 1


# ─── Integration: end_session triggers follow-up SMS ─────────────────────────

def test_end_session_triggers_followup_sms(client, db, host, active_session):
    """POST /sessions/{id}/end sends follow-up SMS to accepted sms_contact guests."""
    host_user, token = host
    _add_invitation(db, host_user, active_session)

    with patch("src.services.invitation_service.boto3") as mock_boto3:
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client

        resp = client.post(
            f"/sessions/{active_session.id}/end",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert resp.status_code == 200
    # SMS should have been attempted for the accepted guest
    assert mock_client.publish.call_count >= 1


def test_end_session_succeeds_even_if_sms_fails(client, db, host, active_session):
    """Session end returns 200 even if follow-up SMS encounters an error."""
    host_user, token = host
    _add_invitation(db, host_user, active_session)

    with patch("src.services.invitation_service.boto3") as mock_boto3:
        mock_client = MagicMock()
        mock_client.publish.side_effect = Exception("SNS unavailable")
        mock_boto3.client.return_value = mock_client

        resp = client.post(
            f"/sessions/{active_session.id}/end",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert resp.status_code == 200
    assert resp.json()["status"] == "ended"
