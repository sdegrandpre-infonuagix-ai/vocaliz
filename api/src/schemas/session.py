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
