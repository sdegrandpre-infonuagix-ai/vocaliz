"""Auth router — OTP request, verify, resend, password sign-in, card recovery."""
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session as DbSession

from src.database import get_db
from src.rate_limit import limiter
from src import card_recovery, credentials, signup
from src.schemas.auth import (
    AuthTokenResponse,
    OtpRequestBody,
    OtpRequestResponse,
    CardRecoveryBody,
    OtpVerifyBody,
    PasswordSignInBody,
)
from src.services import invitation_service, jwt_service, otp as otp_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/otp/request", response_model=OtpRequestResponse, status_code=202)
@limiter.limit("5/minute")
def request_otp(request: Request, body: OtpRequestBody, db: DbSession = Depends(get_db)):
    """Email an OTP to the given address via AWS SES."""
    otp_service.send_otp(body.email, db)
    return OtpRequestResponse(message="Code sent.")


@router.post("/otp/resend", response_model=OtpRequestResponse, status_code=202)
@limiter.limit("5/minute")
def resend_otp(request: Request, body: OtpRequestBody, db: DbSession = Depends(get_db)):
    """Resend a fresh OTP (rate-limited to 5/minute per IP)."""
    otp_service.send_otp(body.email, db)
    return OtpRequestResponse(message="New code sent.")


@router.post("/otp/verify", response_model=AuthTokenResponse)
def verify_otp(body: OtpVerifyBody, db: DbSession = Depends(get_db)):
    """Verify OTP and issue a JWT on success.

    Also converts prior guest participation: links any invitation issued
    invitations for this phone number to the newly registered user account.
    """
    user = otp_service.verify_otp(body.email, body.code, db)
    invitation_service.link_prior_invitations(user, db)
    token = jwt_service.issue_token(str(user.id))
    return AuthTokenResponse(token=token, userId=str(user.id))


@router.post("/password", response_model=AuthTokenResponse)
@limiter.limit("10/minute")
def sign_in_with_password(
    request: Request, body: PasswordSignInBody, db: DbSession = Depends(get_db)
):
    """Sign in with a username and a password (Story 10.7 / FR65).

    A third way in and never a replacement: the code routes stay open, because the failure
    this one covers is precisely that they stopped working.

    One refusal for every failure, naming nothing. Telling somebody the username exists but
    the password is wrong tells an attacker which half to keep working on. Rate-limited for
    the same reason — this is the one route where guessing is the whole attack.
    """
    person = credentials.sign_in(db, username=body.username, password=body.password)
    if person is None:
        raise HTTPException(status_code=401, detail="Wrong username or password.")

    invitation_service.link_prior_invitations(person, db)
    return AuthTokenResponse(
        token=jwt_service.issue_token(str(person.id)), userId=str(person.id)
    )


@router.post("/recover-payment", status_code=200)
@limiter.limit("5/hour")
def recover_payment(
    request: Request, body: CardRecoveryBody, db: DbSession = Depends(get_db)
):
    """Prove the card that paid, and be told what can be refunded (Story 10.7 / FR65).

    Public, because the person asking cannot sign in — that is the situation this exists for.
    Rate-limited at the door as well as per account, since an unauthenticated endpoint that
    compares card details is exactly the shape somebody automates.

    **It returns money, never access.** Holding the card that paid does not prove you are the
    account holder — cards are shared, inherited and issued by employers — so no token is
    issued here and the account stays as unreachable as it was. Restoring access is the other
    routes' business.

    The account is found by the identifier the payer can still name, which is why one is
    required: without it there is nothing to compare a card against.
    """
    person = signup.find_by_identifier(db, signup.normalise_email(body.identifier)) or (
        signup.find_by_identifier(db, signup.normalise_phone(body.identifier))
    )
    if person is None:
        # Deliberately the same answer as a card that does not match. Confirming which
        # addresses have accounts is a directory anybody could build.
        raise HTTPException(
            status_code=400,
            detail="Those details do not match an account we can refund.",
        )

    on_file = card_recovery.CardEvidence(
        last_four=(person.stripe_payment_method_id or "")[-4:],
        expiry=None,
        recent_amount_cents=None,
        recent_charge_on=None,
    )
    given = card_recovery.CardEvidence(
        last_four=body.lastFour,
        expiry=body.expiry,
        recent_amount_cents=body.recentAmountCents,
        recent_charge_on=(
            date.fromisoformat(body.recentChargeOn) if body.recentChargeOn else None
        ),
    )

    try:
        cents = card_recovery.refundable_cents(
            db,
            person.id,
            given=given,
            on_file=on_file,
            now=datetime.now(tz=timezone.utc),
        )
    except card_recovery.RecoveryRefused as exc:
        db.commit()
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    db.commit()
    return {
        "refundableCents": cents,
        "message": (
            "This confirms what can be refunded to the card that paid. It does not open the "
            "account — signing in is a separate matter."
        ),
    }
