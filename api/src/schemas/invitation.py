from pydantic import BaseModel, EmailStr, field_validator


class InviteGuestBody(BaseModel):
    guestEmail: EmailStr

    @field_validator("guestEmail")
    @classmethod
    def normalize(cls, v: str) -> str:
        """Lowercase and trim so a guest is matched to their account regardless of casing."""
        return v.strip().lower()


class InvitationResponse(BaseModel):
    invitationId: str
    invitationType: str   # 'salon_friend' | 'email_contact'
    guestEmail: str
    status: str
    # Always present: a join token exists for every invitation, and the browser join
    # endpoint accepts it whatever the type. Salon friends also get an in-app notification.
    joinLink: str
    # False when delivery failed — the link is still returned so the host can share it.
    emailSent: bool = False


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
