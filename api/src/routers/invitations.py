"""Invitations router — voice-triggered guest invitations."""
import uuid as _uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session as DbSession

from src.database import get_db
from src.dependencies.auth import get_current_user
from src.models.invitation import Invitation
from src.models.session import SessionModel
from src.models.user import User
from src.schemas.invitation import (
    GeoBody,
    GuestJoinResponse,
    InvitationResponse,
    InviteGuestBody,
    PendingInvitationResponse,
)
from src.services import invitation_service, livekit_service, salon_event_service

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
    """Hand out LiveKit credentials for a join token, without spending it.

    No authentication required. The token is *not* consumed here — that happens in
    confirm_guest_join, once the guest's microphone actually works.

    Consuming on this call was the natural reading of "one-time link" and it was wrong in
    practice. A guest who opened the link inside their mail app's embedded browser, which
    typically cannot reach a microphone, burned the link on a page they could never speak
    from: they heard everyone, nobody heard them, and the only way out was to ask the host
    for a fresh invitation. Reloading, the obvious reflex, made it worse.

    What keeps this from becoming a link anyone can share: the participant identity is
    derived from the invitation, so two people opening the same link get the same LiveKit
    identity and the second connection displaces the first. Only one can be in the room.
    """
    now = datetime.now(tz=timezone.utc)

    invitation = db.query(Invitation).filter(
        Invitation.join_token == join_token,
    ).first()

    if not invitation:
        raise HTTPException(status_code=404, detail="Invalid or unknown link.")

    if invitation.status != "pending":
        raise HTTPException(status_code=410, detail="This link has already been used.")

    expires = invitation.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires < now:
        raise HTTPException(status_code=410, detail="This link has expired.")

    session = db.query(SessionModel).filter(
        SessionModel.id == invitation.session_id,
    ).first()
    if not session or session.status != "active":
        raise HTTPException(status_code=410, detail="This session is no longer available.")

    # Derived from the invitation instead of random. The old `guest-<8 hex>` was minted
    # here and stored nowhere, so no part of Salon could name a specific guest — messages
    # could only ever be broadcast to the whole room. The invitation id is already the
    # host's handle on this guest (it comes back when the invitation is created), which
    # makes the participant addressable without a new column or a lookup table.
    #
    # It is a UUID, not personal data, and it is not a credential: the join token is the
    # secret, and every route taking an invitation id requires the host's JWT. Other
    # participants can read it, as they can read any identity in the room, and gain
    # nothing by it.
    guest_id = livekit_service.guest_identity(invitation.id)
    token = livekit_service.generate_participant_token(
        room_name=session.livekit_room_name,
        user_id=guest_id,
        # Every guest used to carry the same fixed label, which made them addressable but
        # still indistinguishable — on screen and to the agent alike. The label carries a
        # slice of the identity, never the email: that address is between the host and
        # their guest, not something to publish to the room.
        display_name=livekit_service.guest_display_name(invitation.id),
        can_publish=True,
    )

    return GuestJoinResponse(
        participantToken=token,
        livekitRoomName=session.livekit_room_name,
        livekitUrl=livekit_service._http_url(),
        sessionId=str(session.id),
        participantIdentity=guest_id,
        participantName=livekit_service.guest_display_name(invitation.id),
    )


@guest_router.post("/guest-join/{join_token}/confirm", status_code=200)
def confirm_guest_join(
    join_token: str,
    request: Request,
    body: GeoBody | None = None,
    db: DbSession = Depends(get_db),
):
    """Spend the join token, now that the guest can actually be heard.

    Called by the guest page the moment the microphone is obtained. Splitting this from
    the credential fetch is what lets a guest recover from a browser that refuses the
    microphone: the link survives the failed attempt and can be reopened elsewhere.

    Idempotent, and never fatal. A guest who is already in the room must not be thrown out
    by a retry or a lost response, so a token that is already spent answers 200 rather than
    410 — the caller has nothing useful to do with an error here.
    """
    invitation = db.query(Invitation).filter(
        Invitation.join_token == join_token,
    ).first()

    if not invitation:
        raise HTTPException(status_code=404, detail="Invalid or unknown link.")

    if invitation.status == "pending":
        invitation.status = "accepted"
        db.commit()

    # Recorded here rather than when the credentials were fetched: this is the first
    # moment the guest is genuinely present — microphone working, able to be heard.
    session = db.query(SessionModel).filter(
        SessionModel.id == invitation.session_id,
    ).first()
    if session is not None:
        salon_event_service.record_entry(
            db,
            email=invitation.guest_email,
            user_type="guest",
            salon_name=session.livekit_room_name,
            ip=salon_event_service.client_ip(request),
            latitude=body.latitude if body else None,
            longitude=body.longitude if body else None,
        )

    return {"status": invitation.status}


# Separate router for /me prefix — registered in main.py
me_router = APIRouter(prefix="/me", tags=["invitations"])


@me_router.get("/invitations", response_model=list[PendingInvitationResponse])
def list_my_invitations(
    db: DbSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return invitation_service.get_pending_invitations_for_user(user=current_user, db=db)
