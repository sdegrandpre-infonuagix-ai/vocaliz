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
    JoinSessionResponse,
    SessionDetailResponse,
    SessionResponse,
    SessionSourceResponse,
    SessionSourceSummary,
)
from src.services import content_service, livekit_service

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.post("", response_model=SessionResponse, status_code=201)
async def create_session(
    source_url: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
    db: DbSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Create a discussion session from a document upload or a URL.
    Provisions a LiveKit room and returns a host participant token.
    """
    if not source_url and (file is None or not file.filename):
        raise HTTPException(
            status_code=400,
            detail="sourceUrl ou file est requis pour créer une session.",
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

    return SessionResponse(
        sessionId=str(session.id),
        livekitRoomName=room_name,
        hostToken=host_token,
        sourceType=source_type,
        createdAt=session.created_at.isoformat(),
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
