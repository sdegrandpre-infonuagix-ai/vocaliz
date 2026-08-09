"""LiveKit room provisioning, agent dispatch, and participant token generation."""
import asyncio
import json
import logging
import uuid

from fastapi import HTTPException
from livekit import api as lk_api

from src.config import settings

logger = logging.getLogger(__name__)


def _http_url() -> str:
    """Convert wss:// LiveKit URL to https:// for the REST API client."""
    return settings.livekit_url.replace("wss://", "https://").replace("ws://", "http://")


async def create_room(room_name: str, *, max_participants: int | None = None) -> None:
    """Provision a new LiveKit room. Raises HTTPException on failure.

    The size comes from the caller since Story 10.2 — a Salon is opened for the number its
    host was given, which is the persisted ceiling bounded by what they asked for. The
    environment variable remains only as the answer for a caller that names no size, so a
    room is never created without a limit at all.

    LiveKit refusing at the door is the backstop and not the mechanism: a connection that
    fails there is silent, and the API refuses first with something a person can read.
    """
    try:
        async with lk_api.LiveKitAPI(
            _http_url(), settings.livekit_api_key, settings.livekit_api_secret
        ) as client:
            await client.room.create_room(
                lk_api.CreateRoomRequest(
                    name=room_name,
                    empty_timeout=settings.livekit_room_empty_timeout,
                    max_participants=(
                        max_participants
                        if max_participants is not None
                        else settings.livekit_room_max_participants
                    ),
                )
            )
    except Exception as exc:
        # A rejected key/secret surfaces here as a 401 and is indistinguishable from an
        # outage in the client-facing 503, so log the cause rather than swallowing it.
        logger.error(
            "LiveKit create_room failed for room %s at %s: %s",
            room_name,
            _http_url(),
            exc,
            exc_info=True,
        )
        raise HTTPException(
            status_code=503,
            detail="Could not create the LiveKit room. Please try again.",
        ) from exc


SALON_AGENT_NAME = "salon-agent"


async def dispatch_agent(
    room_name: str,
    *,
    salon_id: str,
    host_token: str,
    participant_id: str,
    relay_token: str,
    follow_journal: bool,
) -> None:
    """Dispatch one participant's agent into their own room, and tell it whose it is.

    One agent per participant now, not one per Salon — each dispatch is for a single human,
    in a room that holds only them and this agent. `participant_id` is what lets the agent
    stop guessing who it is here for from how many people happen to be in the room, which is
    a race the moment a job starts before its human's browser has finished connecting.

    `host_token` and `relay_token` are two different credentials for two different things.
    `host_token` is always the host's own Vocaliz JWT — reading a Salon's source content is a
    host-only action (`GET /salons/{id}`), the same for every agent regardless of which
    participant it serves, so every dispatch carries it. `relay_token` is scoped to exactly
    this participant in this Salon (`relay_token.py`) and is what the agent presents to
    `/orchestrator/...` — a guest has no Vocaliz account to hold a JWT as, and even the host's
    account should not be handed a credential good for every Salon it will ever host.

    `follow_journal` says whether an orchestrator is actually holding this Salon. `False`
    means the agent runs the conversation it can — its own room, its own human — rather than
    asking a journal that does not exist.

    Explicit dispatch rather than room metadata, still: room metadata is readable by every
    participant, and none of these three should be. Failure is not fatal — the room exists
    and its one human can still be spoken to by whatever joined it — and is logged rather than
    surfaced as a salon error.
    """
    payload = json.dumps(
        {
            "salon_id": salon_id,
            "api_url": settings.salon_web_base_url,
            "host_token": host_token,
            "participant_id": participant_id,
            "relay_token": relay_token,
            "follow_journal": follow_journal,
        }
    )
    try:
        async with lk_api.LiveKitAPI(
            _http_url(), settings.livekit_api_key, settings.livekit_api_secret
        ) as client:
            await client.agent_dispatch.create_dispatch(
                lk_api.CreateAgentDispatchRequest(
                    agent_name=SALON_AGENT_NAME,
                    room=room_name,
                    metadata=payload,
                )
            )
    except Exception as exc:
        logger.error(
            "LiveKit agent dispatch failed for room %s: %s", room_name, exc, exc_info=True
        )


# LiveKit labels every participant with a kind; 4 is AGENT. Matched on the kind rather than on
# the identity because an agent identity is minted per job and is not knowable in advance.
_AGENT_KIND = 4

DELETE_ROOM_ATTEMPTS = 3
DELETE_ROOM_BACKOFF_SECONDS = 0.4


