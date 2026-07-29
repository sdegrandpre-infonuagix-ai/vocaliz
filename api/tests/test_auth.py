"""Tests for OTP auth endpoints."""
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from src.models.user import User


# ─── OTP request ────────────────────────────────────────────────────────────

@patch("src.services.otp._send_sms")
def test_request_otp_creates_user(mock_sms, client):
    """First OTP request for a new number creates a User row."""
    response = client.post("/auth/otp/request", json={"phoneNumber": "+15141234567"})
    assert response.status_code == 202
    assert response.json()["message"] == "Code envoyé."
    mock_sms.assert_called_once()


@patch("src.services.otp._send_sms")
def test_request_otp_reuses_existing_user(mock_sms, client, db):
    """Second OTP request refreshes the code on an existing User row."""
    client.post("/auth/otp/request", json={"phoneNumber": "+15141234567"})
    user_before = db.query(User).filter_by(phone_number="+15141234567").first()
    code_before = user_before.otp_code

    client.post("/auth/otp/request", json={"phoneNumber": "+15141234567"})
    db.expire_all()
    user_after = db.query(User).filter_by(phone_number="+15141234567").first()

    assert user_after.otp_code != code_before
    assert db.query(User).count() == 1


def test_request_otp_invalid_phone(client):
    response = client.post("/auth/otp/request", json={"phoneNumber": "not-a-phone"})
    assert response.status_code == 422


# ─── OTP verify ─────────────────────────────────────────────────────────────

@patch("src.services.otp._send_sms")
def test_verify_otp_success_returns_jwt(mock_sms, client, db):
    """Valid OTP returns a JWT and userId."""
    client.post("/auth/otp/request", json={"phoneNumber": "+15141234567"})
    user = db.query(User).filter_by(phone_number="+15141234567").first()
    code = user.otp_code

    response = client.post("/auth/otp/verify", json={"phoneNumber": "+15141234567", "code": code})
    assert response.status_code == 200
    data = response.json()
    assert "token" in data
    assert "userId" in data


@patch("src.services.otp._send_sms")
def test_verify_otp_wrong_code_returns_400(mock_sms, client, db):
    client.post("/auth/otp/request", json={"phoneNumber": "+15141234567"})

    response = client.post("/auth/otp/verify", json={"phoneNumber": "+15141234567", "code": "000000"})
    assert response.status_code == 400


@patch("src.services.otp._send_sms")
def test_verify_otp_expired_returns_400(mock_sms, client, db):
    client.post("/auth/otp/request", json={"phoneNumber": "+15141234567"})

    user = db.query(User).filter_by(phone_number="+15141234567").first()
    user.otp_expires_at = datetime.utcnow() - timedelta(minutes=1)
    db.commit()

    response = client.post("/auth/otp/verify", json={"phoneNumber": "+15141234567", "code": user.otp_code or "123456"})
    assert response.status_code == 400
    assert "expiré" in response.json()["detail"]


@patch("src.services.otp._send_sms")
def test_verify_otp_no_pending_code_returns_400(mock_sms, client):
    response = client.post("/auth/otp/verify", json={"phoneNumber": "+15141234567", "code": "123456"})
    assert response.status_code == 400


@patch("src.services.otp._send_sms")
def test_verify_otp_clears_code_after_success(mock_sms, client, db):
    """OTP code is cleared from DB after successful verification."""
    client.post("/auth/otp/request", json={"phoneNumber": "+15141234567"})
    user = db.query(User).filter_by(phone_number="+15141234567").first()
    code = user.otp_code

    client.post("/auth/otp/verify", json={"phoneNumber": "+15141234567", "code": code})
    db.expire_all()
    user = db.query(User).filter_by(phone_number="+15141234567").first()
    assert user.otp_code is None


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
