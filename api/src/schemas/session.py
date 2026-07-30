from pydantic import BaseModel, field_validator
import re


class SessionResponse(BaseModel):
    sessionId: str
    livekitRoomName: str
    hostToken: str
    sourceType: str
    createdAt: str


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
