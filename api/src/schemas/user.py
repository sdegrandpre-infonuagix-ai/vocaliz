from pydantic import BaseModel, field_validator


class UserProfileResponse(BaseModel):
    userId: str
    email: str
    # Optional since sign-in moved to email; only set if the user supplied one.
    phoneNumber: str | None = None
    detectedLanguage: str | None = None
    # The two the person chose, as opposed to the one above, which is what they were heard
    # speaking. null means never chosen — for captions that differs from "", which means they
    # chose to read speech as spoken.
    interfaceLanguage: str | None = None
    captionLanguage: str | None = None
    # A whole percentage — 85, 100, 120 — not a multiplier. null means never chosen.
    captionScale: int | None = None


class UpdateLanguageBody(BaseModel):
    language: str

    @field_validator("language")
    @classmethod
    def language_is_bcp47(cls, v: str) -> str:
        v = v.strip().lower()
        if not v or len(v) > 10 or not v.replace("-", "").isalpha():
            raise ValueError("language must be a valid BCP-47 code (e.g. 'fr', 'en', 'en-CA')")
        return v


class LanguagePreferencesBody(BaseModel):
    """Either preference, or both. Absent means "leave this one alone" — the two controls are
    separate on screen and a request that touched both would let one overwrite the other."""

    interfaceLanguage: str | None = None
    captionLanguage: str | None = None
    captionScale: int | None = None

    @field_validator("captionScale")
    @classmethod
    def within_reading_range(cls, v: int | None) -> int | None:
        """Bounded rather than free. A percentage outside a readable range is a bug in a
        caller, and storing it would leave somebody with a caption panel they cannot use and
        no obvious way back."""
        if v is None:
            return None
        if not 50 <= v <= 300:
            raise ValueError("captionScale must be a percentage between 50 and 300")
        return v

    @field_validator("interfaceLanguage", "captionLanguage")
    @classmethod
    def looks_like_a_language(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip().lower()
        # Empty is valid and meaningful for captions: it is the "as spoken" option, which
        # translates nothing. Rejecting it would make that choice impossible to save.
        if not v:
            return ""
        if len(v) > 10 or not v.replace("-", "").isalpha():
            raise ValueError("language must be a valid BCP-47 code (e.g. 'fr', 'en', 'en-CA')")
        return v


class TrialStatusResponse(BaseModel):
    trialSecondsUsed: int
    trialSecondsLimit: int
    trialSecondsRemaining: int
    trialExhausted: bool


class PreviousPartner(BaseModel):
    """A known discussion partner surfaced for quick-start (Story 5.2)."""
    userId: str | None = None       # null for contacts never registered
    phoneNumber: str | None = None  # null for partners known only by email
    email: str | None = None        # null for invited contacts never registered
    lastSalonAt: str | None = None
    salonCount: int


class PreviousPartnersResponse(BaseModel):
    partners: list[PreviousPartner]


class AddPaymentMethodBody(BaseModel):
    paymentMethodId: str


class PaymentMethodResponse(BaseModel):
    stripeCustomerId: str
    paymentMethodAdded: bool


class IdentifierChangeBody(BaseModel):
    """One identifier on the move (Story 10.6 / FR64). Exactly one of the two."""

    newEmail: str | None = None
    newPhone: str | None = None


class IdentifierConfirmBody(BaseModel):
    """The code that proves the person holds the new identifier."""

    code: str


class CredentialsBody(BaseModel):
    """A handle and a password, chosen alongside the identifiers (Story 10.7 / FR65)."""

    username: str
    password: str


class ErasureBody(BaseModel):
    """An erasure request (Story 10.8 / FR66).

    `waiveRefund` is how somebody says knowingly that they are giving up a positive balance.
    Defaulting it to true would make silence a decision about money.
    """

    waiveRefund: bool = False