async def delete_room(room_name: str) -> bool:
    """Get everyone out of a room: tell them it is over, then delete it.

    Deleting the room is what disconnects the participants and stops the agent — ending the
    salon row only settles the accounting. So this is the single point where a conversation
    actually stops, and it used to swallow its failures into a warning nobody reads.

    Announced before deletion, not after, for two reasons. A deleted room cannot be sent
    anything, so afterwards is too late. And it makes the clients independent of this call
    succeeding: they leave because they were told to, not only because their transport
    dropped. That matters because a failure here left everybody sitting in a room with no
    agent and no salon behind it.

    Retried, because a transient LiveKit error is exactly the case that used to strand a
    room permanently — nothing ever tried again.

    Returns whether the room is known to be gone, so a caller can react. Still non-fatal: a
    room that outlives its salon must not block the host from opening the next one.
    """
    # Best-effort and deliberately not retried: if the room is already gone this fails, which
    # is not worth a second attempt. The deletion below is the part that must be certain.
    await notify_room(room_name, {"action": "salon_ended"})

    last: Exception | None = None
    for attempt in range(1, DELETE_ROOM_ATTEMPTS + 1):
        try:
            async with lk_api.LiveKitAPI(
                _http_url(), settings.livekit_api_key, settings.livekit_api_secret
            ) as client:
                await client.room.delete_room(lk_api.DeleteRoomRequest(room=room_name))
            return True
        except lk_api.TwirpError as exc:
            # Already collected by LiveKit, which is the outcome asked for rather than a
            # failure. Retrying would turn the ordinary case into three round trips.
            if getattr(exc, "code", None) == lk_api.TwirpErrorCode.NOT_FOUND:
                logger.info("LiveKit room %s was already gone", room_name)
                return True
            last = exc
        except Exception as exc:  # noqa: BLE001
            last = exc

        if attempt < DELETE_ROOM_ATTEMPTS:
            await asyncio.sleep(DELETE_ROOM_BACKOFF_SECONDS * attempt)

    # Error, not warning: this leaves participants connected to a room whose salon is over,
    # and the only reason it was survivable before is that nobody noticed.
    logger.error(
        "LiveKit delete_room failed for %s after %d attempts: %s",
        room_name,
        DELETE_ROOM_ATTEMPTS,
        last,
        exc_info=last,
    )
    return False


def identity_for(invitation) -> str:
    """The identity this invited participant will actually join under.

    One function because three places have to agree: the token minted for the guest, the value
    handed to the host so they can address that guest, and the participation row. If any of the
    three computed it differently, the host would hold a handle that names nobody.

    An invitation linked to an account joins under that account's UUID, not under an
    invitation-derived identity. Without this, one registered person had two identities — their
    account UUID when they joined through the app, and "guest-<invitation>" when they clicked the
    emailed link — which showed up as two rows for one human in the participant report, and
    three more if they were invited three times.

    The display name is deliberately untouched. Anonymity between participants is carried by that
    label, not by the identity, so a registered guest is still shown as "Guest 3F2A" while being
    one countable person behind the scenes.
    """
    if getattr(invitation, "guest_user_id", None):
        return str(invitation.guest_user_id)
    return guest_identity(invitation.id)


def guest_identity(invitation_id) -> str:
    """The LiveKit participant identity an invited guest joins under.

    Derived rather than random so it is knowable before the guest ever connects: the host
    receives it with the invitation, which is what allows a later message to be addressed
    to that specific guest. Keep this the single place the format is built — an identity
    computed differently in two places is an identity nothing can be addressed by.
    """
    return f"guest-{invitation_id}"


# Short enough to say out loud and to read in a participant list. The full identity stays
# the UUID — this is only how a guest is *shown*, never how one is addressed.
GUEST_LABEL_CHARS = 4


def guest_display_name(invitation_id) -> str:
    """The name other participants see for an invited guest.

    Derived from the invitation id, deliberately, and never from the guest's email: the
    name is visible to everyone in the room, and a guest invited by address did not agree
    to have that address shown to the other participants.

    Four hex characters, not the whole UUID: it has to be readable in a list and sayable
    by the agent. Two guests colliding in a single room is possible in principle and
    harmless in practice — the label only disambiguates on screen, while every actual
    lookup uses the full identity from guest_identity().

    English, matching the platform default. This is one server-side value shown to every
    participant at once, so unlike the interface it cannot follow each viewer's language.
    """
    return f"Guest {str(invitation_id).replace('-', '')[:GUEST_LABEL_CHARS].upper()}"


def display_name_of(user) -> str:
    """The name other participants see for somebody signed in.

    The name they gave when they created their account, which is required for exactly this
    reason: a listener in headphones is told "Marie says…" before what Marie said, because
    they have no screen and no second voice to ask.

    This replaced `user.email`, and that was not a matter of taste. Joining a conversation
    published your address to everybody in it — a leak nobody chose, in exchange for a poor
    thing to be called by. `guest_display_name` above had said so about guests since it was
    written; the host was the one case still doing it.

    Falls back to the same opaque shape when there is no name — a guest registered from an
    invitation was never asked for one. Derived from the identity and never from the address,
    so the absence of a name cannot reintroduce the leak by another route.
    """
    given = (getattr(user, "display_name", None) or "").strip()
    if given:
        return given
    return f"Guest {str(user.id).replace('-', '')[:GUEST_LABEL_CHARS].upper()}"


