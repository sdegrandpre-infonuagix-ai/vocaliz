import re
from pydantic import BaseModel, field_validator


class InviteGuestBody(BaseModel):
    guestPhoneNumber: str

    @field_validator("guestPhoneNumber")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        cleaned = re.sub(r"\s", "", v)
        if not re.match(r"^\+[1-9]\d{7,14}$", cleaned):
            raise ValueError("guestPhoneNumber must be in E.164 format")
        return cleaned


class InvitationResponse(BaseModel):
    invitationId: str
    invitationType: str   # 'salon_friend' | 'sms_contact'
    guestPhone: str
    status: str
    joinLink: str | None  # only for sms_contact type


class PendingInvitationResponse(BaseModel):
    invitationId: str
    sessionId: str
    livekitRoomName: str
    hostEmail: str
    hostPhone: str | None = None
    joinToken: str
    createdAt: str
    expiresAt: str


class GuestJoinResponse(BaseModel):
    participantToken: str
    livekitRoomName: str
    livekitUrl: str
    sessionId: str
