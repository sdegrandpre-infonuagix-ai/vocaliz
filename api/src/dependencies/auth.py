"""FastAPI dependency: extract and validate the current user from a Bearer JWT."""
import uuid

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from src.config import settings
from src.database import get_db
from src.models.user import User
from src.services.jwt_service import decode_token

_bearer = HTTPBearer()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    payload = decode_token(credentials.credentials)
    user_id_str: str | None = payload.get("sub")
    if not user_id_str:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token.")
    try:
        user_id = uuid.UUID(user_id_str)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token.")
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found.")
    return user


def admin_emails() -> set[str]:
    """The configured administrators, lowercased.

    Blank entries are dropped rather than kept as an empty string, which would otherwise
    let a user with no email — there is no such user today, but the model allows it —
    match the list.
    """
    return {e.strip().lower() for e in settings.admin_emails.split(",") if e.strip()}


def get_current_admin(current_user: User = Depends(get_current_user)) -> User:
    """Like get_current_user, but only for the configured administrators.

    403 and not 404: the caller proved who they are, and the honest answer is that this
    identity is not allowed here. Hiding the route's existence from an authenticated user
    buys nothing — the path is in the public OpenAPI document either way.
    """
    if (current_user.email or "").lower() not in admin_emails():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator access required.",
        )
    return current_user
