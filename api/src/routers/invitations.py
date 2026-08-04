"""Invitations router — voice-triggered guest invitations."""
import uuid as _uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session as DbSession

from src.config import settings
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
from src.services import (
    device_service,
    invitation_service,
    livekit_service,
    salon_event_service,
    utterance_service,
)

router = APIRouter(prefix="/sessions", tags=["invitations"])
guest_router = APIRouter(prefix="/invitations", tags=["guest"])


@router.post(
    "/{session_id}/invitations/anonymous",
    response_model=InvitationResponse,
    status_code=201,
)
def create_anonymous_invitation(
    session_id: str,
    db: DbSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """A join link with nobody's address on it, for the host to pass on by hand.

    Separate from the addressed endpoint rather than an empty body on it: that one refuses a
    request with neither channel, and the refusal is worth keeping. Somebody who meant to type
    an address and left the field blank should be told, not handed a link to a stranger.
    """
    return invitation_service.invite_anonymously(
        session_id=session_id, host_user=current_user, db=db
    )


@router.post("/{session_id}/invitations", response_model=InvitationResponse, status_code=201)
async def create_invitation(
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
            guest_phone=body.guestPhone,
            db=db,
        )
    except ValueError as exc:
        if str(exc) == "session_not_found":
            raise HTTPException(status_code=404, detail="Session not found or access denied")
        if str(exc) == "contact_required":
            raise HTTPException(
                status_code=400,
                detail="An email address or a phone number is required.",
            )
        raise HTTPException(status_code=400, detail=str(exc))

    # Tell the agent a guest is on the way, so it opens the conversation instead of
    # leaving the host in silence. Sent from here rather than from the client: it must
    # fire whichever app made the invitation, and whether or not that app is still there
    # a moment later.
    #
    # Best-effort like every other room notification — a lost message costs the automatic
    # opening, never the invitation.
    session = db.query(SessionModel).filter(
        SessionModel.id == _uuid.UUID(str(session_id)),
    ).first()
    if session is not None:
        await livekit_service.notify_room(
            session.livekit_room_name,
            {
                "action": "guest_invited",
                "invitationId": result["invitationId"],
                # The clients count down from this and the agent waits it out, so both are
                # reading one number rather than each trusting their own copy.
                "opensInSeconds": settings.invitation_opening_seconds,
            },
        )

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
            # Derived from the invitation, exactly as this guest's LiveKit token is. It is what
            # lets an anonymous guest be recorded at all: they have no address, and while the
            # key demanded one such a participation was refused and they appeared nowhere.
            participant_identity=livekit_service.guest_identity(invitation.id),
            # Whichever half the host supplied, when there is one. Now an attribute of the row
            # rather than part of its key — it says how to reach somebody, not which
            # participant this is.
            email=invitation.guest_email or "",
            phone=invitation.guest_phone or "",
            user_type="guest",
            salon_name=session.livekit_room_name,
            latitude=body.latitude if body else None,
            longitude=body.longitude if body else None,
            # The client's own answer when it gave one, the header only as a fallback: an iPad
            # cannot be told from a Mac by the header alone.
            device_type=device_service.resolve(
                body.device if body else None, request.headers.get("user-agent")
            ),
            # The browser's own locale region. Validated in the service, so anything that is
            # not two letters is dropped rather than stored.
            country=body.country if body else None,
            device_token=body.deviceToken if body else None,
            # This endpoint is called from the guest page's microphone-success branch and
            # nowhere else, so reaching it *is* the evidence. See its docstring.
            microphone_enabled=True,
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


@guest_router.get("/guest-join/{join_token}/utterances")
def guest_transcript(
    join_token: str,
    lang: str | None = None,
    after: int = 0,
    db: DbSession = Depends(get_db),
):
    """The salon's transcript for a guest, translated into the language they are reading.

    Exists so a guest who changes caption language mid-conversation sees the whole exchange in
    the new one, not half of it. They are the reader who most needs it: the host usually speaks
    the language being used, and the guest often does not.

    Authenticated by the join token, which is the same credential that let them into the room —
    no weaker, and the only one they hold. A guest has no API session, so requiring the host's
    would mean the feature could never reach them.

    Bounded to the guest's own salon: the token names one invitation, which names one session.
    """
    invitation = db.query(Invitation).filter(Invitation.join_token == join_token).first()
    if invitation is None:
        raise HTTPException(status_code=404, detail="Invitation not found.")

    # Expiry is not checked. A conversation in progress outliving its invitation window is
    # possible, and cutting a participant's captions mid-sentence over a timestamp would be a
    # strange way to enforce it — the room membership is what governs whether they are present.
    session = db.query(SessionModel).filter(
        SessionModel.id == invitation.session_id,
    ).first()
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found.")

    return {
        "sessionId": str(session.id),
        # Echoed so a client can tell which language it is looking at: requests can land out of
        # order, and a stale reply must not overwrite a newer choice.
        "language": lang,
        "utterances": utterance_service.transcript(
            db, session_id=session.id, language=lang, after=after
        ),
    }
