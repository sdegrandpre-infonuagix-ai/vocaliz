"""LiveKit room provisioning and participant token generation."""
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
            detail="Impossible de créer la salle LiveKit. Veuillez réessayer.",
        ) from exc


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
