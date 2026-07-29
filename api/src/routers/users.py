"""User profile router — /me/profile and /me/language."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session as DbSession

from src.database import get_db
from src.dependencies.auth import get_current_user
from src.models.user import User
from src.schemas.user import UpdateLanguageBody, UserProfileResponse

router = APIRouter(prefix="/me", tags=["users"])


@router.get("/profile", response_model=UserProfileResponse)
def get_my_profile(current_user: User = Depends(get_current_user)) -> UserProfileResponse:
    """Return the authenticated user's profile including their detected language."""
    return UserProfileResponse(
        userId=str(current_user.id),
        phoneNumber=current_user.phone_number,
        detectedLanguage=current_user.detected_language,
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
    return UserProfileResponse(
        userId=str(current_user.id),
        phoneNumber=current_user.phone_number,
        detectedLanguage=current_user.detected_language,
    )
