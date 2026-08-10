"""The `Notifier` port, answered by calling the API back.

Lives outside `src/` for the same reason `livekit_rooms.py` does: the domain must not name a
transport, and this is where one is named. The orchestrator has no route to LiveKit's data
channel for a served seat — that channel is the agent's, on the other side of the VPC
boundary — so waking one is necessarily a call to something that does, and the API already
holds `notify_room` for exactly this shape of message (`agent_mute`, `source_added`).

A shared secret rather than a per-participant credential: this call carries no content and
authorises nothing about a Salon it could not already reach by being inside the VPC that
holds it. What it proves is only "this really is the orchestrator," which is what stops the
API relaying a wake nobody but this process should be able to ask for.
"""
from __future__ import annotations

import logging

import httpx

logger = logging.getLogger("orchestrator")

# Short, on purpose. This is a courtesy for a fast path; the poll behind it is the correctness
# guarantee, so a slow answer here is better abandoned than waited for — the conversation has
# moved on by the time a straggling call would land.
TIMEOUT_SECONDS = 3.0


class HttpNotifier:
    """Tells the API a participant is owed a wake, over one POST and nothing else.

    Never raises: every failure is the caller's cue that the fast path did not work this
    time, which the poll behind it was always going to cover anyway.
    """

    def __init__(self, *, base_url: str, secret: str) -> None:
        self._base = base_url.rstrip("/")
        self._secret = secret

    async def notify(self, salon_id: str, participant_id: str) -> None:
        if not self._base or not self._secret:
            return
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
                response = await client.post(
                    f"{self._base}/orchestrator/wake",
                    json={"salonId": salon_id, "participantId": participant_id},
                    headers={"Authorization": f"Bearer {self._secret}"},
                )
            if response.status_code >= 400:
                logger.warning(
                    "wake for %s in salon %s answered %d",
                    participant_id,
                    salon_id,
                    response.status_code,
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "could not wake %s in salon %s: %s(%s)",
                participant_id,
                salon_id,
                type(exc).__name__,
                exc,
            )
