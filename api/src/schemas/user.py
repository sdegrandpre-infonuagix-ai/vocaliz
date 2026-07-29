from pydantic import BaseModel, field_validator


class UserProfileResponse(BaseModel):
    userId: str
    phoneNumber: str
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
