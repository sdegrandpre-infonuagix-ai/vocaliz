from pydantic import BaseModel, field_validator
import re


class SessionInvitationSummary(BaseModel):
    """Summary of the partner auto-invited when a session is quick-started (Story 5.2)."""
    invitationId: str
    invitationType: str   # 'salon_friend' | 'email_contact'
    guestEmail: str
    status: str
    joinLink: str | None = None


class SessionResponse(BaseModel):
    sessionId: str
    livekitRoomName: str
    hostToken: str
    sourceType: str
    createdAt: str
    # Present only when a previous partner was auto-invited at creation (quick-start).
    invitation: SessionInvitationSummary | None = None


class AddSourceBody(BaseModel):
    """Body for adding an additional source to an active session (Story 2.3)."""
    sourceUrl: str | None = None

    @field_validator("sourceUrl")
    @classmethod
    def validate_url(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if not re.match(r"^https?://", v):
            raise ValueError("sourceUrl must start with http:// or https://")
        return v


class SessionSourceResponse(BaseModel):
    sourceId: str
    sessionId: str
    sourceType: str       # 'url' | 'document'
    contentLength: int    # characters of extracted plain text
    createdAt: str


class SessionSourceSummary(BaseModel):
    sourceId: str
    sourceType: str
    sourceUrl: str | None = None
    sourceContent: str | None = None   # full extracted text — used by agent for contrast facilitation
    contentLength: int
    createdAt: str


class SessionDetailResponse(BaseModel):
    sessionId: str
    livekitRoomName: str
    sourceType: str
    sourceUrl: str | None
    sourceContent: str | None
    additionalSources: list[SessionSourceSummary]
    status: str
    createdAt: str


class JoinSessionResponse(BaseModel):
    participantToken: str
    livekitRoomName: str
    livekitUrl: str


class SessionPartner(BaseModel):
    """A discussion partner in a past session (host sees guests, guest sees host)."""
    userId: str | None = None       # null for contacts never registered
    phoneNumber: str | None = None  # null for partners known only by email
    email: str | None = None        # null for invited contacts never registered
    displayName: str | None = None


class SessionHistoryItem(BaseModel):
    """One entry in a user's session history — a light summary, no message thread."""
    sessionId: str
    role: str                       # 'host' | 'guest'
    sourceType: str
    sourceUrl: str | None = None
    status: str
    createdAt: str
    endedAt: str | None = None
    partners: list[SessionPartner]


class SessionHistoryResponse(BaseModel):
    sessions: list[SessionHistoryItem]


class BillingChargeSummary(BaseModel):
    """Details of a post-trial charge made when a session ends (Story 4.4)."""
    billedSeconds: int
    amountCents: int
    currency: str
    paymentIntentId: str | None = None
    status: str


class EndSessionResponse(BaseModel):
    sessionId: str
    status: str
    endedAt: str
    # Present only when the host was charged for usage beyond the free trial.
    billing: BillingChargeSummary | None = None


class HeartbeatBody(BaseModel):
    seconds: int


class HeartbeatResponse(BaseModel):
    sessionId: str
    trialSecondsUsed: int
    # Seconds left before this session hits its own cap — not the account's trial.
    # Returned so the agent can wind the conversation down instead of being cut off.
    secondsRemaining: int = 0
    # True when this very heartbeat is the one that closed the session.
    sessionEnded: bool = False
