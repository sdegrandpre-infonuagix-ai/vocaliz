"""Invitations router — voice-triggered guest invitations."""
import uuid as _uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session as DbSession

from src.config import settings
from src.database import get_db
from src.dependencies.auth import get_current_user
from src.models.invitation import Invitation
from src.models.salon import Salon
from src.models.user import User
from src.schemas.invitation import (
    GeoBody,
    GuestJoinResponse,
    GuestOptionsBody,
    GuestOptionsResponse,
    InvitationResponse,
    InviteGuestBody,
    PendingInvitationResponse,
)
from src import participant_cap as participant_cap_service
from src.credit import Tier
from src.participation import join_options
from src.rate_limit import limiter
from src.signup import InvalidRegistration, identifiers_of, register
from src.services import voice_languages
from src.services.voice_languages import FOLLOW_THE_SPEAKER
from src.services import (
    device_service,
    jwt_service,
    invitation_service,
    livekit_service,
    salon_code_service,
    salon_event_service,
    utterance_service,
)

router = APIRouter(prefix="/salons", tags=["invitations"])
guest_router = APIRouter(prefix="/invitations", tags=["guest"])


@router.post(
    "/{salon_id}/invitations/anonymous",
    response_model=InvitationResponse,
    status_code=201,
)
def create_anonymous_invitation(
    salon_id: str,
    db: DbSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Gone since Story 10.1. There is no such thing as a join link addressed to nobody.

    A link with no identifier on it left nothing to hold the ten free minutes against:
    somebody who had used theirs got them back by arriving again as a stranger, and no
    accounting downstream could notice. Every way into a Salon now carries an address or a
    number.

    Answered rather than deleted, and 410 rather than 404. A client still calling this is
    running an old build, and "this is gone, here is what replaced it" is an answer somebody
    can act on where a not-found reads as a bug in the URL.
    """
    raise HTTPException(
        status_code=410,
        detail=(
            "Invitations without an address or a phone number are no longer issued. "
            "Invite your guest on POST /salons/{salon_id}/invitations with whichever of "
            "the two you have."
        ),
    )


@router.post("/{salon_id}/invitations", response_model=InvitationResponse, status_code=201)
def create_invitation(
    salon_id: str,
    body: InviteGuestBody,
    db: DbSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        result = invitation_service.invite_guest(
            salon_id=salon_id,
            host_user=current_user,
            guest_email=body.guestEmail,
            guest_phone=body.guestPhone,
            db=db,
        )
    except ValueError as exc:
        if str(exc) == "salon_not_found":
            raise HTTPException(status_code=404, detail="Salon not found or access denied")
        if str(exc) == "contact_required":
            raise HTTPException(
                status_code=400,
                detail="An email address or a phone number is required.",
            )
        raise HTTPException(status_code=400, detail=str(exc))

    # Nothing is announced to the room any more. An invitation used to start a countdown after
    # which the agent opened the conversation by itself; the host now decides when the agent
    # speaks, so an invitation is an invitation and no longer a starting pistol.

    return result


@router.post("/{salon_id}/invitations/{invitation_id}/email", status_code=200)
def resend_invitation_email(
    salon_id: str,
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
def guest_join_salon(
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

    # Used and abandoned are both refusals and they are not the same refusal (Story 10.3).
    # Telling somebody who never opened their invitation that it has already been used tells
    # them somebody else got in with their link — an accusation rather than an error, and the
    # support call it produces is about an incident that did not happen.
    if invitation.status == "accepted":
        raise HTTPException(status_code=410, detail="This link has already been used.")
    if invitation.status != "pending":
        raise HTTPException(
            status_code=410,
            detail="This Salon has ended, so this link is no longer valid.",
        )

    expires = invitation.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires < now:
        raise HTTPException(status_code=410, detail="This link has expired.")

    salon = db.query(Salon).filter(
        Salon.id == invitation.salon_id,
    ).first()
    if not salon or salon.status != "active":
        raise HTTPException(status_code=410, detail="This salon is no longer available.")

    # Story 10.2, replacing FR2. Refused here, with words, rather than left to LiveKit's own
    # limit: that one rejects the connection silently, and a guest whose link simply does not
    # work has no way to tell a full Salon from a broken one.
    #
    # Counted as seats given, not heads currently present. A spent invitation is spent whether
    # or not its guest is still in the room, and a seat that came back when somebody closed a
    # tab would let a fourth person in behind the host's back.
    if invitation.status == "pending":
        taken = 1 + db.query(Invitation).filter(
            Invitation.salon_id == salon.id,
            Invitation.status == "accepted",
        ).count()
        if participant_cap_service.is_full(taken, cap=salon.participant_cap):
            raise HTTPException(
                status_code=409,
                detail=participant_cap_service.room_full_message(
                    cap=salon.participant_cap
                ),
            )

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
    guest_id = livekit_service.identity_for(invitation)
    token = livekit_service.generate_participant_token(
        room_name=salon.livekit_room_name,
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
        livekitRoomName=salon.livekit_room_name,
        livekitUrl=livekit_service._http_url(),
        salonId=str(salon.id),
        participantIdentity=guest_id,
        participantName=livekit_service.guest_display_name(invitation.id),
        hostPaysAll=bool(salon.host_pays_all),
    )


@guest_router.post(
    "/guest-join/{join_token}/options", response_model=GuestOptionsResponse
)
def choose_guest_options(
    join_token: str,
    body: GuestOptionsBody | None = None,
    db: DbSession = Depends(get_db),
):
    """Settle a guest's three options from the join screen (Story 10.4 / FR35, FR42).

    Story 8.4 decided what happens when somebody chooses — the table, the upward-only host
    override, the credit spent before money is asked for — and never grew a way to *ask*. This
    is that way, and it is the join screen's only call on the subject.

    Three answers in one request because they are answered together on one screen. Three calls
    would let somebody enter having answered two of them.

    No authentication: the invitation carries the identifier since Story 10.1, so the person is
    resolved from the link rather than from a session a guest does not have.
    """
    body = body or GuestOptionsBody()

    invitation = db.query(Invitation).filter(
        Invitation.join_token == join_token,
    ).first()
    if not invitation:
        raise HTTPException(status_code=404, detail="Invalid or unknown link.")

    salon = db.query(Salon).filter(Salon.id == invitation.salon_id).first()
    if invitation.status == "expired" or salon is None or salon.status != "active":
        # Options for a conversation that is over would be a row nobody can act on, written
        # after the only moment it could have mattered.
        raise HTTPException(
            status_code=410,
            detail="This Salon has ended, so there is nothing left to choose.",
        )

    # Named rather than coerced to the cheapest. Somebody sending a tier the server has never
    # heard of has a client that disagrees with it about what exists, and silently downgrading
    # them hides the disagreement behind a bill they did not expect.
    try:
        chosen = Tier(body.tier) if body.tier else None
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=(
                f"{body.tier!r} is not a tier. The four are "
                f"{', '.join(tier.value for tier in Tier)}."
            ),
        ) from None

    try:
        person = register(db, email=invitation.guest_email, phone=invitation.guest_phone)
    except InvalidRegistration as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    settled = join_options(
        db,
        salon_id=salon.id,
        user_id=person.id,
        chosen_tier=chosen,
        video=body.video,
        top_up_cents=body.topUpCents,
        host_pays=bool(salon.host_pays_all),
    )
    db.commit()

    return GuestOptionsResponse(
        tier=settled.tier,
        video=settled.video,
        topUpCents=settled.top_up_cents,
        coveredByCreditMinutes=settled.covered_by_credit_minutes,
        paymentRequired=settled.payment_required,
        choiceOffered=settled.choice_offered,
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

    # Idempotent for a guest who is *in*, which is what the retry it forgives looks like.
    # Somebody arriving on a link that was closed when the Salon ended was never in it, and
    # answering 200 would record a participant in a conversation that is over (Story 10.3).
    if invitation.status not in ("pending", "accepted"):
        raise HTTPException(
            status_code=410,
            detail="This Salon has ended, so this link is no longer valid.",
        )

    if invitation.status == "pending":
        invitation.status = "accepted"
        db.commit()

    # Story 10.1. The moment somebody is genuinely present is the moment their identifier has
    # to key their allowance — every invitation now carries one, since the link addressed to
    # nobody is gone. Registering here rather than when the host typed it: an invitation that
    # was never accepted is somebody who never arrived, and minting them an account would
    # count a person who has not been in a Salon.
    #
    # Never fatal. A guest whose microphone has just started working must not be thrown out
    # because two identifiers turned out to belong to two people; that is a support question,
    # and the participation is recorded either way.
    try:
        register(db, email=invitation.guest_email, phone=invitation.guest_phone)
        db.commit()
    except InvalidRegistration:
        db.rollback()

    # Recorded here rather than when the credentials were fetched: this is the first
    # moment the guest is genuinely present — microphone working, able to be heard.
    salon = db.query(Salon).filter(
        Salon.id == invitation.salon_id,
    ).first()
    if salon is not None:
        salon_event_service.record_entry(
            db,
            # Derived from the invitation, exactly as this guest's LiveKit token is. It is what
            # lets an anonymous guest be recorded at all: they have no address, and while the
            # key demanded one such a participation was refused and they appeared nowhere.
            participant_identity=livekit_service.identity_for(invitation),
            # Whichever half the host supplied, when there is one. Now an attribute of the row
            # rather than part of its key — it says how to reach somebody, not which
            # participant this is.
            email=invitation.guest_email or "",
            phone=invitation.guest_phone or "",
            user_type="guest",
            salon_name=salon.livekit_room_name,
        salon_id=salon.id,
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
    no weaker, and the only one they hold. A guest has no API salon, so requiring the host's
    would mean the feature could never reach them.

    Bounded to the guest's own salon: the token names one invitation, which names one salon.
    """
    invitation = db.query(Invitation).filter(Invitation.join_token == join_token).first()
    if invitation is None:
        raise HTTPException(status_code=404, detail="Invitation not found.")

    # Expiry is not checked. A conversation in progress outliving its invitation window is
    # possible, and cutting a participant's captions mid-sentence over a timestamp would be a
    # strange way to enforce it — the room membership is what governs whether they are present.
    salon = db.query(Salon).filter(
        Salon.id == invitation.salon_id,
    ).first()
    if salon is None:
        raise HTTPException(status_code=404, detail="Salon not found.")

    return {
        "salonId": str(salon.id),
        # Echoed so a client can tell which language it is looking at: requests can land out of
        # order, and a stale reply must not overwrite a newer choice.
        "language": lang,
        "utterances": utterance_service.transcript(
            db, salon_id=salon.id, language=lang, after=after
        ),
    }


@guest_router.post("/dial/{code}", response_model=GuestJoinResponse)
def dial_in(code: str, db: DbSession = Depends(get_db)):
    """Join a salon by six-digit code, the way somebody on a telephone would.

    The codes have existed since migration 022 — minted for every invitation, reserved in a
    pool, released when the salon ends — and until now nothing could redeem one. There is no
    SIP trunk and no dispatch rule, so the telephone leg the codes were built for does not
    exist yet; this is the same door, opened from a browser.

    Deliberately the same lookup a dialled call would use, rather than a shortcut written for
    the simulation. What is exercised here — the pool, the reservation, the invitation behind
    the code — is what the telephone will exercise later, so the parts that will matter then
    are the parts being used now.

    The code is not spent. A telephone call drops, and somebody who has to ask their host for
    a fresh code because the line cut out has been failed by the product, not by the network.
    It stops working when the salon ends, which is when the code returns to the pool.
    """
    invitation = salon_code_service.invitation_for_code(db, code)
    if invitation is None:
        # One message for an unknown code and for a code whose salon is over. Distinguishing
        # them would let anybody sweep the six-digit space and learn which salons exist.
        raise HTTPException(status_code=404, detail="No Salon is reachable with that code.")

    salon = db.query(Salon).filter(
        Salon.id == invitation.salon_id,
    ).first()
    if not salon or salon.status != "active":
        raise HTTPException(status_code=404, detail="No Salon is reachable with that code.")

    caller_id = livekit_service.identity_for(invitation)
    token = livekit_service.generate_participant_token(
        room_name=salon.livekit_room_name,
        user_id=caller_id,
        display_name=livekit_service.guest_display_name(invitation.id),
        can_publish=True,
    )

    # Recorded as a telephone participant. It is a browser today, but what matters to anyone
    # reading the report is that this person had no screen — no captions, no controls, nothing
    # but the voice — and that is true of the simulation exactly as it will be of the call.
    salon_event_service.record_entry(
        db,
        participant_identity=caller_id,
        email=invitation.guest_email or "",
        phone=invitation.guest_phone or "",
        user_type="guest",
        salon_name=salon.livekit_room_name,
        salon_id=salon.id,
        latitude=None,
        longitude=None,
        first_spoken_language="",
        device_type="telephone",
    )

    return GuestJoinResponse(
        participantToken=token,
        livekitRoomName=salon.livekit_room_name,
        livekitUrl=livekit_service._http_url(),
        salonId=str(salon.id),
        participantIdentity=caller_id,
        participantName=livekit_service.guest_display_name(invitation.id),
    )


@guest_router.post("/call-the-desk", response_model=GuestJoinResponse)
@limiter.limit(f"{settings.front_desk_calls_per_hour}/hour")
async def call_the_desk(
    request: Request,
    language: str = FOLLOW_THE_SPEAKER,
    email: str = "",
    phone: str = "",
    db: DbSession = Depends(get_db),
):
    """Ring the front desk from the front page, with no account and no code.

    A Salon is opened in the desk's name, the caller is put into it, and the desk is mailed
    the invitation. That is the whole of a telephone call, minus the telephone: somebody who
    has never heard of Vocaliz presses one button and is in a room with an agent, and the
    person who answers finds out by email.

    An address or a number is required since Story 10.1 — the one thing that changed. It is
    still no account and no code: nothing is verified, nothing is signed in to, and either
    channel will do. What it buys is a key to hold the ten free minutes against, without which
    ringing again is how somebody gets a fresh allowance for the price of pressing a button.

    Public, and therefore rate-limited across everybody rather than per address. The limit is
    deliberately low: the endpoint creates a Salon and sends an email with no authentication at
    all, which is exactly the shape somebody automates, and the failure it prevents is a
    thousand Salons and a thousand emails arriving overnight.

    Two invitations, not one. The caller's is never sent anywhere; it exists to give them an
    identity the room can name and the report can count. The desk's is addressed and mailed,
    which is what tells a human that somebody is waiting.
    """
    try:
        identifiers_of(email=email, phone=phone)
    except InvalidRegistration as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    desk = db.query(User).filter(User.email == settings.front_desk_email).first()
    if desk is None:
        # Not created on the fly. An account minted by an anonymous request would be an
        # account anybody could mint, and the desk address is the one that reads the reports.
        raise HTTPException(status_code=503, detail="The desk is not available.")

    room_name = livekit_service.new_room_name()
    await livekit_service.create_room(room_name)

    salon = Salon(
        host_user_id=desk.id,
        livekit_room_name=room_name,
        # No source. A caller rings about whatever they are ringing about, and a Salon built
        # around a document would have the agent open on a subject nobody chose.
        source_type="none",
        source_content="",
        # Rejected quietly rather than refused. A caller who picked something the model cannot
        # speak should still reach the desk; falling back to following them is the behaviour
        # they would have had by not choosing at all, and it is the closest thing to what they
        # asked for. Refusing the call over a language would be the worse trade by far.
        agent_language=(
            language if voice_languages.is_supported(language) else FOLLOW_THE_SPEAKER
        ),
        # Not paused, unlike every other Salon. Pausing exists so a host decides when their
        # Salon begins — but a caller is not a host, there is no button in front of them, and
        # nobody else is in the room yet to press one. An agent that joined this Salon in
        # silence would leave somebody who just rang listening to nothing at all.
        agent_muted=False,
    )
    db.add(salon)
    db.commit()
    db.refresh(salon)

    await livekit_service.dispatch_agent(
        room_name,
        salon_id=str(salon.id),
        host_token=jwt_service.issue_token(str(desk.id)),
    )

    caller = invitation_service.invite_caller(
        salon_id=str(salon.id), host_user=desk, db=db, email=email, phone=phone
    )
    # Mailed, which is the point of this one. A failure to send is logged inside the service
    # and costs the notification, never the call — the caller is already in the room.
    invitation_service.invite_guest(
        salon_id=str(salon.id),
        host_user=desk,
        guest_email=settings.front_desk_email,
        guest_phone="",
        db=db,
    )

    invitation = db.query(Invitation).filter(
        Invitation.id == _uuid.UUID(caller["invitationId"]),
    ).one()
    caller_id = livekit_service.identity_for(invitation)

    # Read back off the invitation, which now carries it (Story 10.1). An address that
    # failed to look like one is dropped here rather than at the door: `identifiers_of` has
    # already accepted the pair, so somebody who gave a number and mistyped an address still
    # gets through — the address buys them a copy of the conversation, not the call itself.
    caller_email = invitation.guest_email or ""
    if caller_email and "@" not in caller_email:
        caller_email = ""

    salon_event_service.record_entry(
        db,
        participant_identity=caller_id,
        email=caller_email,
        user_type="guest",
        salon_name=room_name,
        latitude=None,
        longitude=None,
        first_spoken_language="",
        device_type="telephone",
    )

    return GuestJoinResponse(
        participantToken=livekit_service.generate_participant_token(
            room_name=room_name,
            user_id=caller_id,
            display_name=livekit_service.guest_display_name(invitation.id),
            can_publish=True,
        ),
        livekitRoomName=room_name,
        livekitUrl=livekit_service._http_url(),
        salonId=str(salon.id),
        participantIdentity=caller_id,
        participantName=livekit_service.guest_display_name(invitation.id),
    )
