"""Sessions router — create and manage discussion sessions."""
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session as DbSession

from src.database import get_db
from src.dependencies.auth import get_current_user
from src.models.session import SessionModel
from src.models.user import User
from src.schemas.session import SessionResponse
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
