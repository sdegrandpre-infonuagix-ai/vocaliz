"""Sessions router — create and manage discussion sessions."""
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session as DbSession

from src.database import get_db
from src.dependencies.auth import get_current_user
from src.models.session import SessionModel
from src.models.session_source import SessionSource
from src.models.user import User
from src.models.invitation import Invitation
from src.schemas.session import (
    BillingChargeSummary,
    EndSessionResponse,
    HeartbeatBody,
    HeartbeatResponse,
    JoinSessionResponse,
    SessionDetailResponse,
    SessionHistoryItem,
    SessionHistoryResponse,
    SessionInvitationSummary,
    SessionPartner,
    SessionResponse,
    SessionSourceResponse,
    SessionSourceSummary,
)
from src.config import settings
from src.schemas.invitation import InviteGuestBody
from src.services import content_service, invitation_service, livekit_service, stripe_service

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.post("", response_model=SessionResponse, status_code=201)
async def create_session(
    source_url: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
    partner_phone: Optional[str] = Form(None),
    db: DbSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Create a discussion session from a document upload or a URL.
    Provisions a LiveKit room and returns a host participant token.

    Quick-start (Story 5.2): pass `partner_phone` (a previous partner selected from
    GET /me/partners) to auto-invite that partner in the same call, so the new session
    starts with the partner already identified — no separate invitation step needed.
    """
    if not source_url and (file is None or not file.filename):
        raise HTTPException(
            status_code=400,
            detail="sourceUrl ou file est requis pour créer une session.",
        )

    # Trial gate: trial exhausted + no payment method → require Stripe setup before continuing
    if (
        current_user.trial_seconds_used >= settings.free_trial_limit_seconds
        and not current_user.stripe_payment_method_id
    ):
        raise HTTPException(
            status_code=402,
            detail=(
                "Votre heure d'essai gratuite est épuisée. "
                "Veuillez ajouter une méthode de paiement pour continuer."
            ),
        )

    # 1. Extract source content
    if source_url:
        content = await content_service.fetch_url_content(source_url)
        source_type = "url"
        source_filename = None
    else:
        content = await content_service.extract_file_content(file)  # type: ignore[arg-type]
        source_type = "document"
        source_filename = file.filename  # type: ignore[union-attr]

    # 2. Provision LiveKit room
    room_name = livekit_service.new_room_name()
    await livekit_service.create_room(room_name)

    # 3. Generate host LiveKit token
    host_token = livekit_service.generate_participant_token(
        room_name=room_name,
        user_id=str(current_user.id),
        display_name=current_user.phone_number,
        can_publish=True,
    )

    # 4. Persist session
    session = SessionModel(
        host_user_id=current_user.id,
        livekit_room_name=room_name,
        source_type=source_type,
        source_url=source_url,
        source_filename=source_filename,
        source_content=content,
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    # Quick-start with a previous partner: auto-invite so the session starts with
    # the partner already identified (Story 5.2). The session is already persisted,
    # so an invitation failure surfaces to the client without losing the session.
    invitation_summary = None
    if partner_phone:
        try:
            normalized_phone = InviteGuestBody(guestPhoneNumber=partner_phone).guestPhoneNumber
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail="partner_phone doit être au format E.164 (ex. +15145550123).",
            )
        invite = invitation_service.invite_guest(
            session_id=str(session.id),
            host_user=current_user,
            guest_phone=normalized_phone,
            db=db,
        )
        invitation_summary = SessionInvitationSummary(
            invitationId=invite["invitationId"],
            invitationType=invite["invitationType"],
            guestPhone=invite["guestPhone"],
            status=invite["status"],
            joinLink=invite.get("joinLink"),
        )

    return SessionResponse(
        sessionId=str(session.id),
        livekitRoomName=room_name,
        hostToken=host_token,
        sourceType=source_type,
        createdAt=session.created_at.isoformat(),
        invitation=invitation_summary,
    )


@router.post("/{session_id}/sources", response_model=SessionSourceResponse, status_code=201)
async def add_session_source(
    session_id: str,
    source_url: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
    db: DbSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Add an additional source (URL or document) to an active session.
    Only the session host may call this endpoint.
    """
    import uuid as _uuid

    try:
        session_uuid = _uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Session introuvable.")

    session = db.query(SessionModel).filter(
        SessionModel.id == session_uuid,
        SessionModel.host_user_id == current_user.id,
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session introuvable ou accès refusé.")

    if session.status != "active":
        raise HTTPException(status_code=409, detail="Impossible d'ajouter une source à une session terminée.")

    if not source_url and (file is None or not file.filename):
        raise HTTPException(
            status_code=400,
            detail="sourceUrl ou file est requis pour ajouter une source.",
        )

    # Extract content
    if source_url:
        content = await content_service.fetch_url_content(source_url)
        src_type = "url"
        src_filename = None
    else:
        content = await content_service.extract_file_content(file)  # type: ignore[arg-type]
        src_type = "document"
        src_filename = file.filename  # type: ignore[union-attr]

    source = SessionSource(
        session_id=session_uuid,
        host_user_id=current_user.id,
        source_type=src_type,
        source_url=source_url,
        source_filename=src_filename,
        source_content=content,
    )
    db.add(source)
    db.commit()
    db.refresh(source)

    return SessionSourceResponse(
        sourceId=str(source.id),
        sessionId=str(session.id),
        sourceType=src_type,
        contentLength=len(content or ""),
        createdAt=source.created_at.isoformat(),
    )


@router.get("", response_model=SessionHistoryResponse)
def list_session_history(
    db: DbSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Return the authenticated user's session history (Story 5.1).

    Lists every session the user took part in — as host or as an accepted guest —
    with the discussion partner(s), most recent first. A light summary only: source
    topic, date and partners. No message thread is returned (Salon keeps no transcript).
    """
    # Sessions where the user was the host.
    host_sessions = (
        db.query(SessionModel)
        .filter(SessionModel.host_user_id == current_user.id)
        .all()
    )

    # Sessions where the user joined as an invited guest (invitation accepted).
    guest_invitations = (
        db.query(Invitation)
        .filter(
            Invitation.guest_user_id == current_user.id,
            Invitation.status == "accepted",
        )
        .all()
    )
    guest_session_ids = {inv.session_id for inv in guest_invitations}
    # Exclude any session the user also hosts (can't be both) to avoid duplicates.
    host_session_ids = {s.id for s in host_sessions}
    guest_session_ids -= host_session_ids
    guest_sessions = (
        db.query(SessionModel).filter(SessionModel.id.in_(guest_session_ids)).all()
        if guest_session_ids
        else []
    )

    items: list[SessionHistoryItem] = []

    # Host-role entries: partners are the invited guests.
    for s in host_sessions:
        invitations = (
            db.query(Invitation).filter(Invitation.session_id == s.id).all()
        )
        partners: list[SessionPartner] = []
        seen: set = set()
        for inv in invitations:
            key = inv.guest_user_id or inv.guest_phone
            if key in seen:
                continue
            seen.add(key)
            phone = inv.guest_phone
            user_id = None
            if inv.guest_user_id:
                guest_user = db.query(User).filter(User.id == inv.guest_user_id).first()
                if guest_user:
                    phone = guest_user.phone_number
                    user_id = str(guest_user.id)
            partners.append(SessionPartner(userId=user_id, phoneNumber=phone))
        items.append(
            SessionHistoryItem(
                sessionId=str(s.id),
                role="host",
                sourceType=s.source_type,
                sourceUrl=s.source_url,
                status=s.status,
                createdAt=s.created_at.isoformat(),
                endedAt=s.ended_at.isoformat() if s.ended_at else None,
                partners=partners,
            )
        )

    # Guest-role entries: the partner is the session host.
    for s in guest_sessions:
        host_user = db.query(User).filter(User.id == s.host_user_id).first()
        partners = (
            [SessionPartner(userId=str(host_user.id), phoneNumber=host_user.phone_number)]
            if host_user
            else []
        )
        items.append(
            SessionHistoryItem(
                sessionId=str(s.id),
                role="guest",
                sourceType=s.source_type,
                sourceUrl=s.source_url,
                status=s.status,
                createdAt=s.created_at.isoformat(),
                endedAt=s.ended_at.isoformat() if s.ended_at else None,
                partners=partners,
            )
        )

    # Most recent first (ISO-8601 timestamps sort lexicographically).
    items.sort(key=lambda i: i.createdAt, reverse=True)

    return SessionHistoryResponse(sessions=items)


@router.get("/{session_id}", response_model=SessionDetailResponse)
def get_session(
    session_id: str,
    db: DbSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Return full session details including source content.
    Used by the agent worker at job start to build facilitation context.
    Only accessible by the session host.
    """
    import uuid as _uuid

    try:
        session_uuid = _uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Session introuvable.")

    session = db.query(SessionModel).filter(
        SessionModel.id == session_uuid,
        SessionModel.host_user_id == current_user.id,
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session introuvable ou accès refusé.")

    extra_sources = (
        db.query(SessionSource)
        .filter(SessionSource.session_id == session_uuid)
        .order_by(SessionSource.created_at)
        .all()
    )

    return SessionDetailResponse(
        sessionId=str(session.id),
        livekitRoomName=session.livekit_room_name,
        sourceType=session.source_type,
        sourceUrl=session.source_url,
        sourceContent=session.source_content,
        additionalSources=[
            SessionSourceSummary(
                sourceId=str(s.id),
                sourceType=s.source_type,
                sourceUrl=s.source_url,
                sourceContent=s.source_content,
                contentLength=len(s.source_content or ""),
                createdAt=s.created_at.isoformat(),
            )
            for s in extra_sources
        ],
        status=session.status,
        createdAt=session.created_at.isoformat(),
    )


@router.post("/{session_id}/join", response_model=JoinSessionResponse)
def join_session(
    session_id: str,
    db: DbSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Generate a LiveKit participant token for joining an active session.
    Accessible by: the session host, or any user with a pending invitation.
    Marks the invitation as accepted when a guest joins.
    """
    import uuid as _uuid
    from datetime import datetime, timezone

    try:
        session_uuid = _uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Session introuvable.")

    session = db.query(SessionModel).filter(
        SessionModel.id == session_uuid,
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session introuvable.")
    if session.status != "active":
        raise HTTPException(status_code=409, detail="Cette session est terminée.")

    # Authorise host OR invited guest
    is_host = session.host_user_id == current_user.id
    invitation = None
    if not is_host:
        now = datetime.now(tz=timezone.utc)
        invitation = (
            db.query(Invitation)
            .filter(
                Invitation.session_id == session_uuid,
                Invitation.guest_user_id == current_user.id,
                Invitation.status == "pending",
                Invitation.expires_at > now,
            )
            .first()
        )
        if not invitation:
            raise HTTPException(status_code=403, detail="Accès refusé à cette session.")

    # Mark invitation accepted
    if invitation:
        invitation.status = "accepted"
        db.commit()

    token = livekit_service.generate_participant_token(
        room_name=session.livekit_room_name,
        user_id=str(current_user.id),
        display_name=current_user.phone_number,
        can_publish=True,
    )

    return JoinSessionResponse(
        participantToken=token,
        livekitRoomName=session.livekit_room_name,
        livekitUrl=livekit_service._http_url(),
    )


@router.post("/{session_id}/heartbeat", response_model=HeartbeatResponse)
def session_heartbeat(
    session_id: str,
    body: HeartbeatBody,
    db: DbSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Record a metering heartbeat from the agent worker.

    Called every 30 seconds by the agent to commit elapsed trial time in real time.
    Ensures metered time is not lost if the session ends unexpectedly.
    Only the session host may call this endpoint.
    """
    import uuid as _uuid
    from datetime import datetime, timezone

    try:
        session_uuid = _uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Session introuvable.")

    session = db.query(SessionModel).filter(
        SessionModel.id == session_uuid,
        SessionModel.host_user_id == current_user.id,
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session introuvable ou accès refusé.")
    if session.status != "active":
        raise HTTPException(status_code=409, detail="La session est terminée.")

    seconds = max(0, body.seconds)
    host = db.query(User).filter(User.id == session.host_user_id).first()
    if host is not None and seconds > 0:
        host.trial_seconds_used = host.trial_seconds_used + seconds

    session.last_heartbeat_at = datetime.now(tz=timezone.utc)
    db.commit()

    used = host.trial_seconds_used if host is not None else 0
    return HeartbeatResponse(sessionId=str(session.id), trialSecondsUsed=used)


@router.post("/{session_id}/end", response_model=EndSessionResponse)
def end_session(
    session_id: str,
    db: DbSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Mark an active session as ended.
    Only the session host (or the agent acting on behalf of the host) may call this.
    Idempotent: calling on an already-ended session returns 409.
    """
    import uuid as _uuid
    from datetime import datetime, timezone

    try:
        session_uuid = _uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Session introuvable.")

    session = db.query(SessionModel).filter(
        SessionModel.id == session_uuid,
        SessionModel.host_user_id == current_user.id,
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session introuvable ou accès refusé.")
    if session.status == "ended":
        raise HTTPException(status_code=409, detail="Cette session est déjà terminée.")

    session.status = "ended"
    session.ended_at = datetime.now(tz=timezone.utc)
    db.commit()
    db.refresh(session)

    # Accumulate remaining host trial time since the last heartbeat (or since session
    # start if no heartbeats were received — fallback for unexpected disconnects).
    # Only the HOST role is tracked (never guests).
    # Normalise timestamps to UTC-aware — SQLite returns naive datetimes.
    reference = session.last_heartbeat_at or session.created_at
    ref = reference
    if ref.tzinfo is None:
        ref = ref.replace(tzinfo=timezone.utc)
    ended = session.ended_at
    if ended.tzinfo is None:
        ended = ended.replace(tzinfo=timezone.utc)
    remaining_seconds = max(0, int((ended - ref).total_seconds()))
    host = db.query(User).filter(User.id == session.host_user_id).first()
    if remaining_seconds > 0 and host is not None:
        host.trial_seconds_used = host.trial_seconds_used + remaining_seconds
        db.commit()

    # Bill the host for any metered time beyond their free trial hour (Story 4.4).
    # Prorated to the second at $5/hr, charged to the saved Stripe method.
    # Guests are never billed — only the host role is charged.
    # Errors are swallowed here so a payment failure never blocks session end;
    # the unbilled span is retried automatically on the host's next session.
    billing_summary = None
    if host is not None:
        try:
            charge = stripe_service.bill_host_for_usage(host, session, db)
            if charge is not None:
                billing_summary = BillingChargeSummary(**charge)
        except Exception:  # noqa: BLE001 — never let billing break session teardown
            billing_summary = None

    # Fire-and-forget: send install-link SMS to anonymous guests who participated.
    # Errors are swallowed inside the service so session end is never blocked.
    invitation_service.send_followup_sms_to_guests(str(session.id), db)

    return EndSessionResponse(
        sessionId=str(session.id),
        status=session.status,
        endedAt=session.ended_at.isoformat(),
        billing=billing_summary,
    )
