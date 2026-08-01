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
    readable by every participant — including anonymous browser guests. Job metadata is
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


async def notify_room(room_name: str, message: dict) -> None:
    """Publish a JSON data message to everyone in a room.

    Used to tell the agent that session state changed mid-conversation (a source was
    added), since it otherwise only reads the session once, at job start.

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
