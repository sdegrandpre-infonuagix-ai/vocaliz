import re

from pydantic import BaseModel, EmailStr, field_validator


def _normalize_email(v: str) -> str:
    """Lowercase and trim so the same address never yields two accounts."""
    return v.strip().lower()


class OtpRequestBody(BaseModel):
    email: EmailStr

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
