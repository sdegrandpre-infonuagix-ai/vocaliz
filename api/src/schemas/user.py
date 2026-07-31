from pydantic import BaseModel, field_validator


class UserProfileResponse(BaseModel):
    userId: str
    email: str
    # Optional since sign-in moved to email; only set if the user supplied one.
    phoneNumber: str | None = None
    detectedLanguage: str | None = None


class UpdateLanguageBody(BaseModel):
    language: str

    @field_validator("language")
    @classmethod
    def language_is_bcp47(cls, v: str) -> str:
        v = v.strip().lower()
        if not v or len(v) > 10 or not v.replace("-", "").isalpha():
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
    lastSessionAt: str | None = None
    sessionCount: int


class PreviousPartnersResponse(BaseModel):
    partners: list[PreviousPartner]


class AddPaymentMethodBody(BaseModel):
    paymentMethodId: str


class PaymentMethodResponse(BaseModel):
    stripeCustomerId: str
    paymentMethodAdded: bool
