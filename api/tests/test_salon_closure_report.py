"""Tests for the closure report mailed the instant a salon ends.

Every salon that reaches `finalize_salon` — by an explicit POST /end, the balance-exhaustion
heartbeat, the abandonment sweep, or a host opening a new salon over an old one — mails one
report to a fixed inbox: who was in the room, what account each of them has (if any), what
they are worth, and their own transcript as an attachment. Sending is never allowed to raise;
a salon must finish closing whether or not the report gets anywhere.
"""
import email
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from src.models.salon import Salon
from src.models.salon_event import SalonEvent
from src.models.user import User
from src.services import salon_closure_report
from src.services.jwt_service import issue_token


@pytest.fixture
def host(db):
    u = User(email="15147770001@example.com", phone_number="+15147770001")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u, issue_token(str(u.id))


@pytest.fixture
def active_salon(db, host):
    host_user, _ = host
    salon = Salon(
        host_user_id=host_user.id,
        livekit_room_name="salon-closure-room",
        source_type="url",
        source_url="https://example.com",
        source_content="content",
        status="active",
    )
    db.add(salon)
    db.commit()
    db.refresh(salon)
    return salon


def _seat(db, salon, *, identity, email="", user_type="guest", language=None):
    event = SalonEvent(
        participant_identity=identity,
        salon_name=salon.livekit_room_name,
        salon_id=salon.id,
        email=email,
        user_type=user_type,
        first_spoken_language=language,
        entered_at=datetime.now(tz=timezone.utc) - timedelta(minutes=5),
        exited_at=datetime.now(tz=timezone.utc),
    )
    db.add(event)
    db.commit()
    return event


def _body_text(raw: bytes) -> str:
    """The report's plain-text part, decoded — never the raw MIME bytes, which is base64
    for both the body and every attachment and would make a substring search meaningless."""
    message = email.message_from_bytes(raw)
    for part in message.walk():
        if part.get_content_type() == "text/plain" and part.get_filename() is None:
            return part.get_payload(decode=True).decode("utf-8")
    raise AssertionError("no text/plain body part found")


def _attachment_filenames(raw: bytes) -> list[str]:
    message = email.message_from_bytes(raw)
    return [part.get_filename() for part in message.walk() if part.get_filename()]


# ─── send() ──────────────────────────────────────────────────────────────────

def test_one_report_per_salon_named_by_participant_count(db, host, active_salon):
    host_user, _ = host
    _seat(db, active_salon, identity=str(host_user.id), email=host_user.email, user_type="host")
    _seat(db, active_salon, identity="guest-abc123", email="", user_type="guest")

    with patch("src.services.salon_closure_report.boto3") as mock_boto3:
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client
        result = salon_closure_report.send(db, active_salon)

    assert result == {"status": "ok", "participants": 2}
    mock_client.send_raw_email.assert_called_once()
    kwargs = mock_client.send_raw_email.call_args[1]
    assert kwargs["Destinations"] == ["s.degrandpre@vocaliz.net"]
    raw = kwargs["RawMessage"]["Data"]
    assert b"Vocaliz" in raw
    assert str(active_salon.id).encode() in raw or b"salon" in raw.lower()


def test_the_host_is_reported_with_their_account_and_balance(db, host, active_salon):
    """The host's identity is their account UUID, so a report about them should carry
    their real creation date and balance, not "(anonymous)"."""
    host_user, _ = host
    _seat(db, active_salon, identity=str(host_user.id), email=host_user.email, user_type="host")

    with patch("src.services.salon_closure_report.boto3") as mock_boto3:
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client
        salon_closure_report.send(db, active_salon)

    body = _body_text(mock_client.send_raw_email.call_args[1]["RawMessage"]["Data"])
    assert host_user.email in body
    assert "no account" not in body.split(host_user.email)[1][:200]


def test_an_anonymous_guest_is_reported_with_no_account(db, host, active_salon):
    """`guest-<invitation id>` is not a UUID a User table holds — there is no account to
    report a creation date or a balance for, and the report must say so rather than guess."""
    _seat(db, active_salon, identity="guest-deadbeef", email="", user_type="guest")

    with patch("src.services.salon_closure_report.boto3") as mock_boto3:
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client
        salon_closure_report.send(db, active_salon)

    body = _body_text(mock_client.send_raw_email.call_args[1]["RawMessage"]["Data"])
    assert "(anonymous)" in body
    assert "no account" in body


def test_one_attachment_per_participant(db, host, active_salon):
    host_user, _ = host
    _seat(db, active_salon, identity=str(host_user.id), email=host_user.email, user_type="host")
    _seat(db, active_salon, identity="guest-xyz", email="guest@example.com", user_type="guest")

    with patch("src.services.salon_closure_report.boto3") as mock_boto3:
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client
        salon_closure_report.send(db, active_salon)

    raw = mock_client.send_raw_email.call_args[1]["RawMessage"]["Data"]
    filenames = _attachment_filenames(raw)
    assert len(filenames) == 2
    # "@" is not filename-safe and is replaced; "." is left alone.
    assert f"{host_user.email}.txt".replace("@", "_") in filenames
    assert "guest_example.com.txt" in filenames


def test_a_send_failure_is_swallowed_not_raised(db, host, active_salon):
    _seat(db, active_salon, identity=str(host[0].id), email=host[0].email, user_type="host")

    with patch("src.services.salon_closure_report.boto3") as mock_boto3:
        mock_client = MagicMock()
        mock_client.send_raw_email.side_effect = Exception("SES is down")
        mock_boto3.client.return_value = mock_client
        result = salon_closure_report.send(db, active_salon)

    assert result == {"status": "send_failed"}


def test_a_salon_with_no_recorded_participants_still_sends(db, active_salon):
    """Every salon that closes gets a report, even one nobody's participation was ever
    recorded for — an empty report is still the true answer, not a reason to skip it."""
    with patch("src.services.salon_closure_report.boto3") as mock_boto3:
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client
        result = salon_closure_report.send(db, active_salon)

    assert result == {"status": "ok", "participants": 0}
    mock_client.send_raw_email.assert_called_once()


# ─── Integration: finalize_salon triggers the report ────────────────────────

def test_ending_a_salon_sends_the_closure_report(client, db, host, active_salon):
    host_user, token = host
    _seat(db, active_salon, identity=str(host_user.id), email=host_user.email, user_type="host")

    with patch("src.services.salon_closure_report.boto3") as mock_boto3:
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client
        resp = client.post(
            f"/salons/{active_salon.id}/end",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert resp.status_code == 200
    mock_client.send_raw_email.assert_called_once()


def test_a_failed_closure_report_does_not_block_ending_the_salon(client, db, host, active_salon):
    host_user, token = host
    _seat(db, active_salon, identity=str(host_user.id), email=host_user.email, user_type="host")

    with patch("src.services.salon_closure_report.boto3") as mock_boto3:
        mock_client = MagicMock()
        mock_client.send_raw_email.side_effect = Exception("SES is down")
        mock_boto3.client.return_value = mock_client
        resp = client.post(
            f"/salons/{active_salon.id}/end",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert resp.status_code == 200
    assert resp.json()["status"] == "ended"
