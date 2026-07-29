"""Invitations router — voice-triggered guest invitations."""
from fastapi import APIRouter, Depends, HTTPException

from src.database import get_db
from sqlalchemy.orm import Session as DbSession
from src.dependencies.auth import get_current_user
from src.models.user import User
from src.schemas.invitation import InvitationResponse, InviteGuestBody, PendingInvitationResponse
from src.services import invitation_service

router = APIRouter(prefix="/sessions", tags=["invitations"])


@router.post("/{session_id}/invitations", response_model=InvitationResponse, status_code=201)
def create_invitation(
    session_id: str,
    body: InviteGuestBody,
    db: DbSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        result = invitation_service.invite_guest(
            session_id=session_id,
            host_user=current_user,
            guest_phone=body.guestPhoneNumber,
            db=db,
        )
    except ValueError as exc:
        if str(exc) == "session_not_found":
            raise HTTPException(status_code=404, detail="Session not found or access denied")
        raise HTTPException(status_code=400, detail=str(exc))
    return result


# Separate router for /me prefix — registered below in main.py
me_router = APIRouter(prefix="/me", tags=["invitations"])


@me_router.get("/invitations", response_model=list[PendingInvitationResponse])
def list_my_invitations(
    db: DbSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return invitation_service.get_pending_invitations_for_user(user=current_user, db=db)
