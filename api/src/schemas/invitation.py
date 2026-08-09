from pydantic import BaseModel, EmailStr, field_validator, model_validator


class InviteGuestBody(BaseModel):
    """An address, a number, or both — but not neither.

    Neither channel is privileged. A host may hold one, the other or both, and the join
    link is the same whichever way it travels; when both are given the invitation goes
    out over both, because the point is that it arrives.
    """

    guestEmail: EmailStr | None = None
    guestPhone: str | None = None

    @field_validator("guestEmail")
    @classmethod
    def normalize(cls, v: str | None) -> str | None:
        """Lowercase and trim so a guest is matched to their account regardless of casing.

        A field left blank arrives as "" from a form and becomes None: an empty string is
        not an address, and storing it as one would make it look like a channel we tried.
        """
        if v is None:
            return None
        v = v.strip().lower()
        return v or None

    @field_validator("guestPhone")
    @classmethod
    def phone_is_e164(cls, v: str | None) -> str | None:
        """E.164, or nothing at all.

        An empty field arrives as "" from a form that was left blank, which is not a
        number and must not be stored as one — it becomes None rather than a validation
        error, since leaving it blank is the expected behaviour.

        The country code is required. A ten-digit local number would be guessed at by the
        carrier, and a text message about a conversation starting in fifteen seconds is
        not worth guessing on.
        """
        if v is None:
            return None
        v = v.strip().replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
        if not v:
            return None
        if not v.startswith("+") or not v[1:].isdigit() or not 8 <= len(v) <= 16:
            raise ValueError(
                "guestPhone must be in E.164 format, including the country code (e.g. +15145550123)"
            )
        return v

    @model_validator(mode="after")
    def at_least_one_contact(self):
        """One of the two is required.

        Checked here as well as by a CHECK in the database: the constraint is what makes
        an unidentified invitation impossible, and this is what makes the refusal a clear
        400 instead of an integrity error surfacing as a 500.
        """
        if not self.guestEmail and not self.guestPhone:
            raise ValueError("An email address or a phone number is required.")
        return self


class GeoBody(BaseModel):
    """Optional position sent by a page that obtained it from the browser.

    Both fields absent is the ordinary case, not an error: the participant declined the
    location prompt, or the browser never offered it.
    """
    latitude: float | None = None
    longitude: float | None = None
    # What kind of device the client believes it is. Sent by the page rather than derived from
    # the User-Agent header because only the browser can tell an iPad from a Mac — iPadOS
    # Safari reports itself as a Macintosh and the header holds nothing to separate them.
    # Validated against a closed vocabulary server-side; an unknown value becomes absent.
    device: str | None = None
    # Two-letter region from the browser's locale. Coarse on purpose: no position is asked for
    # and no address is kept, so this is the whole of what is known about where somebody is.
    country: str | None = None
    # A random UUID this browser keeps, so a returning device is recognisable. Not an identity:
    # it says "the same browser", never who is holding it.
    deviceToken: str | None = None


class InvitationResponse(BaseModel):
    invitationId: str
    invitationType: str   # 'salon_friend' | 'email_contact'
    # Either may be empty — never both. A guest reached only by text has no address here,
    # and the empty string says so; NULL would mean the same thing in a second way.
    guestEmail: str = ""
    guestPhone: str = ""
    status: str
    # Always present: a join token exists for every invitation, and the browser join
    # endpoint accepts it whatever the type. Salon friends also get an in-app notification.
    joinLink: str
    # One flag per channel, each False unless that channel was asked for AND succeeded.
    # A single combined flag would tell a host who supplied both that "it was sent" when
    # only one of the two actually left. The link is returned either way, so a failure
    # costs convenience rather than the invitation.
    emailSent: bool = False
    smsSent: bool = False
    # The six digits this guest types to reach the Salon without a link.
    #
    # Built by the service since migration 022 and absent from this model until now, so
    # FastAPI dropped it on the way out: the code was minted, reserved and mailed, and the one
    # person who might have to read it aloud — the host — could not see it. Empty when the pool
    # could not issue one, which costs the telephone door and never the invitation.
    phonePin: str = ""
    # The LiveKit identity this guest will join under, known before they connect. This is
    # what makes a guest addressable: without it the only handle was a random string
    # minted at join time and recorded nowhere.
    participantIdentity: str
    # How that guest is labelled to everyone in the room. Derived from the identity, never
    # from the email — only the host, here, can tie the two together.
    participantName: str


class PendingInvitationResponse(BaseModel):
    invitationId: str
    salonId: str
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
    salonId: str
    # Returned so the guest's own page knows which identity in the room is itself.
    participantIdentity: str
    # And under which label it appears to the others.
    participantName: str
    # Story 10.4. Whether the host is covering everybody, which decides whether the join
    # screen puts the tier question at all. The page has to know before it renders: asking
    # and then hiding the answer is a question somebody watched appear and vanish.
    hostPaysAll: bool = False


class GuestOptionsBody(BaseModel):
    """The three things a guest settles on the join screen, answered together (FR35)."""

    tier: str | None = None
    video: bool = False
    topUpCents: int | None = None


class GuestOptionsResponse(BaseModel):
    """What was settled, and what the screen should therefore do next."""

    tier: str
    video: bool
    topUpCents: int | None
    # `None` when there is no credit to speak of — the rate stands alone rather than
    # advertising a duration of zero.
    coveredByCreditMinutes: int | None
    paymentRequired: bool
    choiceOffered: bool