async def notify_room(
    room_name: str, message: dict, *, identities: list[str] | None = None
) -> None:
    """Publish a JSON data message to a room, or to named participants within it.

    Used to tell the agent that salon state changed mid-conversation (a source was
    added), since it otherwise only reads the salon once, at job start.

    `identities` narrows delivery to those participants; omitting it broadcasts. Note that
    an *empty* list is LiveKit's own way of saying "everyone", so passing a filtered list
    that happens to come out empty would broadcast to the room rather than to no one —
    the caller is expected to skip the send instead.

    Best-effort: a failed notification must not fail the request that triggered it.
    """
    try:
        async with lk_api.LiveKitAPI(
            _http_url(), settings.livekit_api_key, settings.livekit_api_secret
        ) as client:
            await client.room.send_data(
                lk_api.SendDataRequest(
                    room=room_name,
                    data=json.dumps(message).encode("utf-8"),
                    kind=lk_api.DataPacket.Kind.RELIABLE,
                    destination_identities=identities or [],
                )
            )
    except Exception as exc:
        logger.warning("LiveKit notify_room failed for %s: %s", room_name, exc)


def generate_participant_token(
    room_name: str,
    user_id: str,
    display_name: str = "",
    *,
    can_publish: bool = True,
) -> str:
    """Generate a short-lived LiveKit participant JWT."""
    token = (
        lk_api.AccessToken(settings.livekit_api_key, settings.livekit_api_secret)
        .with_identity(user_id)
        .with_name(display_name or user_id)
        .with_grants(
            lk_api.VideoGrants(
                room_join=True,
                room=room_name,
                can_publish=can_publish,
                can_subscribe=True,
                # Required for live captions, and easy to miss because nothing complains.
                # A participant announces the language it is reading by setting its own
                # `caption_lang` attribute; without this grant the server rejects the
                # call, the agent sees nobody asking for a translation, and captions come
                # back in the language they were spoken — which looks exactly like a
                # translator that is not working.
                can_update_own_metadata=True,
            )
        )
    )
    return token.to_jwt()


def new_room_name() -> str:
    return f"salon-{uuid.uuid4().hex[:12]}"


async def agent_is_present(room_name: str) -> bool:
    """Whether a voice agent is currently in the room.

    Read from LiveKit rather than tracked in our own column, deliberately. The agent can leave
    for reasons nothing here initiated — its worker dies, the job crashes, the room hiccups —
    and a flag we maintained would then describe a room we were no longer looking at. The
    toggle has to show what is true, not what was last requested.
    """
    try:
        async with lk_api.LiveKitAPI(
            _http_url(), settings.livekit_api_key, settings.livekit_api_secret
        ) as client:
            listed = await client.room.list_participants(
                lk_api.ListParticipantsRequest(room=room_name)
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not list participants of %s: %s", room_name, exc)
        return False
    return any(p.kind == _AGENT_KIND for p in listed.participants)


async def remove_agent(room_name: str) -> bool:
    """Take the voice agent out of the room and stop it coming back on its own.

    Two steps, and both are needed. Removing the participant ends the conversation the agent is
    in; deleting the dispatch is what stops LiveKit sending it straight back, which is what an
    explicit dispatch is designed to do.

    Returns whether an agent was actually removed, so a host toggling a room that already has
    none is told the truth rather than shown a success.
    """
    removed = False
    try:
        async with lk_api.LiveKitAPI(
            _http_url(), settings.livekit_api_key, settings.livekit_api_secret
        ) as client:
            # Dispatch first: removing the participant while the dispatch still stands invites
            # a race where the worker rejoins between the two calls.
            try:
                dispatches = await client.agent_dispatch.list_dispatch(room_name=room_name)
                for dispatch in dispatches:
                    await client.agent_dispatch.delete_dispatch(dispatch.id, room_name)
            except Exception as exc:  # noqa: BLE001
                # A dispatch that cannot be deleted is worth knowing about, but the participant
                # removal below is what the host actually asked for.
                logger.warning("Could not delete dispatches for %s: %s", room_name, exc)

            listed = await client.room.list_participants(
                lk_api.ListParticipantsRequest(room=room_name)
            )
            for participant in listed.participants:
                if participant.kind != _AGENT_KIND:
                    continue
                await client.room.remove_participant(
                    lk_api.RoomParticipantIdentity(
                        room=room_name, identity=participant.identity
                    )
                )
                removed = True
                logger.info("Removed agent %s from %s", participant.identity, room_name)
    except Exception as exc:  # noqa: BLE001
        logger.error("Could not remove the agent from %s: %s", room_name, exc, exc_info=True)
        return False
    return removed
