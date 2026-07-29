"""OTP generation, storage, and delivery via AWS SNS."""
import random
import string
from datetime import datetime, timedelta, timezone

import boto3
from botocore.exceptions import ClientError
from fastapi import HTTPException
from sqlalchemy.orm import Session

from src.config import settings
from src.models.user import User


def _generate_otp() -> str:
    return "".join(random.choices(string.digits, k=6))


def send_otp(phone_number: str, db: Session) -> None:
    """Generate OTP, persist it, and send via AWS SNS SMS."""
    user = db.query(User).filter(User.phone_number == phone_number).first()
    if user is None:
        user = User(phone_number=phone_number)
        db.add(user)

    code = _generate_otp()
    user.otp_code = code
    user.otp_expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.otp_expiry_minutes)
    user.otp_attempts = 0
    db.commit()

    _send_sms(phone_number, code)


def verify_otp(phone_number: str, code: str, db: Session) -> User:
    """Verify OTP code. Returns the user on success, raises HTTPException on failure."""
    user = db.query(User).filter(User.phone_number == phone_number).first()

    if user is None or user.otp_code is None:
        raise HTTPException(status_code=400, detail="Aucun code en attente pour ce numéro.")

    if user.otp_attempts >= settings.otp_max_attempts:
        raise HTTPException(
            status_code=429,
            detail="Trop de tentatives. Veuillez demander un nouveau code.",
        )

    now = datetime.now(timezone.utc)
    expires = user.otp_expires_at
    # SQLite returns naive datetimes; treat them as UTC for test compatibility
    if expires is not None and expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires is None or now > expires:
        _clear_otp(user, db)
        raise HTTPException(
            status_code=400,
            detail="Ce code a expiré. Veuillez en demander un nouveau.",
        )

    user.otp_attempts += 1
    db.commit()

    if user.otp_code != code:
        raise HTTPException(status_code=400, detail="Code incorrect. Veuillez réessayer.")

    _clear_otp(user, db)
    return user


def _clear_otp(user: User, db: Session) -> None:
    user.otp_code = None
    user.otp_expires_at = None
    user.otp_attempts = 0
    db.commit()


def _send_sms(phone_number: str, code: str) -> None:
    """Send OTP via AWS SNS transactional SMS."""
    client = boto3.client("sns", region_name=settings.aws_region)
    message = f"Votre code Salon est : {code}\nValable {settings.otp_expiry_minutes} minutes."
    try:
        client.publish(
            PhoneNumber=phone_number,
            Message=message,
            MessageAttributes={
                "AWS.SNS.SMS.SMSType": {"DataType": "String", "StringValue": "Transactional"},
                "AWS.SNS.SMS.SenderID": {"DataType": "String", "StringValue": settings.sns_sender_id},
            },
        )
    except ClientError as exc:
        # Log the error but don't expose SNS internals to the caller
        raise HTTPException(
            status_code=503,
            detail="Impossible d'envoyer le SMS. Veuillez réessayer.",
        ) from exc
