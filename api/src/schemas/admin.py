"""Response shapes for the administration router."""
from datetime import datetime

from pydantic import BaseModel


class ParticipantRecord(BaseModel):
    """One person, summarised across every salon they took part in."""

    # The LiveKit identity, which is the participation's key and what these rows are grouped
    # on. Returned because an address cannot always tell two participants apart — an anonymous
    # guest has none, so grouping on contact details folded every one of them into a single
    # line, and tracing one person's rows meant deducing rather than reading.
    participantIdentity: str = ""
    # Whichever half of the identity this person is known by, when they are known at all. Both
    # are returned so a caller can tell an unknown address from a guest who was only ever
    # texted — one combined "contact" field would hide which channel it is.
    email: str = ""
    phone: str = ""
    # Someone can be a host in one salon and a guest in another, so this is a list.
    userTypes: list[str]
    salonCount: int
    firstSeen: datetime
    lastSeen: datetime
    # Every distinct first-heard language across their salons. Empty when the agent
    # never reported one — a short session, or a participant who never spoke.
    languages: list[str]
    # Every kind of device they have been seen on — "iphone", "windows", "android-tablet" —
    # and never the User-Agent header behind it. Empty for somebody who only ever joined by
    # telephone, who has no device in this sense, and for participations recorded before the
    # column existed. A list rather than one value: hosting from a laptop and joining from a
    # phone are both true of the same person.
    devices: list[str] = []


class ReportResponse(BaseModel):
    """The hourly participant report, returned for a browser to render.

    Columns are sent alongside the rows rather than being known by the page. They are French
    labels chosen for the email, they have changed twice already, and a page holding its own
    copy would show yesterday's headings over today's figures — or silently drop a column
    nobody noticed was added.
    """

    # Ordered. The rows are dictionaries keyed by these labels, and a table has to be drawn
    # in some order — one the sender decides, not one a JSON object happens to preserve.
    columns: list[str]
    rows: list[dict]
    # What each weak column does and does not mean. Travels with the data because a reader who
    # sees "Salons de cet appareil: 3" without them concludes three visits by one person, and
    # that is not what it measures.
    caveats: list[str]
    contacts: int


class ParticipantsResponse(BaseModel):
    total: int
    # How many of the total this page carries. Both are returned so a truncated answer
    # is visible as truncated instead of reading like the whole list.
    returned: int
    participants: list[ParticipantRecord]
