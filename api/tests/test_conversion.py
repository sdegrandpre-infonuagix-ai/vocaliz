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
    u = User(email="15147770002@example.com", phone_number="+15147770002")
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

    new_user = User(email=GUEST_PHONE + "@example.com", phone_number=GUEST_PHONE)
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

    new_user = User(email=GUEST_PHONE + "@example.com", phone_number=GUEST_PHONE)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    count = invitation_service.link_prior_invitations(new_user, db)
    assert count == 2


def test_link_prior_invitations_ignores_already_linked(db, host, session_for_host):
    """Invitations already linked to a user are not double-linked."""
    new_user = User(email=GUEST_PHONE + "@example.com", phone_number=GUEST_PHONE)
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

    new_user = User(email=GUEST_PHONE + "@example.com", phone_number=GUEST_PHONE)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    count = invitation_service.link_prior_invitations(new_user, db)
    assert count == 0


def test_link_prior_invitations_no_prior_sessions_returns_zero(db):
    """User with no prior anonymous invitations: returns 0, no error."""
    new_user = User(email=GUEST_PHONE + "@example.com", phone_number=GUEST_PHONE)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    count = invitation_service.link_prior_invitations(new_user, db)
    assert count == 0


# ─── Integration: OTP verify triggers conversion ──────────────────────────────

GUEST_EMAIL = "guest@example.com"


def test_email_signup_alone_cannot_link_anonymous_participation(
    client, db, host, session_for_host
):
    """Sign-up is email-only, so a fresh account has no phone to correlate on.

    The anonymous invitation was addressed to a phone number; nothing on the new
    account points back to it, so Story 3.5 conversion cannot fire on sign-up alone.
    """
    inv = _make_anonymous_invitation(db, host, session_for_host)

    with patch("src.services.otp._send_email"):
        client.post("/auth/otp/request", json={"email": GUEST_EMAIL})

    user = db.query(User).filter(User.email == GUEST_EMAIL).first()
    assert user is not None
    assert user.phone_number is None

    resp = client.post("/auth/otp/verify", json={"email": GUEST_EMAIL, "code": user.otp_code})
    assert resp.status_code == 200
    assert "token" in resp.json()

    db.expire(inv)
    db.refresh(inv)
    assert inv.guest_user_id is None


def test_linking_works_once_the_account_carries_the_phone(db, host, session_for_host):
    """Adding the phone number to the account restores the correlation key."""
    inv = _make_anonymous_invitation(db, host, session_for_host)

    user = User(email=GUEST_EMAIL)
    db.add(user)
    db.commit()
    db.refresh(user)
    assert invitation_service.link_prior_invitations(user, db) == 0

    user.phone_number = GUEST_PHONE
    db.commit()

    assert invitation_service.link_prior_invitations(user, db) == 1
    db.refresh(inv)
    assert inv.guest_user_id == user.id
