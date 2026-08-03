from pydantic import BaseModel, EmailStr, field_validator


class InviteGuestBody(BaseModel):
    guestEmail: EmailStr

    @field_validator("guestEmail")
    @classmethod
    def normalize(cls, v: str) -> str:
        """Lowercase and trim so a guest is matched to their account regardless of casing."""
        return v.strip().lower()


class GeoBody(BaseModel):
    """Optional position sent by a page that obtained it from the browser.

    Both fields absent is the ordinary case, not an error: the participant declined the
    location prompt, or the browser never offered it.
    """
    latitude: float | None = None
    longitude: float | None = None


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
    # The LiveKit identity this guest will join under, known before they connect. This is
    # what makes a guest addressable: without it the only handle was a random string
    # minted at join time and recorded nowhere.
    participantIdentity: str
    # How that guest is labelled to everyone in the room. Derived from the identity, never
    # from the email — only the host, here, can tie the two together.
    participantName: str


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
    # Returned so the guest's own page knows which identity in the room is itself.
    participantIdentity: str
    # And under which label it appears to the others.
    participantName: str
