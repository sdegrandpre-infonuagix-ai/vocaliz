"""Salons router — create and manage discussion salons."""
import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile
from sqlalchemy.orm import Session as DbSession

from src import participant_cap as participant_cap_service
from src.database import get_db
from src.dependencies.auth import get_current_user
from src.models.ad import Ad
from src.models.ad_broadcast import AdBroadcast
from src.models.salon_event import SalonEvent
from src.models.salon import Salon
from src.models.shared_source import SharedSource, SharedSourceConsent
from src.models.salon_source import SalonSource
from src.models.user import User
from src.models.invitation import Invitation
from src.schemas.salon import (
    AgentMuteBody,
    AgentStateResponse,
    BillingChargeSummary,
    EndSalonBody,
    EndSalonResponse,
    HeartbeatBody,
    ParticipantLanguageBody,
    HeartbeatResponse,
    JoinSalonResponse,
    ParticipantPresence,
    PresenceResponse,
    SalonDetailResponse,
    SalonHistoryItem,
    SalonHistoryResponse,
    SalonInvitationSummary,
    SalonPartner,
    SalonResponse,
    SalonSourceResponse,
    SalonSourceSummary,
    SourceSearchResponse,
    TranscriptResponse,
    UtteranceBody,
    UtteranceResponse,
    VoiceHealthBody,
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
    orchestrator_client,
    relay_token as relay_token_service,
    salon_event_service,
    salon_lifecycle,
    shared_source_service,
    summary_service,
    stripe_service,
    translation_service,
    utterance_service,
    xai_health,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/salons", tags=["salons"])


async def _publish_to_corpus(
    db: DbSession,
    *,
    salon_id,
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
            salon_id=salon_id,
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



def _is_front_desk(salon: Salon, db: DbSession) -> bool:
    """Whether this Salon was opened by somebody ringing the front page.

    The desk's own Salons, started from the console, are ordinary discussions — so owning it
    is not enough. A call has no source: nobody chose a document, they just rang.
    """
    if salon.source_type != "none":
        return False
    host = db.query(User).filter(User.id == salon.host_user_id).first()
    return host is not None and host.email == settings.front_desk_email


@router.post("", response_model=SalonResponse, status_code=201)
async def create_salon(
    source_url: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
    partner_email: Optional[str] = Form(None),
    language: Optional[str] = Form(None),
    # Opt-in, per source, and only ever honoured for a URL. False by default: a host who
    # says nothing has shared nothing.
    share_with_platform: bool = Form(False),
    # Story 10.2. How many people this Salon is opened for. Saying nothing takes the
    # deployment's ceiling, which is the offer; asking for more is bounded down to it rather
    # than refused, since the host asked for the biggest Salon available.
    participant_cap: Optional[int] = Form(None),
    # The same choice a guest makes at join.html's tier-choice — Base, Mode A, Mode B or
    # Mode C — now asked of the host too, at the moment they open the Salon. `host_tier` has
    # carried this since Story 8.4's billing landed; nothing before this wrote it, so every
    # host was silently billed at Base regardless of which natural voice or ad-free tier they
    # thought they were getting.
    host_tier: Optional[str] = Form(None),
    # The interpreter's voice. Every Salon ran on "ara" regardless of tier or taste; this is
    # the host choosing instead of inheriting a default nobody decided on their behalf.
    voice: Optional[str] = Form(None),
    db: DbSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Create a discussion salon from a document upload or a URL.
    Provisions a LiveKit room and returns a host participant token.

    Quick-start (Story 5.2): pass `partner_email` (a previous partner selected from
    GET /me/partners) to auto-invite that partner in the same call, so the new salon
    starts with the partner already identified — no separate invitation step needed.
    """
    from src.credit import Tier as _Tier
    from src.voices import XAI_VOICES

    # Named rather than coerced to the cheapest. Somebody sending a tier the server has
    # never heard of has a client that disagrees with it about what exists, and silently
    # downgrading them hides the disagreement behind a bill they did not expect — the same
    # reasoning `choose_guest_options` applies to a guest's choice.
    try:
        chosen_host_tier = _Tier(host_tier) if host_tier else None
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=(
                f"{host_tier!r} is not a tier. The four are "
                f"{', '.join(tier.value for tier in _Tier)}."
            ),
        ) from None

    if voice and voice not in XAI_VOICES:
        raise HTTPException(
            status_code=400,
            detail=f"{voice!r} is not a voice. Choose one of {', '.join(XAI_VOICES)}.",
        )
    # The free-trial-hour gate that used to live here is retired (FR51 replaces FR19):
    # billing is prepaid now, off the welcome credit signup grants, not a stored payment
    # method checked against a post-paid hour. No balance gate has taken its place yet —
    # that arrives with the per-Salon metering tick this cuts over to next, which is also
    # what will let somebody who has spent their credit actually top up. Until then,
    # creation is ungated: nothing here can charge anybody past what metering later finds.

    # 0. A host may never have two salons open at once. A stale salon keeps its agent
    # alive and talking, so a new room could surface the previous agent instead of its own
    # — which is precisely what happened in testing. Closing settles the metering; deleting
    # the room is what actually stops the old agent.
    closed = await salon_lifecycle.close_previous_host_salons(current_user, db)
    if closed:
        logger.info("Closed %d stale salon(s) before creating a new one", closed)

    # 1. Extract source content. A salon may start with no source at all: the agent
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

    # 2. Provision LiveKit room, sized for the number this host was given (Story 10.2).
    cap = participant_cap_service.bounded(
        participant_cap, ceiling=participant_cap_service.ceiling(db)
    )
    room_name = livekit_service.new_room_name()
    # `cap + 1`, and the `+ 1` is the agent.
    #
    # Two counts meet here and they count different things. `participant_cap` counts people —
    # `MINIMUM_CAP` is 2 precisely because one person and their interpreter is somebody
    # talking to a translation of themselves. LiveKit's `max_participants` counts everyone in
    # the room, and the agent is in the room.
    #
    # Passing one straight into the other silently sized the room one seat short. A host who
    # chose two participants got a room for two, both humans took the seats, and LiveKit
    # refused the agent — leaving exactly what was reported from production: a live audio
    # channel between two people and no interpreter at all. Nothing errored: the dispatch
    # succeeded, the worker was healthy, and the job simply could not get in.
    await livekit_service.create_room(room_name, max_participants=cap + 1)

    # 3. Generate host LiveKit token
    host_token = livekit_service.generate_participant_token(
        room_name=room_name,
        user_id=str(current_user.id),
        display_name=livekit_service.display_name_of(current_user),
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

    # 4. Persist salon
    salon = Salon(
        host_user_id=current_user.id,
        livekit_room_name=room_name,
        source_type=source_type,
        source_url=source_url,
        source_filename=source_filename,
        source_content=content,
        source_summary=summary,
        participant_cap=cap,
        host_tier=chosen_host_tier.value if chosen_host_tier else None,
        agent_voice=voice or None,
    )
    db.add(salon)
    db.commit()
    db.refresh(salon)

    # 4b. Hand the conversation to an orchestrator, and remember which one took it.
    #
    # After the row exists, not before: the request names the Salon, so there has to be a
    # Salon to name. Committed separately for the same reason it is never fatal — a Salon
    # whose orchestrator could not be reached opens without translation, which is far better
    # than a host who cannot start a conversation because a second service was restarting.
    # Null here is the honest record of that, and of the ordinary case today, where no
    # orchestrator is deployed at all.
    salon.orchestrator_url = await orchestrator_client.host_salon(
        salon_id=salon.id, room_name=room_name, host_id=current_user.id
    )
    if salon.orchestrator_url:
        db.commit()

    # Accounting only — nothing reads this back during the conversation.
    if content:
        salon_event_service.record_upload(
            db,
            salon_id=salon.id,
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
            salon_id=salon.id,
            shared_by=current_user.email,
            url=source_url,
            summary=summary,
            content=content,
            provenance=provenance,
            article_date=article_date,
        )

    # 5. Dispatch the host's own agent — one participant, one room, one interpreter — with
    # the salon context it needs to read sources, invite guests and report metering. Done
    # after the commit so the salon id exists.
    #
    # This is a Salon API JWT, not the LiveKit participant token above: the agent calls
    # our REST API with it, and passing the LiveKit token here yields 401 on every call.
    await livekit_service.dispatch_agent(
        room_name,
        salon_id=str(salon.id),
        host_token=jwt_service.issue_token(str(current_user.id)),
        participant_id=str(current_user.id),
        relay_token=relay_token_service.issue(
            salon_id=str(salon.id), participant_id=str(current_user.id)
        ),
        # False until an orchestrator actually took this Salon — set two steps above. An
        # agent told to follow a journal that does not exist would ask forever and answer
        # nobody; running the conversation it can, one room and one human, is the honest
        # fallback.
        follow_journal=bool(salon.orchestrator_url),
    )

    # Quick-start with a previous partner: auto-invite so the salon starts with
    # the partner already identified (Story 5.2). The salon is already persisted,
    # so an invitation failure surfaces to the client without losing the salon.
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
            salon_id=str(salon.id),
            host_user=current_user,
            guest_email=normalized_email,
            db=db,
        )
        invitation_summary = SalonInvitationSummary(
            invitationId=invite["invitationId"],
            invitationType=invite["invitationType"],
            guestEmail=invite["guestEmail"],
            status=invite["status"],
            joinLink=invite.get("joinLink"),
        )

    return SalonResponse(
        salonId=str(salon.id),
        livekitRoomName=room_name,
        hostToken=host_token,
        sourceType=source_type,
        createdAt=salon.created_at.isoformat(),
        invitation=invitation_summary,
    )


@router.post("/{salon_id}/sources", response_model=SalonSourceResponse, status_code=201)
async def add_salon_source(
    salon_id: str,
    source_url: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
    share_with_platform: bool = Form(False),
    db: DbSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Add an additional source (URL or document) to an active salon.
    The host, or a guest who has accepted an invitation to this salon, may call this.
    """
    salon = _salon_for_host_or_accepted_guest(salon_id, db, current_user)

    if salon.status != "active":
        raise HTTPException(status_code=409, detail="Cannot add a source to an ended salon.")

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

    source = SalonSource(
        salon_id=salon.id,
        # Whoever actually added it — the host, or now a guest — not necessarily the
        # Salon's own host. The column predates a second person ever being able to call
        # this; attribution to the real author is more useful than a name that would be
        # wrong every time a guest is the one who added it.
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
        salon_id=salon.id,
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
            salon_id=salon.id,
            shared_by=current_user.email,
            url=source_url,
            summary=summary,
            content=content,
            provenance=provenance,
            article_date=content_service.parse_article_date(
                provenance.get("article_date", "")
            ),
        )

    # The agent reads salon sources once, at job start. Without this it would never
    # learn about a source added mid-conversation (FR3).
    await livekit_service.notify_room(
        salon.livekit_room_name, {"action": "source_added", "sourceId": str(source.id)}
    )

    return SalonSourceResponse(
        sourceId=str(source.id),
        salonId=str(salon.id),
        sourceType=src_type,
        contentLength=len(content or ""),
        createdAt=source.created_at.isoformat(),
    )


@router.get("", response_model=SalonHistoryResponse)
def list_salon_history(
    db: DbSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Return the authenticated user's salon history (Story 5.1).

    Lists every salon the user took part in — as host or as an accepted guest —
    with the discussion partner(s), most recent first. A light summary only: source
    topic, date and partners. No message thread is returned (Salon keeps no transcript).
    """
    # Salons where the user was the host.
    host_salons = (
        db.query(Salon)
        .filter(Salon.host_user_id == current_user.id)
        .all()
    )

    # Salons where the user joined as an invited guest (invitation accepted).
    guest_invitations = (
        db.query(Invitation)
        .filter(
            Invitation.guest_user_id == current_user.id,
            Invitation.status == "accepted",
        )
        .all()
    )
    guest_salon_ids = {inv.salon_id for inv in guest_invitations}
    # Exclude any salon the user also hosts (can't be both) to avoid duplicates.
    host_salon_ids = {s.id for s in host_salons}
    guest_salon_ids -= host_salon_ids
    guest_salons = (
        db.query(Salon).filter(Salon.id.in_(guest_salon_ids)).all()
        if guest_salon_ids
        else []
    )

    items: list[SalonHistoryItem] = []

    # Host-role entries: partners are the invited guests.
    for s in host_salons:
        invitations = (
            db.query(Invitation).filter(Invitation.salon_id == s.id).all()
        )
        partners: list[SalonPartner] = []
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
            partners.append(SalonPartner(userId=user_id, email=email))
        items.append(
            SalonHistoryItem(
                salonId=str(s.id),
                role="host",
                sourceType=s.source_type,
                sourceUrl=s.source_url,
                status=s.status,
                createdAt=s.created_at.isoformat(),
                endedAt=s.ended_at.isoformat() if s.ended_at else None,
                partners=partners,
            )
        )

    # Guest-role entries: the partner is the salon host.
    for s in guest_salons:
        host_user = db.query(User).filter(User.id == s.host_user_id).first()
        partners = (
            [SalonPartner(userId=str(host_user.id), email=host_user.email)]
            if host_user
            else []
        )
        items.append(
            SalonHistoryItem(
                salonId=str(s.id),
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

    return SalonHistoryResponse(salons=items)


@router.get("/{salon_id}", response_model=SalonDetailResponse)
def get_salon(
    salon_id: str,
    db: DbSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Return full salon details including source content.
    Used by the agent worker at job start to build facilitation context.
    Only accessible by the salon host.
    """
    import uuid as _uuid

    try:
        salon_uuid = _uuid.UUID(salon_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Salon not found.")

    salon = db.query(Salon).filter(
        Salon.id == salon_uuid,
        Salon.host_user_id == current_user.id,
    ).first()
    if not salon:
        raise HTTPException(status_code=404, detail="Salon not found or access denied.")

    extra_sources = (
        db.query(SalonSource)
        .filter(SalonSource.salon_id == salon_uuid)
        .order_by(SalonSource.created_at)
        .all()
    )

    return SalonDetailResponse(
        salonId=str(salon.id),
        livekitRoomName=salon.livekit_room_name,
        sourceType=salon.source_type,
        sourceUrl=salon.source_url,
        sourceContent=salon.source_content,
        sourceSummary=salon.source_summary,
        additionalSources=[
            SalonSourceSummary(
                sourceId=str(s.id),
                sourceType=s.source_type,
                sourceUrl=s.source_url,
                sourceContent=s.source_content,
                contentLength=len(s.source_content or ""),
                createdAt=s.created_at.isoformat(),
            )
            for s in extra_sources
        ],
        status=salon.status,
        createdAt=salon.created_at.isoformat(),
        agentMuted=salon.agent_muted,
        hostIdentity=str(salon.host_user_id),
        agentLanguage=salon.agent_language,
        agentVoice=salon.agent_voice or "ara",
        hostTier=salon.host_tier or "Base",
        frontDesk=_is_front_desk(salon, db),
    )


@router.post("/{salon_id}/join", response_model=JoinSalonResponse)
def join_salon(
    salon_id: str,
    request: Request,
    body: GeoBody | None = None,
    db: DbSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Generate a LiveKit participant token for joining an active salon.
    Accessible by: the salon host, or any user with a pending invitation.
    Marks the invitation as accepted when a guest joins.
    """
    import uuid as _uuid
    from datetime import datetime, timezone

    try:
        salon_uuid = _uuid.UUID(salon_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Salon not found.")

    salon = db.query(Salon).filter(
        Salon.id == salon_uuid,
    ).first()
    if not salon:
        raise HTTPException(status_code=404, detail="Salon not found.")
    if salon.status != "active":
        raise HTTPException(status_code=409, detail="This salon has ended.")

    # Authorise host OR invited guest
    is_host = salon.host_user_id == current_user.id
    invitation = None
    if not is_host:
        now = datetime.now(tz=timezone.utc)
        invitation = (
            db.query(Invitation)
            .filter(
                Invitation.salon_id == salon_uuid,
                Invitation.guest_user_id == current_user.id,
                Invitation.status == "pending",
                Invitation.expires_at > now,
            )
            .first()
        )
        if not invitation:
            raise HTTPException(status_code=403, detail="Access denied to this salon.")

    # Mark invitation accepted
    if invitation:
        invitation.status = "accepted"
        db.commit()

    # A signed-in participant is recorded here, which is the moment they receive the
    # credentials to enter. Guests without an account are recorded elsewhere, on
    # confirm — their presence only becomes real once the microphone works.
    salon_event_service.record_entry(
        db,
        # The same value the LiveKit token is minted with a few lines below. One identity from
        # one source, so the row and the room agree about who this is.
        participant_identity=str(current_user.id),
        email=current_user.email or "",
        phone=current_user.phone_number or "",
        user_type="host" if is_host else "guest",
        salon_name=salon.livekit_room_name,
        salon_id=salon.id,
        latitude=body.latitude if body else None,
        longitude=body.longitude if body else None,
        first_spoken_language=current_user.detected_language,
        # The client's own answer when it gave one, the header only as a fallback: an iPad
        # cannot be told from a Mac by the header alone.
        device_type=device_service.resolve(
            body.device if body else None, request.headers.get("user-agent")
        ),
        # The browser's own locale region. Validated in the service, so anything that is not
        # two letters is dropped rather than stored.
        country=body.country if body else None,
        device_token=body.deviceToken if body else None,
    )

    token = livekit_service.generate_participant_token(
        room_name=salon.livekit_room_name,
        user_id=str(current_user.id),
        display_name=livekit_service.display_name_of(current_user),
        can_publish=True,
    )

    return JoinSalonResponse(
        participantToken=token,
        livekitRoomName=salon.livekit_room_name,
        livekitUrl=livekit_service._http_url(),
    )


@router.post("/{salon_id}/heartbeat", response_model=HeartbeatResponse)
async def salon_heartbeat(
    salon_id: str,
    body: HeartbeatBody,
    db: DbSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Record a metering heartbeat from the agent worker, and charge what elapsed.

    Called every 30 seconds by the agent. This is the tick: it is the only thing that fires
    reliably while a conversation is live, so it is where consumption is settled rather than
    at the end. Metered time is therefore not lost if the Salon ends unexpectedly.

    **Prepaid, since the Epic 8 cutover.** The host's balance is debited for their own tier
    and the Salon ends when it cannot cover what comes next — no debt is ever created. The
    host's `trial_seconds_used` is still advanced, but only as a usage counter now: nothing
    gates on it, and the free-trial hour it used to enforce is retired (FR51 replaces FR19).

    Only the host is charged here, and only for their own tier. Each guest paying for
    themselves is metered by the orchestrator, which is the component that knows every
    participant; this endpoint sees one. A host who opted to pay for everybody (FR42) is
    likewise not yet charged per head here — that arrives with the same slice, and until
    then this undercharges rather than over-, which is the right direction to be wrong in.
    """
    import uuid as _uuid
    from datetime import datetime, timezone

    from datetime import timedelta

    from src.coverage import check_coverage
    from src.credit import Tier, balance, debit
    from src.ending import (
        GUEST_NOTICE_SECONDS,
        alert_for,
        guest_notice_text,
        host_alert_text,
    )
    from src.metering import effective_rate_cents_per_hour, remaining_seconds

    try:
        salon_uuid = _uuid.UUID(salon_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Salon not found.")

    salon = db.query(Salon).filter(
        Salon.id == salon_uuid,
        Salon.host_user_id == current_user.id,
    ).first()
    if not salon:
        raise HTTPException(status_code=404, detail="Salon not found or access denied.")
    if salon.status != "active":
        raise HTTPException(status_code=409, detail="The salon has ended.")

    seconds = max(0, body.seconds)
    host = db.query(User).filter(User.id == salon.host_user_id).first()
    if host is not None and seconds > 0:
        host.trial_seconds_used = host.trial_seconds_used + seconds

    now = datetime.now(tz=timezone.utc)
    salon.last_heartbeat_at = now
    db.commit()

    # ── Charge what elapsed, then judge what comes next ───────────────────────────
    #
    # Debit before verify, which is the order `check_coverage` exists to enforce: verifying
    # first would promise a block that the debit about to happen makes impossible.
    charged = 0
    balance_cents = 0
    balance_left: int | None = None
    balance_exhausted = False
    alert_text: str | None = None

    # A Salon already in its closing sequence is not charged for it. That is the one bounded
    # exemption to "no consumption without coverage": announcing the end and asking the
    # satisfaction question are the only things a spent balance may still buy, and billing
    # them would mean charging somebody for being told they have run out.
    closing = salon.closing_at is not None

    if host is not None and not closing:
        host_tier = Tier(salon.host_tier) if salon.host_tier else Tier.BASE
        rate = effective_rate_cents_per_hour([host_tier])
        verdict = check_coverage(
            balance_cents=max(0, balance(db, host.id).total_cents),
            rate_cents_per_hour=rate,
            elapsed_seconds=seconds,
        )
        if verdict.charged_cents:
            debit(db, host.id, cents=verdict.charged_cents, now=now)
            db.commit()
            charged = verdict.charged_cents

        balance_cents = verdict.balance_after_cents
        balance_left = remaining_seconds(balance_cents, rate_cents_per_hour=rate)
        balance_exhausted = verdict.ends_salon

        # Warned while there is still time to act, and only in the payer's own room. A host
        # is warned earlier than a guest would be — the conversation of everybody they are
        # hosting depends on their balance, so they need longer to decide.
        if not balance_exhausted and balance_left is not None:
            warn = alert_for(
                remaining_seconds=balance_left,
                is_host=True,
                already_alerted=salon.balance_alerted,
            )
            if warn.due:
                guests = max(0, salon.participant_cap - 1)
                alert_text = host_alert_text(
                    remaining_seconds=balance_left, guests=guests
                )
                salon.balance_alerted = True
                db.commit()

    # How long this Salon may still run, and the answer is the balance rather than a clock.
    # There was a ten-minute age cap here; it is retired, because how long somebody may talk
    # depends on what they are paying per hour. Mode C at 22.50 buys a different amount of
    # conversation from Base at 3.00, and one number could not mean both.
    #
    # Reported in seconds of *money* so the agent can wind a conversation down rather than
    # have it stop mid-sentence. `None` when nothing is being consumed, which is not zero.
    remaining = balance_left if balance_left is not None else 0

    # ── Closing, which is not the same as closed ──────────────────────────────────
    #
    # A balance running out schedules the end rather than performing it: guests are owed
    # fifteen seconds to say goodbye, and a room that vanishes mid-sentence reads as a
    # failure rather than as somebody's balance running out. The end is carried out by
    # whichever heartbeat arrives after the deadline — or by the sweep, if the worker has
    # gone quiet in the meantime.
    ended_now = False
    closing_in: int | None = None
    closing_notice: str | None = None

    if balance_exhausted and salon.closing_at is None:
        salon.closing_at = now + timedelta(seconds=GUEST_NOTICE_SECONDS)
        db.commit()
        logger.info(
            "Salon %s closing in %ds: balance exhausted", salon.id, GUEST_NOTICE_SECONDS
        )

    if salon.closing_at is not None:
        due = salon.closing_at
        if due.tzinfo is None:
            due = due.replace(tzinfo=timezone.utc)
        left = int((due - now).total_seconds())

        if left > 0:
            closing_in = left
            closing_notice = guest_notice_text()
        else:
            # Deleting the room is what actually stops the agent; finalizing only settles
            # the accounting. Same order as close_previous_host_salons, for the same reason.
            room_name = salon.livekit_room_name
            _, guest_rooms = salon_lifecycle.finalize_salon(salon, db)
            await livekit_service.delete_room(room_name)
            await salon_lifecycle.close_guest_rooms(guest_rooms)
            ended_now = True
            logger.info("Salon %s closed: balance exhausted", salon.id)

    # Re-read after finalize_salon, which may have accrued the closing span.
    used = host.trial_seconds_used if host is not None else 0
    return HeartbeatResponse(
        salonId=str(salon.id),
        trialSecondsUsed=used,
        secondsRemaining=remaining,
        salonEnded=ended_now,
        balanceCents=balance_cents,
        chargedCents=charged,
        balanceSecondsRemaining=balance_left,
        balanceExhausted=balance_exhausted,
        closingInSeconds=closing_in,
        closingNotice=closing_notice,
        balanceAlert=alert_text,
    )


@router.get("/{salon_id}/search", response_model=SourceSearchResponse)
def search_salon_sources(
    salon_id: str,
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
        salon_uuid = _uuid.UUID(salon_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Salon not found.")

    salon = db.query(Salon).filter(
        Salon.id == salon_uuid,
        Salon.host_user_id == current_user.id,
    ).first()
    if not salon:
        raise HTTPException(status_code=404, detail="Salon not found or access denied.")

    texts = [salon.source_content]
    texts += [
        src.source_content
        for src in db.query(SalonSource)
        .filter(SalonSource.salon_id == salon_uuid)
        .all()
    ]

    excerpts: list[str] = []
    for text in texts:
        if text:
            excerpts.extend(summary_service.search(text, q))

    # Capped after merging: three excerpts from each of four sources would be twelve
    # passages read into a live conversation, which helps nobody.
    return SourceSearchResponse(excerpts=excerpts[:4])


@router.get("/{salon_id}/participant-history", status_code=200)
def participant_history(
    salon_id: str,
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
        salon_uuid = _uuid.UUID(salon_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Salon not found.")

    salon = db.query(Salon).filter(
        Salon.id == salon_uuid,
        Salon.host_user_id == current_user.id,
    ).first()
    if not salon:
        raise HTTPException(status_code=404, detail="Salon not found or access denied.")

    return {
        "firstSalon": salon_event_service.is_first_salon(
            db,
            salon_name=salon.livekit_room_name,
        salon_id=salon.id,
            participant_identity=identity,
        )
    }


@router.post("/{salon_id}/voice-health", status_code=200)
def report_voice_health(
    salon_id: str,
    body: VoiceHealthBody,
    db: DbSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """The agent reporting whether its realtime voice connection worked.

    xAI offers no cheap voice call to probe — /v1/audio/speech answers 403 for this team, and a
    realtime salon is the only test, which is too costly to open every minute. So the check is
    not a probe at all: it is the real thing, reported by the agent that just did it.

    Better than a probe in the way that matters. A substitute can succeed while the genuine path
    fails; this cannot, because it *is* the genuine path. What it gives up is warning: it says
    nothing until somebody calls, so a voice outage overnight is discovered by the first caller
    of the morning rather than before them. The scheduled text probe covers the account-level
    causes — spent credit, revoked key — which were the only two that ever actually happened.

    The salon id is not used beyond authorising the call. The health of xAI is not a property
    of one Salon, and recording it per Salon would make "is voice working" unanswerable without
    picking a room first.
    """
    logger.info(
        "Agent reported voice health: ok=%s detail=%s", body.ok, body.detail[:200]
    )
    return xai_health.record(
        db,
        service=xai_health.VOICE_SERVICE,
        healthy=body.ok,
        detail=body.detail,
    )


@router.post("/{salon_id}/participant-language", status_code=200)
def record_participant_language(
    salon_id: str,
    body: ParticipantLanguageBody,
    db: DbSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Record the first language heard from one participant of this salon.

    Distinct from PATCH /me/language, which sets a property of an *account*. A person may
    hold one conversation in French and the next in English, so the language belongs to
    the participation — and guests, having no account, had nowhere for it to go at all.

    Called by the agent with the host's token, which is why authorisation is ownership of
    the salon rather than being the participant in question.
    """
    import uuid as _uuid

    try:
        salon_uuid = _uuid.UUID(salon_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Salon not found.")

    salon = db.query(Salon).filter(
        Salon.id == salon_uuid,
        Salon.host_user_id == current_user.id,
    ).first()
    if not salon:
        raise HTTPException(status_code=404, detail="Salon not found or access denied.")

    written = salon_event_service.record_first_language(
        db,
        salon_name=salon.livekit_room_name,
        salon_id=salon.id,
        participant_identity=body.participantIdentity,
        language=body.language,
    )
    # 200 either way. "Already known" is the expected answer once the first report has
    # landed, and the agent has nothing useful to do with an error.
    return {"recorded": written}


@router.post("/{salon_id}/end", response_model=EndSalonResponse)
async def end_salon(
    salon_id: str,
    body: EndSalonBody | None = None,
    db: DbSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Mark an active salon as ended.
    Only the salon host (or the agent acting on behalf of the host) may call this.
    Idempotent: calling on an already-ended salon returns 409.
    """
    import uuid as _uuid
    from datetime import datetime, timezone

    try:
        salon_uuid = _uuid.UUID(salon_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Salon not found.")

    salon = db.query(Salon).filter(
        Salon.id == salon_uuid,
        Salon.host_user_id == current_user.id,
    ).first()
    if not salon:
        raise HTTPException(status_code=404, detail="Salon not found or access denied.")
    if salon.status == "ended":
        raise HTTPException(status_code=409, detail="This salon has already ended.")

    # Shared with the cleanup that runs before a host opens a new salon, so the
    # metering clamp and the billing path cannot drift between the two.
    # The closing answer, when the agent managed to get one. The cap path above passes
    # nothing: a salon cut off by its own limit was never asked the question.
    charge, guest_rooms = salon_lifecycle.finalize_salon(
        salon, db, enjoyed=body.enjoyed if body else None
    )
    billing_summary = BillingChargeSummary(**charge) if charge else None

    # Deleting the room stops the host's own agent; without it the worker keeps talking in
    # a salon the host believes is over. Guests are untouched here — each has their own room
    # under the per-participant topology, and keeps it unless the host was paying for
    # everyone (FR42), in which case `finalize_salon` already named their rooms above.
    await livekit_service.delete_room(salon.livekit_room_name)
    await salon_lifecycle.close_guest_rooms(guest_rooms)

    return EndSalonResponse(
        salonId=str(salon.id),
        status=salon.status,
        endedAt=salon.ended_at.isoformat(),
        billing=billing_summary,
    )


@router.post("/{salon_id}/utterances", response_model=UtteranceResponse, status_code=201)
def record_utterance(
    salon_id: str,
    body: UtteranceBody,
    db: DbSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Store one final turn of speech and return it in the languages being watched.

    Called by the agent with the host's token, as the other agent-facing endpoints are:
    authorisation is ownership of the salon, not being the person who spoke.

    Storing and translating happen in one round trip on purpose. The caption cannot be
    published until it is translated, so a second call would sit on the critical path
    between someone finishing a sentence and the other person reading it.
    """
    import uuid as _uuid

    try:
        salon_uuid = _uuid.UUID(salon_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Salon not found.")

    salon = db.query(Salon).filter(
        Salon.id == salon_uuid,
        Salon.host_user_id == current_user.id,
    ).first()
    if not salon:
        raise HTTPException(status_code=404, detail="Salon not found or access denied.")

    utterance = utterance_service.record(
        db,
        salon_id=salon.id,
        speaker_identity=body.speakerIdentity,
        speaker_role=body.speakerRole,
        speaker_name=body.speakerName,
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
            utterance.speaker_identity, utterance.speaker_role, utterance.speaker_name
        ),
        role=utterance.speaker_role,
        text=utterance.text,
        language=utterance.language,
        spokenAt=utterance.spoken_at.isoformat() if utterance.spoken_at else None,
        translations=translations,
    )


@router.get("/{salon_id}/utterances", response_model=TranscriptResponse)
def get_transcript(
    salon_id: str,
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
        salon_uuid = _uuid.UUID(salon_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Salon not found.")

    salon = db.query(Salon).filter(
        Salon.id == salon_uuid,
        Salon.host_user_id == current_user.id,
    ).first()
    if not salon:
        raise HTTPException(status_code=404, detail="Salon not found or access denied.")

    return TranscriptResponse(
        salonId=str(salon.id),
        language=lang,
        utterances=utterance_service.transcript(
            db, salon_id=salon.id, language=lang, after=after
        ),
    )


@router.post("/{salon_id}/ad", status_code=200)
def request_ad(
    salon_id: str,
    db: DbSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Run the auction for this salon and hand back the winning pitch, once.

    Called by the agent immediately after its welcome. Everything the auction needs is gathered
    here rather than passed in: the agent knows who is in the room but not where they are, what
    the salon's topics are, or what anyone bid.

    ONE PER SALON, enforced here rather than trusted to the prompt. A model that called this
    twice would spend two of an advertiser's broadcasts and charge for both, and no instruction
    is a substitute for the check.

    Returns {"pitch": ""} when nothing is eligible. An empty pitch means say nothing at all —
    not "we have no advertisers", which would be a strange thing to announce.
    """
    import uuid as _uuid

    try:
        salon_uuid = _uuid.UUID(salon_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Salon not found.")

    salon = db.query(Salon).filter(
        Salon.id == salon_uuid,
        Salon.host_user_id == current_user.id,
    ).first()
    if not salon:
        raise HTTPException(status_code=404, detail="Salon not found or access denied.")

    already = (
        db.query(AdBroadcast).filter(AdBroadcast.salon_id == salon.id).first()
    )
    if already is not None:
        return {"pitch": "", "reason": "already_broadcast"}

    # Mode B and Mode C sell exactly this: no advertising, for a rate the auction's own
    # revenue does not have to cover. Nothing enforced that before — the auction ran for
    # every Salon regardless of what its host paid for, which is not a missing feature so
    # much as a bill nobody was keeping.
    from src.credit import Tier as _Tier

    host_tier = _Tier(salon.host_tier) if salon.host_tier else _Tier.BASE
    if host_tier in (_Tier.MODE_B, _Tier.MODE_C):
        return {"pitch": "", "reason": "tier_excludes_ads"}

    # Where the participants are and what they speak, from the participation records. Both may
    # be empty this early — someone who declined the location prompt has no position, and a
    # participant who has not spoken has no language yet. The auction treats an unknown language
    # as admitting everything, so an ad still plays.
    participations = (
        db.query(SalonEvent.plus_code, SalonEvent.first_spoken_language)
        .filter(SalonEvent.salon_id == salon.id)
        .all()
    )
    participant_codes = [row[0] for row in participations]
    salon_languages = [row[1] for row in participations if row[1]]

    # The salon's topics exist only if the host published their source to the shared corpus.
    # Otherwise topic targeting cannot apply here, and the auction falls back to region alone —
    # deliberately, because extracting topics from a private document to place advertising is a
    # different consent from making a public page searchable.
    topics: list[str] = []
    if salon.source_url:
        shared = (
            db.query(SharedSource)
            .join(SharedSourceConsent, SharedSourceConsent.source_id == SharedSource.id)
            .filter(SharedSourceConsent.salon_id == salon.id)
            .first()
        )
        if shared is not None:
            topics = list(shared.topics or [])

    broadcast = ad_auction_service.broadcast_winner(
        db,
        salon=salon,
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


@router.post("/{salon_id}/ad/delivered", status_code=200)
def confirm_ad_delivered(
    salon_id: str,
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
        salon_uuid = _uuid.UUID(salon_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Salon not found.")

    salon = db.query(Salon).filter(
        Salon.id == salon_uuid,
        Salon.host_user_id == current_user.id,
    ).first()
    if not salon:
        raise HTTPException(status_code=404, detail="Salon not found or access denied.")

    broadcast = (
        db.query(AdBroadcast).filter(AdBroadcast.salon_id == salon.id).first()
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


def _salon_for_host_or_accepted_guest(
    salon_id: str, db: DbSession, current_user: User
) -> Salon:
    """Like `_host_salon`, widened to a guest who has actually accepted an invitation to
    this specific Salon — never any guest of any Salon, and never a pending one who has
    not yet arrived.

    Deliberately its own function rather than a parameter on `_host_salon`. The two named
    actions that still call `_host_salon` directly — disconnecting the agent and
    reconnecting it — end the interpreter's memory of the conversation outright, which
    stays the host's call alone; conflating the checks would make widening one an accident
    of widening the other.

    A guest reaches this with the same JWT the host has always used here: `confirm_guest_join`
    issues one from the account `register()` already creates for them, the moment they are
    genuinely present with a working microphone. No new credential type, no new dependency —
    the ownership check is the only thing that changed.
    """
    import uuid as _uuid

    try:
        salon_uuid = _uuid.UUID(salon_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Salon not found.")

    salon = db.query(Salon).filter(Salon.id == salon_uuid).first()
    if salon is None:
        raise HTTPException(status_code=404, detail="Salon not found or access denied.")

    if salon.host_user_id == current_user.id:
        return salon

    accepted_guest = (
        db.query(Invitation)
        .filter(
            Invitation.salon_id == salon.id,
            Invitation.guest_user_id == current_user.id,
            Invitation.status == "accepted",
        )
        .first()
    )
    if accepted_guest is None:
        raise HTTPException(status_code=404, detail="Salon not found or access denied.")
    return salon


def _host_salon(salon_id: str, db: DbSession, current_user: User) -> Salon:
    # Imported inside the function, as every other handler in this module does. There is no
    # module-level `uuid` here, and assuming one produced a NameError on the first click of a
    # button that had passed every test — the tests patch this module's dependencies but never
    # exercise a real request through these two endpoints.
    import uuid as _uuid

    try:
        salon_uuid = _uuid.UUID(salon_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Salon not found.")
    salon = db.query(Salon).filter(
        Salon.id == salon_uuid,
        Salon.host_user_id == current_user.id,
    ).first()
    if salon is None:
        raise HTTPException(status_code=404, detail="Salon not found or access denied.")
    return salon


@router.get("/{salon_id}/presence", response_model=PresenceResponse)
async def get_presence(
    salon_id: str,
    db: DbSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Who is currently connected to this salon.

    Under the per-participant topology there is no one room to list — the host and every
    accepted guest each have their own, so this is an aggregate over all of them rather than
    a single room's participant list.

    The host, or a guest who has accepted an invitation to this salon, may read this.
    """
    salon = _salon_for_host_or_accepted_guest(salon_id, db, current_user)

    host = db.query(User).filter(User.id == salon.host_user_id).first()
    accepted_guests = (
        db.query(Invitation)
        .filter(Invitation.salon_id == salon.id, Invitation.status == "accepted")
        .all()
    )

    # (room, name, role) for everyone who has ever accepted a seat — a guest with no room
    # yet has never actually connected, so their presence is known without asking LiveKit.
    entries = [
        (salon.livekit_room_name, livekit_service.display_name_of(host) if host else "Host", "host")
    ]
    pending_guests = []
    for invitation in accepted_guests:
        # Matches the name LiveKit itself shows this guest under — set once, at token
        # generation time, as their given name or else this same anonymised fallback — never
        # `display_name_of`'s own id-derived one, which a registered-but-nameless guest would
        # otherwise be shown under here and nowhere else.
        guest_user = (
            db.query(User).filter(User.id == invitation.guest_user_id).first()
            if invitation.guest_user_id
            else None
        )
        given_name = (getattr(guest_user, "display_name", None) or "").strip()
        name = given_name or livekit_service.guest_display_name(invitation.id)
        if invitation.livekit_room_name is None:
            pending_guests.append(ParticipantPresence(name=name, role="guest", connected=False))
        else:
            entries.append((invitation.livekit_room_name, name, "guest"))

    connected = await asyncio.gather(
        *(livekit_service.human_is_present(room) for room, _, _ in entries)
    )
    participants = [
        ParticipantPresence(name=name, role=role, connected=is_connected)
        for (_, name, role), is_connected in zip(entries, connected)
    ]
    participants.extend(pending_guests)
    return PresenceResponse(participants=participants)


@router.get("/{salon_id}/agent", response_model=AgentStateResponse)
async def get_agent_state(
    salon_id: str,
    db: DbSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Whether the agent is in the room, and whether it is listening.

    Presence comes from LiveKit rather than from a column: it is the authority on who is in a
    room, and an agent can leave for reasons nothing here initiated. Mute has no such authority
    to consult — it lives inside the running agent — so it is the one thing recorded.

    The host, or a guest who has accepted an invitation to this salon, may read this.
    """
    salon = _salon_for_host_or_accepted_guest(salon_id, db, current_user)
    return AgentStateResponse(
        present=await livekit_service.agent_is_present(salon.livekit_room_name),
        muted=salon.agent_muted,
    )


@router.post("/{salon_id}/agent/mute", response_model=AgentStateResponse)
async def set_agent_muted(
    salon_id: str,
    body: AgentMuteBody,
    db: DbSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Pause or resume the agent without taking it out of the room.

    The agent does the muting itself, on a message: only it can stop its own input, and doing
    it from here by muting its published track would silence its voice while leaving it
    listening — half a pause, and the wrong half.

    The host, or a guest who has accepted an invitation to this salon, may pause or resume it.
    Removing the agent outright stays the host's call alone — see `_host_salon`.
    """
    salon = _salon_for_host_or_accepted_guest(salon_id, db, current_user)
    salon.agent_muted = body.muted
    db.commit()
    await livekit_service.notify_room(
        salon.livekit_room_name, {"action": "agent_mute", "muted": body.muted}
    )
    logger.info("Agent %s in salon %s", "muted" if body.muted else "unmuted", salon.id)
    return AgentStateResponse(present=True, muted=body.muted)


@router.post("/{salon_id}/agent/disconnect", response_model=AgentStateResponse)
async def disconnect_agent(
    salon_id: str,
    db: DbSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Take the agent out. Its memory of the conversation goes with it."""
    salon = _host_salon(salon_id, db, current_user)
    await livekit_service.remove_agent(salon.livekit_room_name)
    # A removed agent is not a paused one. Leaving the flag set would bring the next agent back
    # already silent, which is not what "reconnect" means to the host who asked for it.
    salon.agent_muted = False
    db.commit()
    return AgentStateResponse(present=False, muted=False)


@router.post("/{salon_id}/agent/connect", response_model=AgentStateResponse)
async def connect_agent(
    salon_id: str,
    db: DbSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Send a fresh agent in.

    A new job with a new context: it reads the sources again and knows nothing of what was
    said. The host asked for a restart, and this is what a restart is.
    """
    salon = _host_salon(salon_id, db, current_user)
    if salon.status != "active":
        raise HTTPException(status_code=409, detail="This salon is no longer active.")
    await livekit_service.dispatch_agent(
        salon.livekit_room_name,
        salon_id=str(salon.id),
        host_token=jwt_service.issue_token(str(current_user.id)),
        participant_id=str(current_user.id),
        relay_token=relay_token_service.issue(
            salon_id=str(salon.id), participant_id=str(current_user.id)
        ),
        follow_journal=bool(salon.orchestrator_url),
    )
    salon.agent_muted = False
    db.commit()
    return AgentStateResponse(present=True, muted=False)


@router.post("/{salon_id}/microphone", status_code=204)
def report_microphone_working(
    salon_id: str,
    db: DbSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """The host's microphone is working. Reported by the page, which is the only party to know.

    A guest needs no equivalent: their page calls guest-join/confirm from the same
    microphone-success branch and nowhere else, so reaching that endpoint is already the
    evidence. A host obtains credentials before touching their microphone, so the two moments
    are separate and only they can report the second.

    Recorded because two states looked identical and needed opposite responses: somebody who
    never tried to speak, and somebody who tried and was not heard. Read with
    first_spoken_language, this separates them.

    204 and never an error: this is an observation about a conversation, and failing to record
    one must not interrupt it.
    """
    salon = _host_salon(salon_id, db, current_user)
    salon_event_service.record_entry(
        db,
        participant_identity=str(current_user.id),
        email=current_user.email or "",
        phone=current_user.phone_number or "",
        user_type="host",
        salon_name=salon.livekit_room_name,
        salon_id=salon.id,
        microphone_enabled=True,
    )
    return Response(status_code=204)
