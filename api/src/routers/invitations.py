"""Invitations router — voice-triggered guest invitations."""
import uuid as _uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session as DbSession

from src.database import get_db
from src.dependencies.auth import get_current_user
from src.models.invitation import Invitation
from src.models.session import SessionModel
from src.models.user import User
from src.schemas.invitation import (
    GuestJoinResponse,
    InvitationResponse,
    InviteGuestBody,
    PendingInvitationResponse,
)
from src.services import invitation_service, livekit_service

router = APIRouter(prefix="/sessions", tags=["invitations"])
guest_router = APIRouter(prefix="/invitations", tags=["guest"])


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
            guest_email=body.guestEmail,
            db=db,
        )
    except ValueError as exc:
        if str(exc) == "session_not_found":
            raise HTTPException(status_code=404, detail="Session not found or access denied")
        raise HTTPException(status_code=400, detail=str(exc))
    return result


@router.post("/{session_id}/invitations/{invitation_id}/email", status_code=200)
def resend_invitation_email(
    session_id: str,
    invitation_id: str,
    db: DbSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Email the join link for an existing invitation.

    Split from creation so the host sees the link immediately and mails it afterwards —
    or retries a failed send without minting a second one-time token.
    """
    return invitation_service.send_invitation_email(invitation_id, current_user, db)


@guest_router.get("/guest-join/{join_token}", response_model=GuestJoinResponse)
def guest_join_session(
    join_token: str,
    db: DbSession = Depends(get_db),
):
    """Redeem a one-time join token for anonymous browser access.

    No authentication required. Marks the token as used so it cannot be reused.
    Returns LiveKit credentials to connect directly from the browser.
    """
    now = datetime.now(tz=timezone.utc)

    invitation = db.query(Invitation).filter(
        Invitation.join_token == join_token,
    ).first()

    if not invitation:
        raise HTTPException(status_code=404, detail="Lien invalide ou introuvable.")

    if invitation.status != "pending":
        raise HTTPException(status_code=410, detail="Ce lien a déjà été utilisé.")

    expires = invitation.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires < now:
        raise HTTPException(status_code=410, detail="Ce lien a expiré.")

    session = db.query(SessionModel).filter(
        SessionModel.id == invitation.session_id,
    ).first()
    if not session or session.status != "active":
        raise HTTPException(status_code=410, detail="Cette session n'est plus disponible.")

    # One-time use: mark token consumed before issuing LiveKit credentials
    invitation.status = "accepted"
    db.commit()

    anonymous_id = f"guest-{_uuid.uuid4().hex[:8]}"
    token = livekit_service.generate_participant_token(
        room_name=session.livekit_room_name,
        user_id=anonymous_id,
        display_name="Invité",
        can_publish=True,
    )

    return GuestJoinResponse(
        participantToken=token,
        livekitRoomName=session.livekit_room_name,
        livekitUrl=livekit_service._http_url(),
        sessionId=str(session.id),
    )


# Separate router for /me prefix — registered in main.py
me_router = APIRouter(prefix="/me", tags=["invitations"])


@me_router.get("/invitations", response_model=list[PendingInvitationResponse])
def list_my_invitations(
    db: DbSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return invitation_service.get_pending_invitations_for_user(user=current_user, db=db)
