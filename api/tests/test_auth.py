"""Tests for OTP auth endpoints (email identity, SES delivery)."""
import logging
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from src.config import settings
from src.models.user import User

EMAIL = "seb@example.com"


def _user(db, email=EMAIL):
    return db.query(User).filter_by(email=email).first()


# ─── OTP request ────────────────────────────────────────────────────────────

@patch("src.services.otp._send_email")
def test_request_otp_creates_user(mock_email, client):
    """First OTP request for a new address creates a User row."""
    response = client.post("/auth/otp/request", json={"email": EMAIL, "name": "Seb"})
    assert response.status_code == 202
    assert response.json()["message"] == "Code sent."
    mock_email.assert_called_once()


@patch("src.services.otp._send_email")
def test_request_otp_reuses_existing_user(mock_email, client, db):
    """Second OTP request refreshes the code on an existing User row."""
    client.post("/auth/otp/request", json={"email": EMAIL, "name": "Seb"})
    code_before = _user(db).otp_code

    client.post("/auth/otp/request", json={"email": EMAIL, "name": "Seb"})
    db.expire_all()

    assert _user(db).otp_code != code_before
    assert db.query(User).count() == 1


@patch("src.services.otp._send_email")
def test_request_otp_is_case_insensitive(mock_email, client, db):
    """Address casing must not create a second account."""
    first = client.post("/auth/otp/request", json={"email": "  Seb@Example.COM ", "name": "Seb"})
    second = client.post("/auth/otp/request", json={"email": "seb@example.com", "name": "Seb"})
    assert (first.status_code, second.status_code) == (202, 202)
    assert db.query(User).count() == 1
    assert _user(db) is not None


def test_request_otp_invalid_email(client):
    response = client.post("/auth/otp/request", json={"email": "not-an-email", "name": "Seb"})
    assert response.status_code == 422


def test_request_otp_rejects_phone_number(client):
    """The old phone-based payload must no longer be accepted."""
    response = client.post("/auth/otp/request", json={"phoneNumber": "+15141234567"})
    assert response.status_code == 422


# ─── OTP verify ─────────────────────────────────────────────────────────────

@patch("src.services.otp._send_email")
def test_verify_otp_success_returns_jwt(mock_email, client, db):
    """Valid OTP returns a JWT and userId."""
    client.post("/auth/otp/request", json={"email": EMAIL, "name": "Seb"})
    code = _user(db).otp_code

    response = client.post("/auth/otp/verify", json={"email": EMAIL, "code": code})
    assert response.status_code == 200
    data = response.json()
    assert "token" in data
    assert "userId" in data


@patch("src.services.otp._send_email")
def test_verify_otp_wrong_code_returns_400(mock_email, client, db):
    client.post("/auth/otp/request", json={"email": EMAIL, "name": "Seb"})

    response = client.post("/auth/otp/verify", json={"email": EMAIL, "code": "000000"})
    assert response.status_code == 400


@patch("src.services.otp._send_email")
def test_verify_otp_expired_returns_400(mock_email, client, db):
    client.post("/auth/otp/request", json={"email": EMAIL, "name": "Seb"})

    user = _user(db)
    user.otp_expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db.commit()

    response = client.post(
        "/auth/otp/verify", json={"email": EMAIL, "code": user.otp_code or "123456"}
    )
    assert response.status_code == 400
    assert "expired" in response.json()["detail"]


@patch("src.services.otp._send_email")
def test_verify_otp_no_pending_code_returns_400(mock_email, client):
    response = client.post("/auth/otp/verify", json={"email": EMAIL, "code": "123456"})
    assert response.status_code == 400


@patch("src.services.otp._send_email")
def test_verify_otp_clears_code_after_success(mock_email, client, db):
    """OTP code is cleared from DB after successful verification."""
    client.post("/auth/otp/request", json={"email": EMAIL, "name": "Seb"})
    code = _user(db).otp_code

    client.post("/auth/otp/verify", json={"email": EMAIL, "code": code})
    db.expire_all()
    assert _user(db).otp_code is None


# ─── Account shape ──────────────────────────────────────────────────────────

@patch("src.services.otp._send_email")
def test_signup_leaves_phone_number_unset(mock_email, client, db):
    """Email is the identifier; a phone number is not collected at sign-in."""
    client.post("/auth/otp/request", json={"email": EMAIL, "name": "Seb"})
    user = _user(db)
    assert user.email == EMAIL
    assert user.phone_number is None


# ─── DEV_MODE email bypass ──────────────────────────────────────────────────

@patch("src.services.otp.boto3.client")
def test_dev_mode_logs_code_instead_of_emailing(mock_boto, client, db, caplog):
    """With DEV_MODE on, no SES client is built and the code reaches the log."""
    with patch.object(settings, "dev_mode", True), caplog.at_level(logging.WARNING):
        response = client.post("/auth/otp/request", json={"email": EMAIL, "name": "Seb"})

    assert response.status_code == 202
    mock_boto.assert_not_called()
    assert _user(db).otp_code in caplog.text


@patch("src.services.otp.boto3.client")
def test_dev_mode_off_sends_through_ses(mock_boto, client):
    """The bypass is opt-in: with DEV_MODE off the SES path is used."""
    with patch.object(settings, "dev_mode", False):
        response = client.post("/auth/otp/request", json={"email": EMAIL, "name": "Seb"})

    assert response.status_code == 202
    mock_boto.assert_called_once_with("sesv2", region_name=settings.aws_region)
    kwargs = mock_boto.return_value.send_email.call_args.kwargs
    assert kwargs["Destination"]["ToAddresses"] == [EMAIL]
    assert kwargs["FromEmailAddress"] == settings.ses_from_address


@patch("src.services.otp.boto3.client")
def test_dev_mode_code_still_verifies_normally(mock_boto, client, db):
    """A DEV_MODE-issued code goes through the same verification path."""
    with patch.object(settings, "dev_mode", True):
        client.post("/auth/otp/request", json={"email": EMAIL, "name": "Seb"})
        code = _user(db).otp_code
        response = client.post("/auth/otp/verify", json={"email": EMAIL, "code": code})

    assert response.status_code == 200
    assert response.json()["token"]


# ─── JWT ────────────────────────────────────────────────────────────────────

def test_jwt_decode_valid():
    from src.services.jwt_service import decode_token, issue_token
    token = issue_token("test-user-id")
    payload = decode_token(token)
    assert payload["sub"] == "test-user-id"


def test_jwt_decode_invalid_raises():
    from src.services.jwt_service import decode_token
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc_info:
        decode_token("not.a.valid.jwt")
    assert exc_info.value.status_code == 401


def test_a_new_address_with_no_name_is_refused_with_422(client):
    """422 rather than 400: a missing required field, which the client fixes by asking for
    one and sending the request again. A 400 would read as "this address is wrong"."""
    response = client.post("/auth/otp/request", json={"email": "stranger@example.com"})

    assert response.status_code == 422


@patch("src.services.otp._send_email")
def test_a_returning_address_needs_no_name(mock_email, client):
    client.post("/auth/otp/request", json={"email": EMAIL, "name": "Seb"})

    response = client.post("/auth/otp/request", json={"email": EMAIL})

    assert response.status_code == 202


@patch("src.services.otp._send_email")
def test_a_resend_carries_the_name_too(mock_email, client):
    """A first request that failed leaves nothing on file. Refusing the retry for want of a
    field the client is holding would strand somebody at the second step of signing up."""
    response = client.post(
        "/auth/otp/resend", json={"email": "newcomer@example.com", "name": "Rhys"}
    )

    assert response.status_code == 202
