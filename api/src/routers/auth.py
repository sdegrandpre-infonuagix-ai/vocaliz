"""Auth router — OTP request, verify, resend."""
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from src.database import get_db
from src.rate_limit import limiter
from src.schemas.auth import AuthTokenResponse, OtpRequestBody, OtpRequestResponse, OtpVerifyBody
from src.services import invitation_service, jwt_service, otp as otp_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/otp/request", response_model=OtpRequestResponse, status_code=202)
@limiter.limit("5/minute")
def request_otp(request: Request, body: OtpRequestBody, db: Session = Depends(get_db)):
    """Email an OTP to the given address via AWS SES."""
    otp_service.send_otp(body.email, db)
    return OtpRequestResponse(message="Code envoyé.")


@router.post("/otp/resend", response_model=OtpRequestResponse, status_code=202)
@limiter.limit("5/minute")
def resend_otp(request: Request, body: OtpRequestBody, db: Session = Depends(get_db)):
    """Resend a fresh OTP (rate-limited to 5/minute per IP)."""
    otp_service.send_otp(body.email, db)
    return OtpRequestResponse(message="Nouveau code envoyé.")


@router.post("/otp/verify", response_model=AuthTokenResponse)
def verify_otp(body: OtpVerifyBody, db: Session = Depends(get_db)):
    """Verify OTP and issue a JWT on success.

    Also converts anonymous guest participation: links any prior anonymous
    invitations for this phone number to the newly registered user account.
    """
    user = otp_service.verify_otp(body.email, body.code, db)
    invitation_service.link_prior_invitations(user, db)
    token = jwt_service.issue_token(str(user.id))
    return AuthTokenResponse(token=token, userId=str(user.id))
