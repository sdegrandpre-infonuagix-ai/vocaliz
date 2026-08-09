"""Tests for Story 3.5 — anonymous guest conversion to registered user."""
import secrets
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from src.models.invitation import Invitation
from src.models.salon import Salon
from src.models.user import User
from src.services import invitation_service


# ─── Fixtures ────────────────────────────────────────────────────────────────

GUEST_EMAIL = "guest@example.com"


@pytest.fixture
def host(db):
    u = User(email="host@example.com", phone_number="+15147770002")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


@pytest.fixture
def salon_for_host(db, host):
    sess = Salon(
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


def _make_anonymous_invitation(db, host, salon, *, email=GUEST_EMAIL, status="accepted"):
    inv = Invitation(
        salon_id=salon.id,
        host_user_id=host.id,
        guest_email=email,
        guest_user_id=None,
        invitation_type="email_contact",
        join_token=secrets.token_urlsafe(32),
        status=status,
        expires_at=datetime.now(tz=timezone.utc) + timedelta(hours=24),
    )
    db.add(inv)
    db.commit()
    db.refresh(inv)
    return inv


# ─── link_prior_invitations unit tests ───────────────────────────────────────

def test_link_prior_invitations_sets_guest_user_id(db, host, salon_for_host):
    """When an anonymous guest registers, their prior invitations are linked."""
    inv = _make_anonymous_invitation(db, host, salon_for_host)
    assert inv.guest_user_id is None

    new_user = User(email=GUEST_EMAIL)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    assert invitation_service.link_prior_invitations(new_user, db) == 1

    db.expire(inv)
    db.refresh(inv)
    assert inv.guest_user_id == new_user.id


def test_link_prior_invitations_returns_count(db, host, salon_for_host):
    """Returns the number of invitations linked."""
    sess2 = Salon(
        host_user_id=host.id,
        livekit_room_name="salon-conv-room-2",
        source_type="url",
        source_content="c",
        status="ended",
    )
    db.add(sess2)
    db.commit()
    db.refresh(sess2)

    _make_anonymous_invitation(db, host, salon_for_host)
    _make_anonymous_invitation(db, host, sess2)

    new_user = User(email=GUEST_EMAIL)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    assert invitation_service.link_prior_invitations(new_user, db) == 2


def test_link_prior_invitations_ignores_already_linked(db, host, salon_for_host):
    """Invitations already linked to a user are not double-linked."""
    new_user = User(email=GUEST_EMAIL)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    inv = Invitation(
        salon_id=salon_for_host.id,
        host_user_id=host.id,
        guest_email=GUEST_EMAIL,
        guest_user_id=new_user.id,
        invitation_type="email_contact",
        join_token=secrets.token_urlsafe(32),
        status="accepted",
        expires_at=datetime.now(tz=timezone.utc) + timedelta(hours=24),
    )
    db.add(inv)
    db.commit()

    assert invitation_service.link_prior_invitations(new_user, db) == 0


def test_link_prior_invitations_other_address_not_affected(db, host, salon_for_host):
    """Invitations addressed to someone else are not linked."""
    _make_anonymous_invitation(db, host, salon_for_host, email="someone.else@example.com")

    new_user = User(email=GUEST_EMAIL)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    assert invitation_service.link_prior_invitations(new_user, db) == 0


def test_link_prior_invitations_no_prior_salons_returns_zero(db):
    """User with no prior anonymous invitations: returns 0, no error."""
    new_user = User(email=GUEST_EMAIL)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    assert invitation_service.link_prior_invitations(new_user, db) == 0


# ─── Integration: OTP verify triggers conversion ──────────────────────────────

def test_email_signup_links_anonymous_participation(client, db, host, salon_for_host):
    """Signing up reattaches the guest's earlier anonymous salon.

    This is what inviting by email restored: the invitation and the account are keyed on
    the same address, so the correlation always exists. While invitations were addressed
    to phone numbers, an email-only sign-up had no key to match on and this could not
    work at all.
    """
    inv = _make_anonymous_invitation(db, host, salon_for_host)

    with patch("src.services.otp._send_email"):
        client.post("/auth/otp/request", json={"email": GUEST_EMAIL, "name": "Seb"})

    user = db.query(User).filter(User.email == GUEST_EMAIL).first()
    assert user is not None

    resp = client.post("/auth/otp/verify", json={"email": GUEST_EMAIL, "code": user.otp_code})
    assert resp.status_code == 200
    assert "token" in resp.json()

    db.expire(inv)
    db.refresh(inv)
    assert inv.guest_user_id == user.id


def test_conversion_is_case_insensitive(client, db, host, salon_for_host):
    """An invitation sent to a differently-cased address still links.

    Both sides are normalised on the way in, so casing cannot silently orphan a guest.
    """
    inv = _make_anonymous_invitation(db, host, salon_for_host, email="guest@example.com")

    with patch("src.services.otp._send_email"):
        client.post("/auth/otp/request", json={"email": "GUEST@Example.COM", "name": "Seb"})

    user = db.query(User).filter(User.email == GUEST_EMAIL).first()
    assert user is not None

    client.post("/auth/otp/verify", json={"email": GUEST_EMAIL, "code": user.otp_code})
    db.expire(inv)
    db.refresh(inv)
    assert inv.guest_user_id == user.id
