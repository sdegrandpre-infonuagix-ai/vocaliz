import re

from pydantic import BaseModel, EmailStr, Field, field_validator


def _normalize_email(v: str) -> str:
    """Lowercase and trim so the same address never yields two accounts."""
    return v.strip().lower()


class OtpRequestBody(BaseModel):
    email: EmailStr
    # Required, of every request and not only the first.
    #
    # It was briefly optional here, with the rule enforced further in where a new address can
    # be told from a returning one. That is a subtler contract than it is worth: the field is
    # on the same form as the address in every client, so nobody is made to remember anything
    # they are not already looking at, and a schema that says "required" cannot be satisfied
    # by accident in one case and not another. What a name is *for* is unconditional too — it
    # is how the others in a Salon are told who is speaking.
    #
    # Sixty characters, matching the column. Trimmed before length is judged, so whitespace
    # cannot pass for an answer.
    name: str = Field(min_length=1, max_length=60)

    @field_validator("email")
    @classmethod
    def normalize(cls, v: str) -> str:
        return _normalize_email(v)

    @field_validator("name")
    @classmethod
    def named(cls, v: str) -> str:
        trimmed = v.strip()
        if not trimmed:
            raise ValueError("a name is required to create an account")
        return trimmed


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
