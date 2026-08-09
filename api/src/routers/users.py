"""User profile router — /me/profile, /me/language, /me/payment-method."""
import logging
from datetime import datetime, timezone

import stripe
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session as DbSession

from src import credentials, identifier_change, privacy
from src.models.pending_identifier_change import PendingIdentifierChange

from src.config import settings
from src.database import get_db
from src.dependencies.auth import get_current_user
from src.models.user import User
from src.schemas.user import (
    CredentialsBody,
    ErasureBody,
    IdentifierChangeBody,
    IdentifierConfirmBody,
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
from src.services import otp as otp_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/me", tags=["users"])


@router.get("/profile", response_model=UserProfileResponse)
def get_my_profile(current_user: User = Depends(get_current_user)) -> UserProfileResponse:
    """Return the authenticated user's profile including their detected language."""
    return _profile(current_user)


@router.get("/trial-status", response_model=TrialStatusResponse)
def get_trial_status(current_user: User = Depends(get_current_user)) -> TrialStatusResponse:
    """Return the authenticated host's free trial usage and remaining time.

    Guests never accumulate trial time — only host-role salon seconds count.
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

    Powers quick-start: the app shows this list so the user can begin a new salon
    with a known partner without repeating the full voice-invitation flow. Pass the
    chosen partner's phone number as `partner_phone` to POST /salons to auto-invite.
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
    Required before creating a new salon once the free trial is exhausted.
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
        captionScale=user.caption_scale,
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
    if body.captionScale is not None:
        current_user.caption_scale = body.captionScale
    db.commit()
    db.refresh(current_user)
    return _profile(current_user)


@router.post("/identifier", status_code=202)
def request_identifier_change(
    body: IdentifierChangeBody,
    db: DbSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Ask to move one identifier, keeping the other as the anchor (Story 10.6 / FR64).

    202 rather than 200: nothing has changed yet. A code goes to the new address or number and
    the change waits for it — applying on request would let anybody holding a session move
    somebody's key to something they control.

    The code is not in the response, for the same reason it never is: it travels to the
    identifier being proved, which is the whole of what proving means.
    """
    try:
        planned = identifier_change.plan_change(
            db,
            current_user,
            new_email=body.newEmail,
            new_phone=body.newPhone,
            now=datetime.now(tz=timezone.utc),
        )
    except identifier_change.ChangeRefused as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if "@" in planned.new_identifier:
        try:
            otp_service.send_change_code(planned.new_identifier, planned.code)
        except Exception:  # noqa: BLE001
            # The change is already set aside and a code can be asked for again. Losing the
            # delivery must not lose the request the user just made.
            logger.warning("Could not send the identifier change code", exc_info=True)

    db.commit()
    return {
        "anchor": planned.anchor,
        "newIdentifier": planned.new_identifier,
        "message": "A code is on its way to the new identifier.",
    }


@router.post("/identifier/confirm", response_model=UserProfileResponse)
def confirm_identifier_change(
    body: IdentifierConfirmBody,
    db: DbSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Give the code and let the change take effect.

    The most recent unused request is the one being confirmed. Somebody who asked twice meant
    the second one — the first is abandoned rather than ambiguous.
    """
    row = (
        db.query(PendingIdentifierChange)
        .filter(
            PendingIdentifierChange.user_id == current_user.id,
            PendingIdentifierChange.used_at.is_(None),
        )
        .order_by(PendingIdentifierChange.requested_at.desc())
        .first()
    )
    if row is None:
        raise HTTPException(
            status_code=404, detail="There is no identifier change waiting to be confirmed."
        )

    try:
        identifier_change.apply_change(
            db,
            identifier_change.PlannedChange(row=row),
            code=body.code,
            now=datetime.now(tz=timezone.utc),
        )
    except identifier_change.ChangeRefused as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    db.commit()
    db.refresh(current_user)
    return _profile(current_user)


@router.put("/credentials", status_code=200)
def set_password(
    body: CredentialsBody,
    db: DbSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Choose a username and a password for this account (Story 10.7 / FR65).

    Sets both together: a username with no password is a handle that opens nothing, and a
    password with no username has nothing to be typed beside.
    """
    try:
        credentials.set_credentials(
            db, current_user, username=body.username, password=body.password
        )
    except credentials.CredentialsRefused as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    db.commit()
    return {"username": current_user.username}


@router.get("/data", status_code=200)
def export_my_data(
    db: DbSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """A copy of everything Vocaliz holds about you (Story 10.8 / FR66).

    Plain JSON, so it is a file somebody can open rather than an object graph. Their own words
    and nobody else's: handing somebody the other half of a conversation would be answering one
    person's right with another person's words.
    """
    return privacy.export_data(db, current_user)


@router.post("/erasure", status_code=200)
def erase_my_data(
    body: ErasureBody,
    db: DbSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Erase what is yours, keeping what is other people's (Story 10.8 / FR66).

    The bearer token is the verification. It was issued by one of Story 10.7's routes — a code
    to an identifier, or a username and password — which is what the criterion asks for, and
    an erasure nobody verified is a way to destroy somebody else's account.

    A positive paid balance refuses the request until it is refunded or knowingly given up.
    Erasing an account must never be how the money in it disappears.
    """
    try:
        record = privacy.erase(
            db,
            current_user,
            verified=True,
            waive_refund=body.waiveRefund,
            now=datetime.now(tz=timezone.utc),
        )
    except privacy.ErasureRefused as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    db.commit()
    return {
        "scope": record.scope,
        "dueBy": record.due_by.isoformat(),
        "completedAt": record.requested_at.isoformat(),
        "message": "Your data has been erased. This is the record of it.",
    }
