"""Redispatching an agent that left its room on its own — the other half of a webhook.

An agent's own job ending, with a human still in the room, is not the same event as a Salon
ending. LiveKit's agent dispatch (`livekit_service.dispatch_agent`) is a one-shot request made
when the room was created — not a standing rule LiveKit re-enforces — so if that job exits for
a reason nobody asked for (a realtime connection `following.follow` gave up on, see its
`on_unrecoverable`), nothing sends a replacement unless something here does.

Reconstructs the same dispatch this room's agent was given originally, by finding which Salon,
and which participant, the room belongs to. Two lookups because the per-participant topology
keeps them in two different places: the host's own room is named on the Salon row itself
(`salons.livekit_room_name`); a guest's is named on their invitation
(`invitations.livekit_room_name`) — see `routers.invitations.guest_join_salon`'s own comment on
why a guest never shares the host's room name.
"""
import logging

from sqlalchemy.orm import Session as DbSession

from src.models.invitation import Invitation
from src.models.salon import Salon
from src.services import jwt_service, livekit_service
from src.services import relay_token as relay_token_service

logger = logging.getLogger(__name__)


async def redispatch_for_room(db: DbSession, room_name: str) -> bool:
    """Send a fresh agent into `room_name`, if it still belongs to a Salon that is not over.

    Returns whether a dispatch was actually sent. False is the ordinary answer for a room
    whose Salon has already ended by the time this runs — the agent leaving was then the
    normal departure `finalize_salon` already causes, not the failure this exists to answer.
    """
    salon = (
        db.query(Salon)
        .filter(Salon.livekit_room_name == room_name, Salon.status == "active")
        .first()
    )
    if salon is not None:
        await livekit_service.dispatch_agent(
            room_name,
            salon_id=str(salon.id),
            host_token=jwt_service.issue_token(str(salon.host_user_id)),
            participant_id=str(salon.host_user_id),
            relay_token=relay_token_service.issue(
                salon_id=str(salon.id), participant_id=str(salon.host_user_id)
            ),
            follow_journal=bool(salon.orchestrator_url),
        )
        logger.info("Redispatched the host's own agent for salon %s", salon.id)
        return True

    invitation = (
        db.query(Invitation)
        .filter(Invitation.livekit_room_name == room_name, Invitation.status == "accepted")
        .first()
    )
    if invitation is not None and invitation.salon_id is not None:
        salon = (
            db.query(Salon)
            .filter(Salon.id == invitation.salon_id, Salon.status == "active")
            .first()
        )
        if salon is not None:
            guest_id = livekit_service.identity_for(invitation)
            await livekit_service.dispatch_agent(
                room_name,
                salon_id=str(salon.id),
                host_token=jwt_service.issue_token(str(salon.host_user_id)),
                participant_id=guest_id,
                relay_token=relay_token_service.issue(
                    salon_id=str(salon.id), participant_id=guest_id
                ),
                follow_journal=bool(salon.orchestrator_url),
            )
            logger.info(
                "Redispatched a guest's own agent for salon %s (invitation %s)",
                salon.id,
                invitation.id,
            )
            return True

    logger.info("No active salon owns room %s; nothing to redispatch", room_name)
    return False
