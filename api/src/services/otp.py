"""OTP generation, storage, and delivery by email via AWS SES."""
import logging
import random
import string
from datetime import datetime, timedelta, timezone

import boto3
from botocore.exceptions import ClientError
from fastapi import HTTPException
from sqlalchemy.orm import Session as DbSession

from src.config import settings
from src.models.user import User
from src.services.email_text import bilingual_body, bilingual_subject
from src.signup import find_by_identifier, normalise_email, register

logger = logging.getLogger(__name__)


class MissingName(ValueError):
    """Somebody tried to create an account without saying what to call them.

    A name is the one thing a Salon cannot work around. Every other participant hears "Marie
    says…" before what Marie said, because a listener in headphones has no screen and no
    second voice to ask — introductions are how they tell two strangers apart. An account
    with no name would be introduced as nothing, in every conversation, for as long as it
    existed.
    """

    def __init__(self, address: str) -> None:
        self.address = address
        super().__init__("a name is required to create an account")


def _generate_otp() -> str:
    return "".join(random.choices(string.digits, k=6))


def send_otp(email: str, db: DbSession, *, name: str | None = None) -> None:
    """Generate OTP, persist it, and email it via AWS SES.

    Signing up and asking for a code are one act (Story 10.1), so the account is created
    through `register`: the address is normalised and written into the identifier registry,
    which is what keys the lifetime quota to the person rather than to the account. Creating
    the row here instead would leave somebody registered with no key to their own allowance.

    A name is required, and `OtpRequestBody` is where that is enforced for anything arriving
    over HTTP — 422, with the field named. The check below is the backstop for callers that
    do not go through the schema: this function is reached directly from the invitation
    service and from tests, and an account created there with no name would be introduced as
    nothing for as long as it existed.
    """
    address = normalise_email(email)

    if find_by_identifier(db, address) is None and not (name or "").strip():
        raise MissingName(address)

    user = register(db, email=address, name=name)

    code = _generate_otp()
    user.otp_code = code
    user.otp_expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.otp_expiry_minutes)
    user.otp_attempts = 0
    db.commit()

    _send_email(address, code)


def verify_otp(email: str, code: str, db: DbSession) -> User:
    """Verify OTP code. Returns the user on success, raises HTTPException on failure.

    Normalised on the way in, exactly as `send_otp` normalises it: a code requested at
    `marie@example.com` and confirmed at `Marie@Example.com` is one person confirming one
    code, and matching the raw string would tell them there was no pending code.
    """
    user = db.query(User).filter(User.email == normalise_email(email)).first()

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


def _clear_otp(user: User, db: DbSession) -> None:
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


def send_change_code(address: str, code: str) -> None:
    """Email a code for an identifier change (Story 10.6 / FR64).

    Separate from `send_otp` because it must **not** create an account. That one signs
    somebody up as a side effect of asking for a code, which is right at the door and wrong
    here: the address being proved does not belong to anybody yet, and minting an account for
    it would make the change collide with the account it just created.
    """
    _send_email(address, code)
