"""LiveKit room provisioning, agent dispatch, and participant token generation."""
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


async def create_room(room_name: str) -> None:
    """Provision a new LiveKit room. Raises HTTPException on failure."""
    try:
        async with lk_api.LiveKitAPI(
            _http_url(), settings.livekit_api_key, settings.livekit_api_secret
        ) as client:
            await client.room.create_room(
                lk_api.CreateRoomRequest(
                    name=room_name,
                    empty_timeout=settings.livekit_room_empty_timeout,
                    max_participants=settings.livekit_room_max_participants,
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


async def dispatch_agent(room_name: str, *, session_id: str, host_token: str) -> None:
    """Dispatch the Salon agent into a room, handing it the session context it needs.

    Explicit dispatch rather than room metadata: the agent needs the host's JWT to read
    session sources and send invitations on the host's behalf, and room metadata is
    readable by every participant — including browser guests. Job metadata is
    not, so the token stays out of reach.

    Failure is not fatal: the room already exists and participants can talk. The agent
    simply will not join, which is logged rather than surfaced as a session error.
    """
    payload = json.dumps(
        {
            "session_id": session_id,
            "api_url": settings.salon_web_base_url,
            "host_token": host_token,
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


async def delete_room(room_name: str) -> None:
    """Delete a room, disconnecting everyone and stopping its agent.

    This is what actually silences a stale agent: ending the session row settles the
    accounting, but the worker keeps running until its room disappears.

    Best-effort — a room that is already gone, or a LiveKit outage, must not block the
    caller from opening a new session.
    """
    try:
        async with lk_api.LiveKitAPI(
            _http_url(), settings.livekit_api_key, settings.livekit_api_secret
        ) as client:
            await client.room.delete_room(lk_api.DeleteRoomRequest(room=room_name))
    except Exception as exc:
        logger.warning("LiveKit delete_room failed for %s: %s", room_name, exc)


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


async def notify_room(
    room_name: str, message: dict, *, identities: list[str] | None = None
) -> None:
    """Publish a JSON data message to a room, or to named participants within it.

    Used to tell the agent that session state changed mid-conversation (a source was
    added), since it otherwise only reads the session once, at job start.

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
            )
        )
    )
    return token.to_jwt()


def new_room_name() -> str:
    return f"salon-{uuid.uuid4().hex[:12]}"
