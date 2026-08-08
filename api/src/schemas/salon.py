from pydantic import BaseModel, field_validator
import re


class SalonInvitationSummary(BaseModel):
    """Summary of the partner auto-invited when a salon is quick-started (Story 5.2)."""
    invitationId: str
    invitationType: str   # 'salon_friend' | 'email_contact'
    guestEmail: str
    status: str
    joinLink: str | None = None


class SalonResponse(BaseModel):
    salonId: str
    livekitRoomName: str
    hostToken: str
    sourceType: str
    createdAt: str
    # Present only when a previous partner was auto-invited at creation (quick-start).
    invitation: SalonInvitationSummary | None = None


class AddSourceBody(BaseModel):
    """Body for adding an additional source to an active salon (Story 2.3)."""
    sourceUrl: str | None = None

    @field_validator("sourceUrl")
    @classmethod
    def validate_url(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if not re.match(r"^https?://", v):
            raise ValueError("sourceUrl must start with http:// or https://")
        return v


class SalonSourceResponse(BaseModel):
    sourceId: str
    salonId: str
    sourceType: str       # 'url' | 'document'
    contentLength: int    # characters of extracted plain text
    createdAt: str


class SalonSourceSummary(BaseModel):
    sourceId: str
    sourceType: str
    sourceUrl: str | None = None
    sourceContent: str | None = None   # full extracted text — used by agent for contrast facilitation
    sourceSummary: str | None = None
    contentLength: int
    createdAt: str


class SalonDetailResponse(BaseModel):
    salonId: str
    livekitRoomName: str
    sourceType: str
    sourceUrl: str | None
    sourceContent: str | None
    # The brief the agent works from. sourceContent stays available for search, but it is
    # this that goes into the prompt.
    sourceSummary: str | None = None
    additionalSources: list[SalonSourceSummary]
    status: str
    createdAt: str
    # Read by the agent at start-up, which is the only way it can know it is joining a salon
    # that has not been activated yet. Defaulted to True so an agent talking to an older API
    # errs towards silence: a salon that stays quiet until asked is a smaller failure than one
    # that starts talking over its host.
    agentMuted: bool = True
    # The LiveKit identity the host joins under, so the agent can tell it is really them.
    #
    # Not derived from the identity's shape. The old rule — anything not prefixed "guest-" is
    # the host — stopped being true when a registered guest began joining under their own
    # account id, and it now guards something that matters: whose typed words the agent will
    # speak aloud in its own voice.
    hostIdentity: str = ""
    # Which language the agent must speak, or "auto" to follow each speaker. Read at start-up
    # like agentMuted: a Salon rung from the front page carries the caller's choice, and an
    # agent that ignored it would answer a Persian speaker in whatever it guessed instead.
    agentLanguage: str = "auto"
    # True when this Salon was opened by somebody ringing the front page.
    #
    # Computed from who owns it rather than stored: a column would have to be written at
    # creation and would then be one more thing that can disagree with reality. The agent
    # reads this to know it is answering a call rather than facilitating a discussion — two
    # different jobs that happen to share a room.
    frontDesk: bool = False


class JoinSalonResponse(BaseModel):
    participantToken: str
    livekitRoomName: str
    livekitUrl: str


class SalonPartner(BaseModel):
    """A discussion partner in a past salon (host sees guests, guest sees host)."""
    userId: str | None = None       # null for contacts never registered
    phoneNumber: str | None = None  # null for partners known only by email
    email: str | None = None        # null for invited contacts never registered
    displayName: str | None = None


class SalonHistoryItem(BaseModel):
    """One entry in a user's salon history — a light summary, no message thread."""
    salonId: str
    role: str                       # 'host' | 'guest'
    sourceType: str
    sourceUrl: str | None = None
    status: str
    createdAt: str
    endedAt: str | None = None
    partners: list[SalonPartner]


class SalonHistoryResponse(BaseModel):
    salons: list[SalonHistoryItem]


class BillingChargeSummary(BaseModel):
    """Details of a post-trial charge made when a salon ends (Story 4.4)."""
    billedSeconds: int
    amountCents: int
    currency: str
    paymentIntentId: str | None = None
    status: str


class EndSalonResponse(BaseModel):
    salonId: str
    status: str
    endedAt: str
    # Present only when the host was charged for usage beyond the free trial.
    billing: BillingChargeSummary | None = None


class SourceSearchResponse(BaseModel):
    """Passages of a salon's sources that bear on a question.

    Excerpts rather than the whole text: the point of summarising was to keep the prompt
    small, and answering a question by posting the document back into the conversation
    would undo it.
    """
    excerpts: list[str]


class ParticipantLanguageBody(BaseModel):
    """The first language heard from one participant of one salon.

    participantIdentity is the LiveKit one, the only handle the agent holds. It resolves
    to an email server-side, which is what salon_events is keyed by.
    """
    participantIdentity: str
    language: str


class EndSalonBody(BaseModel):
    """Optional closing answer, supplied by the agent that asked the question.

    Three states and the third is not a failure: True and False are answers, None means
    the participant never replied — someone who simply closed the tab. Recording None as
    False would invent dissatisfaction nobody voiced.
    """
    enjoyed: bool | None = None


class HeartbeatBody(BaseModel):
    seconds: int


class HeartbeatResponse(BaseModel):
    salonId: str
    trialSecondsUsed: int
    # Seconds left before this salon hits its own cap — not the account's trial.
    # Returned so the agent can wind the conversation down instead of being cut off.
    secondsRemaining: int = 0
    # True when this very heartbeat is the one that closed the salon.
    salonEnded: bool = False


class UtteranceBody(BaseModel):
    """One final turn of speech, posted by the agent as it is transcribed.

    speakerIdentity is the LiveKit one — the only handle available at the moment someone
    speaks, and deliberately not an email: a caption carries a display label, and a
    guest's address must never reach the other participants.

    targetLanguages asks for the turn rendered into each of them in the same round trip.
    The agent knows what every viewer is reading, from their participant attributes, and
    asking here saves a second call before the caption can be published.
    """
    speakerIdentity: str
    speakerRole: str
    text: str
    language: str | None = None
    targetLanguages: list[str] = []

    @field_validator("speakerRole")
    @classmethod
    def role_is_known(cls, v: str) -> str:
        v = v.strip().lower()
        if v not in {"host", "guest", "agent"}:
            raise ValueError("speakerRole must be one of: host, guest, agent")
        return v

    @field_validator("text")
    @classmethod
    def text_is_not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("text must not be blank")
        return v


class UtteranceResponse(BaseModel):
    sequence: int
    speaker: str
    role: str
    text: str
    language: str | None = None
    spokenAt: str | None = None
    # Keyed by requested language. A language whose translation failed is absent rather
    # than echoing the original: the caller can tell "not translated" from "translated".
    translations: dict[str, str] = {}


class TranscriptResponse(BaseModel):
    salonId: str
    # Echoed so a client can tell which language it is looking at after changing it
    # mid-salon, when a request in flight may answer after the newer one.
    language: str | None = None
    utterances: list[dict]


class AgentStateResponse(BaseModel):
    """What the host toggle should show.

    Two independent facts, not one tri-state: an agent can be present and listening, present
    and paused, or absent. Collapsing them into a single value would make "absent" and
    "paused" indistinguishable to a control that has to offer different actions for each.
    """

    present: bool
    muted: bool


class AgentMuteBody(BaseModel):
    muted: bool



class VoiceHealthBody(BaseModel):
    """What an agent reports about its realtime voice connection.

    `ok` is what the agent actually observed, not a prediction. `detail` carries the failure so
    the alert can quote it — an alert saying "voice failed" without saying how sends somebody
    looking through logs at an awkward hour.
    """

    ok: bool
    detail: str = ""
