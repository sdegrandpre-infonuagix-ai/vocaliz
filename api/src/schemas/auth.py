import re

from pydantic import BaseModel, EmailStr, field_validator


def _normalize_email(v: str) -> str:
    """Lowercase and trim so the same address never yields two accounts."""
    return v.strip().lower()


class OtpRequestBody(BaseModel):
    email: EmailStr
    # Required to create an account, ignored when signing in to one — and optional here
    # because this one request is both. The rule is enforced in `otp.send_otp`, which is the
    # only place that can tell the two apart: an address nobody has seen before is somebody
    # signing up, and an address already on file is somebody coming back.
    name: str | None = None

    @field_validator("email")
    @classmethod
    def normalize(cls, v: str) -> str:
        return _normalize_email(v)


class OtpVerifyBody(BaseModel):
    email: EmailStr
    code: str

    @field_validator("email")
    @classmethod
    def normalize(cls, v: str) -> str:
        return _normalize_email(v)

    @field_validator("code")
    @classmethod
    def validate_code(cls, v: str) -> str:
        if not re.match(r"^\d{6}$", v.strip()):
            raise ValueError("code must be a 6-digit number")
        return v.strip()


class OtpRequestResponse(BaseModel):
    message: str
    # Never expose the OTP itself in responses


class AuthTokenResponse(BaseModel):
    token: str
    userId: str


class PasswordSignInBody(BaseModel):
    """The third way in (Story 10.7 / FR65). Never a replacement for the other two."""

    username: str
    password: str


class CredentialsBody(BaseModel):
    """A handle and a password, chosen alongside the identifiers."""

    username: str
    password: str


class CardRecoveryBody(BaseModel):
    """Which account, and what the payer can say about the card.

    The identifier is required even though the person cannot receive a code at it: without
    one there is nothing to compare a card against, and a card alone names no account.
    """

    identifier: str
    # At least three elements must agree and one has to be a transaction detail: the last
    # four digits are ten thousand guesses and are printed on receipts.
    lastFour: str
    expiry: str | None = None
    recentAmountCents: int | None = None
    recentChargeOn: str | None = None
