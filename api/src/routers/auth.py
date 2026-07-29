"""Auth router — OTP request, verify, resend."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from src.database import get_db
from src.schemas.auth import AuthTokenResponse, OtpRequestBody, OtpRequestResponse, OtpVerifyBody
from src.services import jwt_service, otp as otp_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/otp/request", response_model=OtpRequestResponse, status_code=202)
def request_otp(body: OtpRequestBody, db: Session = Depends(get_db)):
    """Send an OTP to the given phone number via AWS SNS."""
    otp_service.send_otp(body.phoneNumber, db)
    return OtpRequestResponse(message="Code envoyé.")


@router.post("/otp/resend", response_model=OtpRequestResponse, status_code=202)
def resend_otp(body: OtpRequestBody, db: Session = Depends(get_db)):
    """Resend a fresh OTP (rate-limited by slowapi at the app level)."""
    otp_service.send_otp(body.phoneNumber, db)
    return OtpRequestResponse(message="Nouveau code envoyé.")


@router.post("/otp/verify", response_model=AuthTokenResponse)
def verify_otp(body: OtpVerifyBody, db: Session = Depends(get_db)):
    """Verify OTP and issue a JWT on success."""
    user = otp_service.verify_otp(body.phoneNumber, body.code, db)
    token = jwt_service.issue_token(str(user.id))
    return AuthTokenResponse(token=token, userId=str(user.id))
