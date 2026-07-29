"""Tests for Story 3.5 — anonymous guest conversion to registered user."""
import secrets
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from src.models.invitation import Invitation
from src.models.session import SessionModel
from src.models.user import User
from src.services import invitation_service


# ─── Fixtures ────────────────────────────────────────────────────────────────

GUEST_PHONE = "+15147770001"


@pytest.fixture
def host(db):
    u = User(phone_number="+15147770002")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


@pytest.fixture
def session_for_host(db, host):
    sess = SessionModel(
        host_user_id=host.id,
        livekit_room_name="salon-conversion-room",
        source_type="url",
        source_content="content",
        status="ended",
    )
    db.add(sess)
    db.commit()
    db.refresh(sess)
    return sess


def _make_anonymous_invitation(db, host, session, *, phone=GUEST_PHONE, status="accepted"):
    inv = Invitation(
        session_id=session.id,
        host_user_id=host.id,
        guest_phone=phone,
        guest_user_id=None,
        invitation_type="sms_contact",
        join_token=secrets.token_urlsafe(32),
        status=status,
        expires_at=datetime.now(tz=timezone.utc) + timedelta(hours=24),
    )
    db.add(inv)
    db.commit()
    db.refresh(inv)
    return inv


# ─── link_prior_invitations unit tests ───────────────────────────────────────

def test_link_prior_invitations_sets_guest_user_id(db, host, session_for_host):
    """When an anonymous guest registers, their prior invitations are linked."""
    inv = _make_anonymous_invitation(db, host, session_for_host)
    assert inv.guest_user_id is None

    new_user = User(phone_number=GUEST_PHONE)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    count = invitation_service.link_prior_invitations(new_user, db)
    assert count == 1

    db.expire(inv)
    db.refresh(inv)
    assert inv.guest_user_id == new_user.id


def test_link_prior_invitations_returns_count(db, host, session_for_host):
    """Returns the number of invitations linked."""
    sess2 = SessionModel(
        host_user_id=host.id,
        livekit_room_name="salon-conv-room-2",
        source_type="url",
        source_content="c",
        status="ended",
    )
    db.add(sess2)
    db.commit()
    db.refresh(sess2)

    _make_anonymous_invitation(db, host, session_for_host)
    _make_anonymous_invitation(db, host, sess2)

    new_user = User(phone_number=GUEST_PHONE)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    count = invitation_service.link_prior_invitations(new_user, db)
    assert count == 2


def test_link_prior_invitations_ignores_already_linked(db, host, session_for_host):
    """Invitations already linked to a user are not double-linked."""
    new_user = User(phone_number=GUEST_PHONE)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    # Invitation already has guest_user_id set
    inv = Invitation(
        session_id=session_for_host.id,
        host_user_id=host.id,
        guest_phone=GUEST_PHONE,
        guest_user_id=new_user.id,
        invitation_type="sms_contact",
        join_token=secrets.token_urlsafe(32),
        status="accepted",
        expires_at=datetime.now(tz=timezone.utc) + timedelta(hours=24),
    )
    db.add(inv)
    db.commit()

    count = invitation_service.link_prior_invitations(new_user, db)
    assert count == 0


def test_link_prior_invitations_different_phone_not_affected(db, host, session_for_host):
    """Invitations for a different phone number are not linked."""
    _make_anonymous_invitation(db, host, session_for_host, phone="+15147779999")

    new_user = User(phone_number=GUEST_PHONE)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    count = invitation_service.link_prior_invitations(new_user, db)
    assert count == 0


def test_link_prior_invitations_no_prior_sessions_returns_zero(db):
    """User with no prior anonymous invitations: returns 0, no error."""
    new_user = User(phone_number=GUEST_PHONE)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    count = invitation_service.link_prior_invitations(new_user, db)
    assert count == 0


# ─── Integration: OTP verify triggers conversion ──────────────────────────────

def test_verify_otp_links_anonymous_invitations(client, db, host, session_for_host):
    """POST /auth/otp/verify links prior anonymous invitations for the new user."""
    inv = _make_anonymous_invitation(db, host, session_for_host)

    with patch("src.services.otp.boto3") as mock_boto3:
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client
        # Request OTP to create the user record
        client.post("/auth/otp/request", json={"phoneNumber": GUEST_PHONE})

    # Get the OTP code from the DB
    user = db.query(User).filter(User.phone_number == GUEST_PHONE).first()
    assert user is not None
    code = user.otp_code

    # Verify OTP — this triggers conversion
    resp = client.post("/auth/otp/verify", json={"phoneNumber": GUEST_PHONE, "code": code})
    assert resp.status_code == 200
    body = resp.json()
    assert "token" in body

    # Anonymous invitation should now be linked to the registered user
    db.expire(inv)
    db.refresh(inv)
    registered_user = db.query(User).filter(User.phone_number == GUEST_PHONE).first()
    assert inv.guest_user_id == registered_user.id
