"""User profile router — /me/profile, /me/language, /me/payment-method."""
import stripe
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session as DbSession

from src.config import settings
from src.database import get_db
from src.dependencies.auth import get_current_user
from src.models.user import User
from src.schemas.user import (
    LanguagePreferencesBody,
    AddPaymentMethodBody,
    PaymentMethodResponse,
    PreviousPartner,
    PreviousPartnersResponse,
    TrialStatusResponse,
    UpdateLanguageBody,
    UserProfileResponse,
)
from src.services import partner_service, stripe_service

router = APIRouter(prefix="/me", tags=["users"])


@router.get("/profile", response_model=UserProfileResponse)
def get_my_profile(current_user: User = Depends(get_current_user)) -> UserProfileResponse:
    """Return the authenticated user's profile including their detected language."""
    return _profile(current_user)


@router.get("/trial-status", response_model=TrialStatusResponse)
def get_trial_status(current_user: User = Depends(get_current_user)) -> TrialStatusResponse:
    """Return the authenticated host's free trial usage and remaining time.

    Guests never accumulate trial time — only host-role session seconds count.
    """
    limit = settings.free_trial_limit_seconds
    used = current_user.trial_seconds_used
    remaining = max(0, limit - used)
    return TrialStatusResponse(
        trialSecondsUsed=used,
        trialSecondsLimit=limit,
        trialSecondsRemaining=remaining,
        trialExhausted=(used >= limit),
    )


@router.get("/partners", response_model=PreviousPartnersResponse)
def get_previous_partners(
    db: DbSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PreviousPartnersResponse:
    """List the authenticated user's previous discussion partners (Story 5.2).

    Powers quick-start: the app shows this list so the user can begin a new session
    with a known partner without repeating the full voice-invitation flow. Pass the
    chosen partner's phone number as `partner_phone` to POST /sessions to auto-invite.
    """
    partners = partner_service.get_previous_partners(current_user, db)
    return PreviousPartnersResponse(
        partners=[PreviousPartner(**p) for p in partners]
    )


@router.post("/payment-method", response_model=PaymentMethodResponse)
def add_payment_method(
    body: AddPaymentMethodBody,
    db: DbSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PaymentMethodResponse:
    """Attach a Stripe PaymentMethod to the host's account.

    The mobile app collects the card via Stripe Elements and passes the
    resulting PaymentMethod ID here. A Stripe Customer is created on first call.
    Required before creating a new session once the free trial is exhausted.
    """
    try:
        stripe_service.attach_payment_method(current_user, body.paymentMethodId, db)
    except stripe.StripeError as exc:
        message = getattr(exc, "user_message", None) or str(exc)
        raise HTTPException(status_code=402, detail=message)

    return PaymentMethodResponse(
        stripeCustomerId=current_user.stripe_customer_id or "",
        paymentMethodAdded=True,
    )


@router.patch("/language", response_model=UserProfileResponse)
def update_language(
    body: UpdateLanguageBody,
    db: DbSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> UserProfileResponse:
    """Set the user's detected spoken language.

    Called by the agent worker when it detects the host's language from speech,
    or by the mobile app to reflect a user's language preference.
    """
    current_user.detected_language = body.language
    db.commit()
    db.refresh(current_user)
    return _profile(current_user)


def _profile(user: User) -> UserProfileResponse:
    """The profile as every endpoint returns it.

    Written once because it is returned from three places now, and a field added to one copy
    and forgotten in another is the ordinary way these fall out of step.
    """
    return UserProfileResponse(
        userId=str(user.id),
        email=user.email,
        phoneNumber=user.phone_number,
        detectedLanguage=user.detected_language,
        interfaceLanguage=user.interface_language,
        captionLanguage=user.caption_language,
    )


@router.patch("/preferences", response_model=UserProfileResponse)
def update_language_preferences(
    body: LanguagePreferencesBody,
    db: DbSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> UserProfileResponse:
    """Remember which languages this person chose to read in.

    Two separate controls, so each field is applied only when present: sending one must not
    clear the other. `captionLanguage` accepts the empty string, which is the "as spoken"
    option and a real choice — distinct from null, which means never chosen and lets the client
    fall back to the browser or device language.

    Deliberately not merged into PATCH /language: that one records what the agent *heard*, is
    called by the worker rather than by a person, and conflating a measurement with a
    preference would make it impossible to tell which had set the value.
    """
    if body.interfaceLanguage is not None:
        current_user.interface_language = body.interfaceLanguage
    if body.captionLanguage is not None:
        current_user.caption_language = body.captionLanguage
    db.commit()
    db.refresh(current_user)
    return _profile(current_user)
