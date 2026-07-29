from pydantic import BaseModel, field_validator
import re


class OtpRequestBody(BaseModel):
    phoneNumber: str

    @field_validator("phoneNumber")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        # Accept E.164 format: +1XXXXXXXXXX
        cleaned = re.sub(r"\s", "", v)
        if not re.match(r"^\+[1-9]\d{7,14}$", cleaned):
            raise ValueError("phoneNumber must be in E.164 format (e.g. +15141234567)")
        return cleaned


class OtpVerifyBody(BaseModel):
    phoneNumber: str
    code: str

    @field_validator("phoneNumber")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        cleaned = re.sub(r"\s", "", v)
        if not re.match(r"^\+[1-9]\d{7,14}$", cleaned):
            raise ValueError("phoneNumber must be in E.164 format")
        return cleaned

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
