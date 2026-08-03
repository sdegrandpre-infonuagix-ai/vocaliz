"""Response shapes for the administration router."""
from datetime import datetime

from pydantic import BaseModel


class ParticipantRecord(BaseModel):
    """One person, summarised across every salon they took part in."""

    email: str
    # Someone can be a host in one salon and a guest in another, so this is a list.
    userTypes: list[str]
    salonCount: int
    firstSeen: datetime
    lastSeen: datetime
    # Every distinct first-heard language across their salons. Empty when the agent
    # never reported one — a short session, or a participant who never spoke.
    languages: list[str]


class ParticipantsResponse(BaseModel):
    total: int
    # How many of the total this page carries. Both are returned so a truncated answer
    # is visible as truncated instead of reading like the whole list.
    returned: int
    participants: list[ParticipantRecord]
