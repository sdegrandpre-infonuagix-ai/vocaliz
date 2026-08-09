"""Telling an orchestrator which Salon it holds.

One call, made when a Salon is created — in the same breath as its LiveKit room, because the
room and the conversation are two halves of one act. The orchestrator answers, the address is
written onto the Salon row, and every agent that joins afterwards knows where to ask what it
owes its human.

**Text only, in both directions.** Nothing here carries audio and nothing here could: the
request names a Salon and a room, and the answer is an acknowledgement. That is the whole
surface between the two services on this side.

**Never fatal.** A Salon whose orchestrator could not be reached is a Salon that opens without
translation and says so by leaving `orchestrator_url` null — worse than a working one, and
enormously better than a host who cannot start a conversation at all because a second service
was restarting. The failure is logged with the identifiers and never with anything said.

**Inert until an orchestrator exists.** `orchestrator_base_url` is empty by default and this
returns `None` without making a request. The ECS service is not deployed yet; a default address
resolving to nothing would turn every salon creation into a five-second wait for a connection
refused, which is a worse way to express "not built yet" than doing nothing.
"""
import logging

import httpx

from src.config import settings

logger = logging.getLogger(__name__)

# Short on purpose. This sits in the path of a host waiting for a Salon to open, and the
# orchestrator is answering a request that writes nothing to a database — an instance that
# cannot say yes in this long is an instance that should not be given the Salon.
HOST_TIMEOUT_SECONDS = 5.0


async def host_salon(*, salon_id, room_name: str, host_id) -> str | None:
    """Ask an orchestrator to take responsibility for this Salon.

    Returns the address that accepted it, to be written onto the Salon row, or `None` when
    there is no orchestrator configured or none would take it.

    `PUT` rather than `POST`, and idempotent at the far end: a retried request is ordinary
    here, and building a second conversation over the first would silently drop everything
    already said.
    """
    base = (settings.orchestrator_base_url or "").rstrip("/")
    if not base:
        return None

    url = f"{base}/salons/{salon_id}"
    try:
        async with httpx.AsyncClient(timeout=HOST_TIMEOUT_SECONDS) as client:
            response = await client.put(
                url,
                json={"livekitRoomName": room_name, "hostId": str(host_id)},
            )
    except Exception as exc:  # noqa: BLE001
        # Deliberately everything, including a timeout and a DNS failure. A host must not be
        # stopped from opening a Salon because a second service is restarting.
        # The class as well as the message. `httpx.ConnectTimeout` stringifies to nothing at
        # all, so `%s` alone produced a warning that said a request had failed and gave no
        # hint whether it was DNS, a closed port or a slow answer — which is the entire
        # question when something cannot be reached.
        logger.warning(
            "orchestrator did not take salon %s at %s: %s(%s)",
            salon_id,
            base,
            type(exc).__name__,
            exc,
        )
        return None

    if response.status_code == 503:
        # Draining, and saying so properly. Distinguished from an error because it is not
        # one: this instance is finishing what it holds, and the right answer is another
        # instance rather than a retry against this one. There is one instance today, so
        # there is nowhere else to go and the Salon opens without translation.
        logger.warning("orchestrator at %s is draining, salon %s not hosted", base, salon_id)
        return None

    if response.status_code >= 400:
        logger.warning(
            "orchestrator at %s refused salon %s with %d", base, salon_id, response.status_code
        )
        return None

    return base
