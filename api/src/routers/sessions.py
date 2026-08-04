"""Sessions router — create and manage discussion sessions."""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from sqlalchemy.orm import Session as DbSession

from src.database import get_db
from src.dependencies.auth import get_current_user
from src.models.ad import Ad
from src.models.ad_broadcast import AdBroadcast
from src.models.salon_event import SalonEvent
from src.models.session import SessionModel
from src.models.shared_source import SharedSource, SharedSourceConsent
from src.models.session_source import SessionSource
from src.models.user import User
from src.models.invitation import Invitation
from src.schemas.session import (
    AgentMuteBody,
    AgentStateResponse,
    BillingChargeSummary,
    EndSessionBody,
    EndSessionResponse,
    HeartbeatBody,
    ParticipantLanguageBody,
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
    SourceSearchResponse,
    TranscriptResponse,
    UtteranceBody,
    UtteranceResponse,
)
from src.config import settings
from src.schemas.invitation import GeoBody, InviteGuestBody
from src.services import (
    ad_auction_service,
    content_service,
    device_service,
    invitation_service,
    jwt_service,
    livekit_service,
    salon_event_service,
    session_lifecycle,
    shared_source_service,
    summary_service,
    stripe_service,
    translation_service,
    utterance_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sessions", tags=["sessions"])


async def _publish_to_corpus(
    db: DbSession,
    *,
    session_id,
    shared_by: str,
    url: str,
    summary: str | None,
    content: str,
    provenance: dict,
    article_date,
) -> None:
    """Add a consented page to the shared corpus, topics and all.

    Written once and called from both source paths so the two cannot drift: a page shared
    on creation and the same page shared mid-conversation must land identically.

    Topics are extracted here rather than at search time, because a spoken question has
    to be answered in the time it takes to say a sentence. Best-effort throughout — a
    failure costs the page its searchability, never the host their source.
    """
    try:
        topics = await summary_service.topics(content)
        shared_source_service.publish(
            db,
            session_id=session_id,
            shared_by=shared_by,
            url=url,
            summary=summary or "",
            content=content,
            topics=topics,
            article_date=article_date,
            author=provenance.get("author", ""),
            publisher=provenance.get("publisher", ""),
        )
    except Exception:  # noqa: BLE001
        logger.warning("Could not publish %s to the shared corpus", url, exc_info=True)


@router.post("", response_model=SessionResponse, status_code=201)
async def create_session(
    source_url: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
    partner_email: Optional[str] = Form(None),
    language: Optional[str] = Form(None),
    # Opt-in, per source, and only ever honoured for a URL. False by default: a host who
    # says nothing has shared nothing.
    share_with_platform: bool = Form(False),
    db: DbSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Create a discussion session from a document upload or a URL.
    Provisions a LiveKit room and returns a host participant token.

    Quick-start (Story 5.2): pass `partner_email` (a previous partner selected from
    GET /me/partners) to auto-invite that partner in the same call, so the new session
    starts with the partner already identified — no separate invitation step needed.
    """
    # Trial gate: trial exhausted + no payment method → require Stripe setup before continuing
    if (
        current_user.trial_seconds_used >= settings.free_trial_limit_seconds
        and not current_user.stripe_payment_method_id
    ):
        raise HTTPException(
            status_code=402,
            detail=(
                "Your free trial hour is used up. "
                "Please add a payment method to continue."
            ),
        )

    # 0. A host may never have two sessions open at once. A stale session keeps its agent
    # alive and talking, so a new room could surface the previous agent instead of its own
    # — which is precisely what happened in testing. Closing settles the metering; deleting
    # the room is what actually stops the old agent.
    closed = await session_lifecycle.close_previous_host_sessions(current_user, db)
    if closed:
        logger.info("Closed %d stale session(s) before creating a new one", closed)

    # 1. Extract source content. A session may start with no source at all: the agent
    # then opens by asking participants what they want to discuss (see _build_instructions).
    # Metadata is read from the same fetch as the text, never a second request: fetching
    # twice doubles the wait and can return two different versions of a page.
    provenance = {"article_date": "", "author": "", "publisher": ""}
    if source_url:
        content, provenance = await content_service.fetch_url_document(source_url)
        source_type = "url"
        source_filename = None
    elif file is not None and file.filename:
        content = await content_service.extract_file_content(file)
        source_type = "document"
        source_filename = file.filename
    else:
        content = None
        source_type = "none"
        source_filename = None

    article_date = content_service.parse_article_date(provenance.get("article_date", ""))

    # 2. Provision LiveKit room
    room_name = livekit_service.new_room_name()
    await livekit_service.create_room(room_name)

    # 3. Generate host LiveKit token
    host_token = livekit_service.generate_participant_token(
        room_name=room_name,
        user_id=str(current_user.id),
        display_name=current_user.email,
        can_publish=True,
    )

    # 3b. Condense the source into the host's language. This is what the agent will
    # actually read: the full text stays below for search, but the prompt carries the
    # brief. Sent before the room exists so a failure here costs nothing but a fallback.
    #
    # The language comes from the client when it knows it — the web console knows which
    # of EN/FR the host is reading — falling back to whatever the agent detected last
    # time. A brief the host has to translate in their head is worse than no brief.
    summary, summary_tokens = await summary_service.summarise(
        content, language or current_user.detected_language
    )

    # 4. Persist session
    session = SessionModel(
        host_user_id=current_user.id,
        livekit_room_name=room_name,
        source_type=source_type,
        source_url=source_url,
        source_filename=source_filename,
        source_content=content,
        source_summary=summary,
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    # Accounting only — nothing reads this back during the conversation.
    if content:
        salon_event_service.record_upload(
            db,
            salon_id=session.id,
            uploaded_by=current_user.email,
            url=source_url,
            filename=source_filename,
            content=content,
            tokens=summary_tokens,
            article_date=article_date,
            author=provenance.get("author", ""),
            publisher=provenance.get("publisher", ""),
        )

    # Publish to the shared corpus, if the host asked and the source is a URL. The type
    # check is belt-and-braces: publish() has no parameter for a file and shared_sources has
    # no column for one, so a document cannot get in even from here.
    if share_with_platform and source_type == "url" and content:
        await _publish_to_corpus(
            db,
            session_id=session.id,
            shared_by=current_user.email,
            url=source_url,
            summary=summary,
            content=content,
            provenance=provenance,
            article_date=article_date,
        )

    # 5. Dispatch the agent with the session context it needs to read sources, invite
    # guests and report metering. Done after the commit so the session id exists.
    #
    # This is a Salon API JWT, not the LiveKit participant token above: the agent calls
    # our REST API with it, and passing the LiveKit token here yields 401 on every call.
    await livekit_service.dispatch_agent(
        room_name,
        session_id=str(session.id),
        host_token=jwt_service.issue_token(str(current_user.id)),
    )

    # Quick-start with a previous partner: auto-invite so the session starts with
    # the partner already identified (Story 5.2). The session is already persisted,
    # so an invitation failure surfaces to the client without losing the session.
    invitation_summary = None
    if partner_email:
        try:
            normalized_email = InviteGuestBody(guestEmail=partner_email).guestEmail
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail="partner_email must be a valid email address.",
            )
        invite = invitation_service.invite_guest(
            session_id=str(session.id),
            host_user=current_user,
            guest_email=normalized_email,
            db=db,
        )
        invitation_summary = SessionInvitationSummary(
            invitationId=invite["invitationId"],
            invitationType=invite["invitationType"],
            guestEmail=invite["guestEmail"],
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
    share_with_platform: bool = Form(False),
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
        raise HTTPException(status_code=404, detail="Session not found.")

    session = db.query(SessionModel).filter(
        SessionModel.id == session_uuid,
        SessionModel.host_user_id == current_user.id,
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found or access denied.")

    if session.status != "active":
        raise HTTPException(status_code=409, detail="Cannot add a source to an ended session.")

    if not source_url and (file is None or not file.filename):
        raise HTTPException(
            status_code=400,
            detail="sourceUrl or file is required to add a source.",
        )

    # Extract content
    provenance = {"article_date": "", "author": "", "publisher": ""}
    if source_url:
        content, provenance = await content_service.fetch_url_document(source_url)
        src_type = "url"
        src_filename = None
    else:
        content = await content_service.extract_file_content(file)  # type: ignore[arg-type]
        src_type = "document"
        src_filename = file.filename  # type: ignore[union-attr]

    # Same treatment as the opening source: the agent reads the brief, not the raw text.
    summary, summary_tokens = await summary_service.summarise(
        content, current_user.detected_language
    )

    source = SessionSource(
        session_id=session_uuid,
        host_user_id=current_user.id,
        source_type=src_type,
        source_url=source_url,
        source_filename=src_filename,
        source_content=content,
        source_summary=summary,
    )
    db.add(source)
    db.commit()
    db.refresh(source)

    salon_event_service.record_upload(
        db,
        salon_id=session.id,
        uploaded_by=current_user.email,
        url=source_url,
        filename=src_filename,
        content=content,
        tokens=summary_tokens,
        article_date=content_service.parse_article_date(provenance.get("article_date", "")),
        author=provenance.get("author", ""),
        publisher=provenance.get("publisher", ""),
    )

    if share_with_platform and source_url and content:
        await _publish_to_corpus(
            db,
            session_id=session.id,
            shared_by=current_user.email,
            url=source_url,
            summary=summary,
            content=content,
            provenance=provenance,
            article_date=content_service.parse_article_date(
                provenance.get("article_date", "")
            ),
        )

    # The agent reads session sources once, at job start. Without this it would never
    # learn about a source added mid-conversation (FR3).
    await livekit_service.notify_room(
        session.livekit_room_name, {"action": "source_added", "sourceId": str(source.id)}
    )

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
            key = inv.guest_user_id or inv.guest_email
            if key in seen:
                continue
            seen.add(key)
            email = inv.guest_email
            user_id = None
            if inv.guest_user_id:
                guest_user = db.query(User).filter(User.id == inv.guest_user_id).first()
                if guest_user:
                    email = guest_user.email
                    user_id = str(guest_user.id)
            partners.append(SessionPartner(userId=user_id, email=email))
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
            [SessionPartner(userId=str(host_user.id), email=host_user.email)]
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
        raise HTTPException(status_code=404, detail="Session not found.")

    session = db.query(SessionModel).filter(
        SessionModel.id == session_uuid,
        SessionModel.host_user_id == current_user.id,
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found or access denied.")

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
        sourceSummary=session.source_summary,
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
    request: Request,
    body: GeoBody | None = None,
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
        raise HTTPException(status_code=404, detail="Session not found.")

    session = db.query(SessionModel).filter(
        SessionModel.id == session_uuid,
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")
    if session.status != "active":
        raise HTTPException(status_code=409, detail="This session has ended.")

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
            raise HTTPException(status_code=403, detail="Access denied to this session.")

    # Mark invitation accepted
    if invitation:
        invitation.status = "accepted"
        db.commit()

    # A signed-in participant is recorded here, which is the moment they receive the
    # credentials to enter. Guests without an account are recorded elsewhere, on
    # confirm — their presence only becomes real once the microphone works.
    salon_event_service.record_entry(
        db,
        email=current_user.email or "",
        phone=current_user.phone_number or "",
        user_type="host" if is_host else "guest",
        salon_name=session.livekit_room_name,
        latitude=body.latitude if body else None,
        longitude=body.longitude if body else None,
        first_spoken_language=current_user.detected_language,
        # The client's own answer when it gave one, the header only as a fallback: an iPad
        # cannot be told from a Mac by the header alone.
        device_type=device_service.resolve(
            body.device if body else None, request.headers.get("user-agent")
        ),
    )

    token = livekit_service.generate_participant_token(
        room_name=session.livekit_room_name,
        user_id=str(current_user.id),
        display_name=current_user.email,
        can_publish=True,
    )

    return JoinSessionResponse(
        participantToken=token,
        livekitRoomName=session.livekit_room_name,
        livekitUrl=livekit_service._http_url(),
    )


@router.post("/{session_id}/heartbeat", response_model=HeartbeatResponse)
async def session_heartbeat(
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
        raise HTTPException(status_code=404, detail="Session not found.")

    session = db.query(SessionModel).filter(
        SessionModel.id == session_uuid,
        SessionModel.host_user_id == current_user.id,
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found or access denied.")
    if session.status != "active":
        raise HTTPException(status_code=409, detail="The session has ended.")

    seconds = max(0, body.seconds)
    host = db.query(User).filter(User.id == session.host_user_id).first()
    if host is not None and seconds > 0:
        host.trial_seconds_used = host.trial_seconds_used + seconds

    now = datetime.now(tz=timezone.utc)
    session.last_heartbeat_at = now
    db.commit()

    # Per-session cap, enforced here because the heartbeat is the only thing that ticks
    # reliably while a conversation is live. Doing it server-side rather than trusting the
    # agent to stop itself matters: a worker that crashes or loses its connection would
    # otherwise leave the room open and billing.
    #
    # Overshoot is bounded by the heartbeat interval — thirty seconds — which is close
    # enough for a spending guard, and far simpler than a scheduled sweep.
    started = session.created_at
    if started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)
    remaining = max(0, settings.max_session_seconds - int((now - started).total_seconds()))

    ended_now = False
    if remaining == 0:
        # Deleting the room is what actually stops the agent; finalizing only settles the
        # accounting. Same order as close_previous_host_sessions, for the same reason.
        room_name = session.livekit_room_name
        session_lifecycle.finalize_session(session, db)
        await livekit_service.delete_room(room_name)
        ended_now = True
        logger.info(
            "Session %s reached the %ds cap and was closed",
            session.id,
            settings.max_session_seconds,
        )

    # Re-read after finalize_session, which may have accrued the closing span.
    used = host.trial_seconds_used if host is not None else 0
    return HeartbeatResponse(
        sessionId=str(session.id),
        trialSecondsUsed=used,
        secondsRemaining=remaining,
        sessionEnded=ended_now,
    )


@router.get("/{session_id}/search", response_model=SourceSearchResponse)
def search_session_sources(
    session_id: str,
    q: str,
    db: DbSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Find the passages of this salon's sources that bear on a question.

    This is the other half of summarising. The agent holds a brief of a few thousand
    characters; when a participant asks about a detail the brief does not carry, it comes
    here rather than being handed the whole document — which is what the brief exists to
    avoid.

    Searches the opening source and everything added since, because a participant asking
    about "the article" does not know which of them it lives in.
    """
    import uuid as _uuid

    try:
        session_uuid = _uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Session not found.")

    session = db.query(SessionModel).filter(
        SessionModel.id == session_uuid,
        SessionModel.host_user_id == current_user.id,
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found or access denied.")

    texts = [session.source_content]
    texts += [
        src.source_content
        for src in db.query(SessionSource)
        .filter(SessionSource.session_id == session_uuid)
        .all()
    ]

    excerpts: list[str] = []
    for text in texts:
        if text:
            excerpts.extend(summary_service.search(text, q))

    # Capped after merging: three excerpts from each of four sources would be twelve
    # passages read into a live conversation, which helps nobody.
    return SourceSearchResponse(excerpts=excerpts[:4])


@router.get("/{session_id}/participant-history", status_code=200)
def participant_history(
    session_id: str,
    identity: str,
    db: DbSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Whether this participant has ever been in another salon.

    Exists so the agent can say something once to a newcomer and never again — an aside
    repeated at every salon stops being an aside.

    Answers about the participant, not the caller: the agent asks with the host's token on
    behalf of whoever just joined.
    """
    import uuid as _uuid

    try:
        session_uuid = _uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Session not found.")

    session = db.query(SessionModel).filter(
        SessionModel.id == session_uuid,
        SessionModel.host_user_id == current_user.id,
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found or access denied.")

    return {
        "firstSalon": salon_event_service.is_first_salon(
            db,
            salon_name=session.livekit_room_name,
            participant_identity=identity,
        )
    }


@router.post("/{session_id}/participant-language", status_code=200)
def record_participant_language(
    session_id: str,
    body: ParticipantLanguageBody,
    db: DbSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Record the first language heard from one participant of this salon.

    Distinct from PATCH /me/language, which sets a property of an *account*. A person may
    hold one conversation in French and the next in English, so the language belongs to
    the participation — and guests, having no account, had nowhere for it to go at all.

    Called by the agent with the host's token, which is why authorisation is ownership of
    the session rather than being the participant in question.
    """
    import uuid as _uuid

    try:
        session_uuid = _uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Session not found.")

    session = db.query(SessionModel).filter(
        SessionModel.id == session_uuid,
        SessionModel.host_user_id == current_user.id,
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found or access denied.")

    written = salon_event_service.record_first_language(
        db,
        salon_name=session.livekit_room_name,
        participant_identity=body.participantIdentity,
        language=body.language,
    )
    # 200 either way. "Already known" is the expected answer once the first report has
    # landed, and the agent has nothing useful to do with an error.
    return {"recorded": written}


@router.post("/{session_id}/end", response_model=EndSessionResponse)
async def end_session(
    session_id: str,
    body: EndSessionBody | None = None,
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
        raise HTTPException(status_code=404, detail="Session not found.")

    session = db.query(SessionModel).filter(
        SessionModel.id == session_uuid,
        SessionModel.host_user_id == current_user.id,
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found or access denied.")
    if session.status == "ended":
        raise HTTPException(status_code=409, detail="This session has already ended.")

    # Shared with the cleanup that runs before a host opens a new session, so the
    # metering clamp and the billing path cannot drift between the two.
    # The closing answer, when the agent managed to get one. The cap path above passes
    # nothing: a session cut off by its own limit was never asked the question.
    charge = session_lifecycle.finalize_session(
        session, db, enjoyed=body.enjoyed if body else None
    )
    billing_summary = BillingChargeSummary(**charge) if charge else None

    # Deleting the room disconnects everyone and stops the agent; without it the worker
    # keeps talking in a session the host believes is over.
    await livekit_service.delete_room(session.livekit_room_name)

    return EndSessionResponse(
        sessionId=str(session.id),
        status=session.status,
        endedAt=session.ended_at.isoformat(),
        billing=billing_summary,
    )


@router.post("/{session_id}/utterances", response_model=UtteranceResponse, status_code=201)
def record_utterance(
    session_id: str,
    body: UtteranceBody,
    db: DbSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Store one final turn of speech and return it in the languages being watched.

    Called by the agent with the host's token, as the other agent-facing endpoints are:
    authorisation is ownership of the session, not being the person who spoke.

    Storing and translating happen in one round trip on purpose. The caption cannot be
    published until it is translated, so a second call would sit on the critical path
    between someone finishing a sentence and the other person reading it.
    """
    import uuid as _uuid

    try:
        session_uuid = _uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Session not found.")

    session = db.query(SessionModel).filter(
        SessionModel.id == session_uuid,
        SessionModel.host_user_id == current_user.id,
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found or access denied.")

    utterance = utterance_service.record(
        db,
        session_id=session.id,
        speaker_identity=body.speakerIdentity,
        speaker_role=body.speakerRole,
        text=body.text,
        language=body.language,
    )
    if utterance is None:
        raise HTTPException(status_code=500, detail="Could not record the utterance.")

    translations: dict[str, str] = {}
    for target in body.targetLanguages:
        rendered = translation_service.translated_text(db, utterance, target)
        # Omit rather than echo the original: an absent key means "not translated", and a
        # viewer reading a caption in what they think is their language deserves to know.
        if rendered != utterance.text or translation_service.same_language(
            utterance.language, target
        ):
            translations[target] = rendered

    return UtteranceResponse(
        sequence=utterance.sequence,
        speaker=utterance_service.display_label(
            utterance.speaker_identity, utterance.speaker_role
        ),
        role=utterance.speaker_role,
        text=utterance.text,
        language=utterance.language,
        spokenAt=utterance.spoken_at.isoformat() if utterance.spoken_at else None,
        translations=translations,
    )


@router.get("/{session_id}/utterances", response_model=TranscriptResponse)
def get_transcript(
    session_id: str,
    lang: str | None = None,
    after: int = 0,
    db: DbSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """This salon's turns, in order, translated into `lang`.

    Live captions travel over the room's data channel; this exists for the viewer who
    joined late, reloaded, or changed language mid-conversation and needs what came
    before rendered again.

    `after` is a sequence number rather than a timestamp, so a client that has seen turn
    12 asks for everything above 12 and cannot lose one to a clock skew.
    """
    import uuid as _uuid

    try:
        session_uuid = _uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Session not found.")

    session = db.query(SessionModel).filter(
        SessionModel.id == session_uuid,
        SessionModel.host_user_id == current_user.id,
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found or access denied.")

    return TranscriptResponse(
        sessionId=str(session.id),
        language=lang,
        utterances=utterance_service.transcript(
            db, session_id=session.id, language=lang, after=after
        ),
    )


@router.post("/{session_id}/ad", status_code=200)
def request_ad(
    session_id: str,
    db: DbSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Run the auction for this salon and hand back the winning pitch, once.

    Called by the agent immediately after its welcome. Everything the auction needs is gathered
    here rather than passed in: the agent knows who is in the room but not where they are, what
    the salon's topics are, or what anyone bid.

    ONE PER SESSION, enforced here rather than trusted to the prompt. A model that called this
    twice would spend two of an advertiser's broadcasts and charge for both, and no instruction
    is a substitute for the check.

    Returns {"pitch": ""} when nothing is eligible. An empty pitch means say nothing at all —
    not "we have no advertisers", which would be a strange thing to announce.
    """
    import uuid as _uuid

    try:
        session_uuid = _uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Session not found.")

    session = db.query(SessionModel).filter(
        SessionModel.id == session_uuid,
        SessionModel.host_user_id == current_user.id,
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found or access denied.")

    already = (
        db.query(AdBroadcast).filter(AdBroadcast.session_id == session.id).first()
    )
    if already is not None:
        return {"pitch": "", "reason": "already_broadcast"}

    # Where the participants are and what they speak, from the participation records. Both may
    # be empty this early — someone who declined the location prompt has no position, and a
    # participant who has not spoken has no language yet. The auction treats an unknown language
    # as admitting everything, so an ad still plays.
    participations = (
        db.query(SalonEvent.plus_code, SalonEvent.first_spoken_language)
        .filter(SalonEvent.salon_name == session.livekit_room_name)
        .all()
    )
    participant_codes = [row[0] for row in participations]
    salon_languages = [row[1] for row in participations if row[1]]

    # The salon's topics exist only if the host published their source to the shared corpus.
    # Otherwise topic targeting cannot apply here, and the auction falls back to region alone —
    # deliberately, because extracting topics from a private document to place advertising is a
    # different consent from making a public page searchable.
    topics: list[str] = []
    if session.source_url:
        shared = (
            db.query(SharedSource)
            .join(SharedSourceConsent, SharedSourceConsent.source_id == SharedSource.id)
            .filter(SharedSourceConsent.session_id == session.id)
            .first()
        )
        if shared is not None:
            topics = list(shared.topics or [])

    broadcast = ad_auction_service.broadcast_winner(
        db,
        session=session,
        participant_codes=participant_codes,
        salon_topics=topics,
        salon_languages=salon_languages,
    )
    if broadcast is None:
        return {"pitch": "", "reason": "no_eligible_ad"}

    ad = db.get(Ad, broadcast.ad_id)
    return {
        # What the agent says. Rendered by it into the listener's language, so the wording here
        # is the advertiser's substance rather than a script to read verbatim.
        "pitch": ad.sales_pitch if ad else "",
        "writtenIn": ad.spoken_language if ad else "en",
    }


@router.post("/{session_id}/ad/delivered", status_code=200)
def confirm_ad_delivered(
    session_id: str,
    db: DbSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Confirm that the reserved ad was actually spoken.

    This is the moment the advertiser becomes liable. Until it arrives, the reservation costs
    them nothing — not money, not one of the broadcasts they bought — because a salon that opens
    and closes before the greeting ends must not produce a charge.

    Idempotent: a second confirmation changes nothing. The agent may retry, and a retry must not
    spend two of a purchase.
    """
    import uuid as _uuid

    try:
        session_uuid = _uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Session not found.")

    session = db.query(SessionModel).filter(
        SessionModel.id == session_uuid,
        SessionModel.host_user_id == current_user.id,
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found or access denied.")

    broadcast = (
        db.query(AdBroadcast).filter(AdBroadcast.session_id == session.id).first()
    )
    if broadcast is None:
        # Nothing was reserved, so nothing can be confirmed. Not an error: an agent that heard
        # "no ad" and confirmed anyway is harmless, and refusing would make it look like one.
        return {"delivered": False, "reason": "nothing_reserved"}

    return {"delivered": ad_auction_service.mark_delivered(db, broadcast)}


# ── The voice agent, under the host's control ────────────────────────────────
#
# Two different things, offered separately because they are not interchangeable.
#
# Pausing stops the agent hearing and speaking while it stays in the room, so it keeps
# everything it knows: who is present, what has been said, which language each person speaks.
# It is what a host wants for "let us talk among ourselves for a minute".
#
# Removing ends the job. The agent's memory of the conversation goes with it — nothing is read
# back on restart — so the next one arrives knowing only the source. That is what a host wants
# when the agent has gone wrong and should start over.


def _host_session(session_id: str, db: DbSession, current_user: User) -> SessionModel:
    try:
        session_uuid = uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Session not found.")
    session = db.query(SessionModel).filter(
        SessionModel.id == session_uuid,
        SessionModel.host_user_id == current_user.id,
    ).first()
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found or access denied.")
    return session


@router.get("/{session_id}/agent", response_model=AgentStateResponse)
async def get_agent_state(
    session_id: str,
    db: DbSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Whether the agent is in the room, and whether it is listening.

    Presence comes from LiveKit rather than from a column: it is the authority on who is in a
    room, and an agent can leave for reasons nothing here initiated. Mute has no such authority
    to consult — it lives inside the running agent — so it is the one thing recorded.
    """
    session = _host_session(session_id, db, current_user)
    return AgentStateResponse(
        present=await livekit_service.agent_is_present(session.livekit_room_name),
        muted=session.agent_muted,
    )


@router.post("/{session_id}/agent/mute", response_model=AgentStateResponse)
async def set_agent_muted(
    session_id: str,
    body: AgentMuteBody,
    db: DbSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Pause or resume the agent without taking it out of the room.

    The agent does the muting itself, on a message: only it can stop its own input, and doing
    it from here by muting its published track would silence its voice while leaving it
    listening — half a pause, and the wrong half.
    """
    session = _host_session(session_id, db, current_user)
    session.agent_muted = body.muted
    db.commit()
    await livekit_service.notify_room(
        session.livekit_room_name, {"action": "agent_mute", "muted": body.muted}
    )
    logger.info("Agent %s in session %s", "muted" if body.muted else "unmuted", session.id)
    return AgentStateResponse(present=True, muted=body.muted)


@router.post("/{session_id}/agent/disconnect", response_model=AgentStateResponse)
async def disconnect_agent(
    session_id: str,
    db: DbSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Take the agent out. Its memory of the conversation goes with it."""
    session = _host_session(session_id, db, current_user)
    await livekit_service.remove_agent(session.livekit_room_name)
    # A removed agent is not a paused one. Leaving the flag set would bring the next agent back
    # already silent, which is not what "reconnect" means to the host who asked for it.
    session.agent_muted = False
    db.commit()
    return AgentStateResponse(present=False, muted=False)


@router.post("/{session_id}/agent/connect", response_model=AgentStateResponse)
async def connect_agent(
    session_id: str,
    db: DbSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Send a fresh agent in.

    A new job with a new context: it reads the sources again and knows nothing of what was
    said. The host asked for a restart, and this is what a restart is.
    """
    session = _host_session(session_id, db, current_user)
    if session.status != "active":
        raise HTTPException(status_code=409, detail="This session is no longer active.")
    await livekit_service.dispatch_agent(
        session.livekit_room_name,
        session_id=str(session.id),
        host_token=jwt_service.issue_token(str(current_user.id)),
    )
    session.agent_muted = False
    db.commit()
    return AgentStateResponse(present=True, muted=False)
