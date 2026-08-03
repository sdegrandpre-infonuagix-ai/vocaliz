"""OTP generation, storage, and delivery by email via AWS SES."""
import logging
import random
import string
from datetime import datetime, timedelta, timezone

import boto3
from botocore.exceptions import ClientError
from fastapi import HTTPException
from sqlalchemy.orm import Session

from src.config import settings
from src.models.user import User
from src.services.email_text import bilingual_body, bilingual_subject

logger = logging.getLogger(__name__)


def _generate_otp() -> str:
    return "".join(random.choices(string.digits, k=6))


def send_otp(email: str, db: Session) -> None:
    """Generate OTP, persist it, and email it via AWS SES."""
    user = db.query(User).filter(User.email == email).first()
    if user is None:
        user = User(email=email)
        db.add(user)

    code = _generate_otp()
    user.otp_code = code
    user.otp_expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.otp_expiry_minutes)
    user.otp_attempts = 0
    db.commit()

    _send_email(email, code)


def verify_otp(email: str, code: str, db: Session) -> User:
    """Verify OTP code. Returns the user on success, raises HTTPException on failure."""
    user = db.query(User).filter(User.email == email).first()

    if user is None or user.otp_code is None:
        raise HTTPException(status_code=400, detail="No pending code for this address.")

    if user.otp_attempts >= settings.otp_max_attempts:
        raise HTTPException(
            status_code=429,
            detail="Too many attempts. Please request a new code.",
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
            detail="This code has expired. Please request a new one.",
        )

    user.otp_attempts += 1
    db.commit()

    if user.otp_code != code:
        raise HTTPException(status_code=400, detail="Incorrect code. Please try again.")

    _clear_otp(user, db)
    return user


def _clear_otp(user: User, db: Session) -> None:
    user.otp_code = None
    user.otp_expires_at = None
    user.otp_attempts = 0
    db.commit()


def _send_email(email: str, code: str) -> None:
    """Send the OTP by email through AWS SES.

    In DEV_MODE the code is logged instead of sent, so testing needs no verified SES
    identity — read it from the API console locally, or CloudWatch on Lambda.
    """
    if settings.dev_mode:
        logger.warning("DEV_MODE: OTP for %s is %s (email not sent)", email, code)
        return

    minutes = settings.otp_expiry_minutes
    client = boto3.client("sesv2", region_name=settings.aws_region)
    try:
        client.send_email(
            FromEmailAddress=settings.ses_from_address,
            Destination={"ToAddresses": [email]},
            Content={
                "Simple": {
                    "Subject": {
                        "Data": bilingual_subject(
                            f"Your Vocaliz code: {code}",
                            f"Votre code Vocaliz : {code}",
                        ),
                        "Charset": "UTF-8",
                    },
                    "Body": {
                        "Text": {
                            "Data": bilingual_body(
                                f"Your Vocaliz code is: {code}\n"
                                f"Valid for {minutes} minutes.\n\n"
                                "If you did not request this code, ignore this message.",
                                f"Votre code Vocaliz est : {code}\n"
                                f"Valable {minutes} minutes.\n\n"
                                "Si vous n'avez pas demandé ce code, ignorez ce message.",
                            ),
                            "Charset": "UTF-8",
                        }
                    },
                }
            },
        )
    except ClientError as exc:
        # A rejected sender identity and a service outage both land here; log the cause
        # rather than leaving only the opaque 503 the caller sees.
        logger.error("SES send_email failed for %s: %s", email, exc, exc_info=True)
        raise HTTPException(
            status_code=503,
            detail="Could not send the email. Please try again.",
        ) from exc
