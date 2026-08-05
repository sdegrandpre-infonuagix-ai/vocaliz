"""Tests for POST /sessions/{session_id}/end (Story 2.11)."""
import uuid
from datetime import datetime, timezone

import pytest

from src.models.session import SessionModel
from src.models.user import User
from src.services.jwt_service import issue_token


# ─── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def host(db):
    u = User(email="15143330000@example.com", phone_number="+15143330000")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u, issue_token(str(u.id))


@pytest.fixture
def other_user(db):
    u = User(email="15143331111@example.com", phone_number="+15143331111")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u, issue_token(str(u.id))


@pytest.fixture
def active_session(db, host):
    host_user, _ = host
    sess = SessionModel(
        host_user_id=host_user.id,
        livekit_room_name="salon-end-test-room",
        source_type="url",
        source_url="https://example.com",
        source_content="content",
        status="active",
    )
    db.add(sess)
    db.commit()
    db.refresh(sess)
    return sess


@pytest.fixture
def ended_session(db, host):
    host_user, _ = host
    sess = SessionModel(
        host_user_id=host_user.id,
        livekit_room_name="salon-already-ended",
        source_type="url",
        source_content="content",
        status="ended",
        ended_at=datetime.now(tz=timezone.utc),
    )
    db.add(sess)
    db.commit()
    db.refresh(sess)
    return sess


# ─── Tests ────────────────────────────────────────────────────────────────────

def test_end_session_success(client, host, active_session):
    """Host can end their active session."""
    _, token = host
    resp = client.post(
        f"/sessions/{active_session.id}/end",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["sessionId"] == str(active_session.id)
    assert body["status"] == "ended"
    assert "endedAt" in body
    assert body["endedAt"] is not None


def test_end_session_persists_status(client, host, active_session, db):
    """Session status is persisted as 'ended' in the database."""
    _, token = host
    client.post(
        f"/sessions/{active_session.id}/end",
        headers={"Authorization": f"Bearer {token}"},
    )
    db.expire(active_session)
    db.refresh(active_session)
    assert active_session.status == "ended"
    assert active_session.ended_at is not None


def test_end_session_persists_ended_at_timestamp(client, host, active_session, db):
    """ended_at timestamp is populated and timezone-aware."""
    _, token = host
    before = datetime.now(tz=timezone.utc)
    client.post(
        f"/sessions/{active_session.id}/end",
        headers={"Authorization": f"Bearer {token}"},
    )
    after = datetime.now(tz=timezone.utc)
    db.expire(active_session)
    db.refresh(active_session)
    assert active_session.ended_at is not None
    ts = active_session.ended_at
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    assert before <= ts <= after


def test_end_already_ended_session_returns_409(client, host, ended_session):
    """Calling end on an already-ended session returns 409 Conflict."""
    _, token = host
    resp = client.post(
        f"/sessions/{ended_session.id}/end",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 409
    assert "already ended" in resp.json()["detail"]


def test_end_session_by_non_host_returns_404(client, other_user, active_session):
    """Non-host cannot end someone else's session (returns 404, not 403)."""
    _, token = other_user
    resp = client.post(
        f"/sessions/{active_session.id}/end",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


def test_end_session_unauthenticated_returns_401(client, active_session):
    """Unauthenticated request is rejected."""
    resp = client.post(f"/sessions/{active_session.id}/end")
    assert resp.status_code == 401


def test_end_session_invalid_uuid_returns_404(client, host):
    """Malformed session ID returns 404."""
    _, token = host
    resp = client.post(
        "/sessions/not-a-uuid/end",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


def test_end_session_unknown_uuid_returns_404(client, host):
    """Unknown session UUID returns 404."""
    _, token = host
    resp = client.post(
        f"/sessions/{uuid.uuid4()}/end",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


# ─── Invitations left behind by a salon that is over ──────────────────────────
#
# Ending a salon returned its telephone codes to the pool but left the invitations pending.
# A pending invitation holds its code under a partial unique index, so the pool then offered
# a code that was still owned — and since it hands out its oldest free code first, the same
# value came back on every claim. One abandoned invitation made every invitation in the
# system fail with a 500, for hosts who had never touched that salon.

def _pending_invitation(db, session, *, code, token, email="left@example.com"):
    from datetime import timedelta

    from src.models.invitation import Invitation

    row = Invitation(
        session_id=session.id,
        host_user_id=session.host_user_id,
        guest_email=email,
        guest_phone="",
        invitation_type="email_contact",
        join_token=token,
        phone_pin=code,
        status="pending",
        expires_at=datetime.now(tz=timezone.utc) + timedelta(hours=24),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def test_ending_a_salon_closes_its_unused_invitations(client, host, active_session, db):
    """The root cause. Nobody arrived, so the invitation stays as a record — but it stops
    being pending, and therefore stops holding its code."""
    _, token = host
    invitation = _pending_invitation(db, active_session, code="909090", token="tok-left-909090")

    resp = client.post(
        f"/sessions/{active_session.id}/end", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200

    db.refresh(invitation)
    assert invitation.status == "expired"


def test_the_released_code_is_no_longer_owned_by_anybody(client, host, active_session, db):
    """The two halves have to agree. A code free in the pool while a pending row still holds
    it is the exact state that produced the outage, so this asserts the pair, not the status
    alone."""
    from src.models.salon_code import CodeAvailable
    from src.services import salon_code_service

    _, token = host
    code = salon_code_service.claim(db)
    _pending_invitation(db, active_session, code=code, token="tok-paired")

    client.post(
        f"/sessions/{active_session.id}/end", headers={"Authorization": f"Bearer {token}"}
    )

    assert db.get(CodeAvailable, code).available is True
    # And the pool is now willing to hand it back out, which it was not while the invitation
    # was pending — the guard in the service would have skipped it.
    assert salon_code_service.claim(db) == code


def test_an_invitation_that_was_used_is_left_alone(client, host, active_session, db):
    """Only pending rows are closed. Rewriting an accepted invitation would erase the fact
    that somebody actually joined."""
    _, token = host
    invitation = _pending_invitation(db, active_session, code="808080", token="tok-used")
    invitation.status = "accepted"
    db.commit()

    client.post(
        f"/sessions/{active_session.id}/end", headers={"Authorization": f"Bearer {token}"}
    )

    db.refresh(invitation)
    assert invitation.status == "accepted"
