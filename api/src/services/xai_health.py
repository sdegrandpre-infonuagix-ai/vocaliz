"""Is xAI answering us? Probed, because there is no balance to read.

xAI publishes no credit endpoint — /v1/billing, /v1/credits and /v1/usage all answer 404, and
/v1/api-key returns the key's own metadata and nothing about money. A threshold on a balance
was the obvious design and it is not available, so this detects the condition instead of
predicting it.

That turns out to catch more than a spent balance. The symptom the agent shows is identical for
a depleted account, a key revoked by mistake, and a suspended team: it joins a room and never
speaks, with no error anywhere in Vocaliz. One probe covers all three.

The cost of knowing: a one-token completion a minute on the cheapest configured model. A
fraction of a cent an hour, against the alternative of a caller reaching silence and nobody
finding out until they complain.
"""
import logging
from datetime import datetime, timezone

import boto3
import httpx
from sqlalchemy.orm import Session as DbSession

from src.config import settings
from src.models.service_health import ServiceHealth

logger = logging.getLogger(__name__)

# Two things can fail independently, so two rows. Text is probed on a schedule; voice is
# reported by the agent when it actually connects, because xAI offers no cheap voice call to
# probe — /v1/audio/speech answers 403 for this team.
SERVICE = "xai"
VOICE_SERVICE = "xai_voice"

# Long enough that a slow answer is not called an outage, short enough to finish well inside a
# minute so probes cannot pile up on each other.
_TIMEOUT_SECONDS = 15.0


def probe() -> tuple[bool, str]:
    """Ask xAI for one token. Returns (healthy, what went wrong).

    A real completion, not /v1/api-key. That endpoint answers 200 with a spent balance — it
    validates the key and knows nothing about credit — so probing it would report health right
    through the outage this exists to catch.
    """
    if not settings.xai_api_key:
        return False, "No xAI API key is configured."
    try:
        response = httpx.post(
            "https://api.x.ai/v1/chat/completions",
            headers={"Authorization": f"Bearer {settings.xai_api_key}"},
            json={
                "model": settings.summary_model,
                "messages": [{"role": "user", "content": "ping"}],
                "max_tokens": 1,
            },
            timeout=_TIMEOUT_SECONDS,
        )
    except Exception as exc:  # noqa: BLE001
        # Unreachable is indistinguishable from refusing, from where the agent stands.
        return False, f"xAI could not be reached: {type(exc).__name__}"

    if response.status_code == 200:
        return True, ""
    # The body carries the reason — "insufficient credits", "invalid api key" — and quoting it
    # is the difference between an alert somebody can act on and one they have to investigate.
    return False, f"HTTP {response.status_code}: {response.text[:300]}"


def check(db: DbSession, recipient: str = "") -> dict:
    """Probe the text API and record the result. Invoked every minute by EventBridge."""
    healthy, detail = probe()
    return record(db, service=SERVICE, healthy=healthy, detail=detail, recipient=recipient)


def record(
    db: DbSession, *, service: str, healthy: bool, detail: str = "", recipient: str = ""
) -> dict:
    """Store one service's state and email the administrator when it has changed.

    On transition only. A check every minute that emailed on every failure would send more than
    a thousand messages during one bad night, and an inbox with a thousand identical alerts is
    an inbox where the next real one is missed.

    Recovery is announced too. Being told something broke and never told it was fixed leaves
    somebody checking by hand, which is the work this was meant to remove.

    Shared by the scheduled text probe and the agent's report on the voice connection, so both
    inherit the same alert-once behaviour rather than each inventing it.
    """
    to = recipient or settings.front_desk_email
    row = db.get(ServiceHealth, service)

    if row is None:
        # First ever result. Recorded without alerting when healthy: an email saying "xAI is
        # fine" to announce that monitoring has started is noise on the day it is deployed.
        db.add(ServiceHealth(service=service, healthy=healthy, detail=detail))
        db.commit()
        if healthy:
            return {"status": "ok", "healthy": True, "alerted": False}
        _alert(to, healthy=False, detail=detail, service=service)
        return {"status": "ok", "healthy": False, "alerted": True}

    if row.healthy == healthy:
        # Nothing changed. The row is deliberately not touched, so changed_at keeps meaning
        # "when this last became true" rather than "when we last looked".
        return {"status": "ok", "healthy": healthy, "alerted": False}

    row.healthy = healthy
    row.detail = detail
    row.changed_at = datetime.now(tz=timezone.utc)
    db.commit()

    _alert(to, healthy=healthy, detail=detail, service=service)
    return {"status": "ok", "healthy": healthy, "alerted": True}


def _alert(recipient: str, *, healthy: bool, detail: str, service: str = SERVICE) -> None:
    """Send the one email a transition earns. Never raises.

    A monitor that can crash is a monitor that stops monitoring, and it would fail silently —
    the same shape as the outage it watches for.
    """
    voice = service == VOICE_SERVICE
    what = "the xAI voice model" if voice else "xAI"

    if healthy:
        subject = f"Vocaliz: {what} is answering again"
        body = (
            f"{what} is responding normally again. Salons can be held.\n\n"
            "Nothing was lost that was not already lost while it was down."
        )
    else:
        subject = f"Vocaliz: {what} is NOT answering — agents will be silent"
        body = (
            f"A check on {what} failed. Until it succeeds, an agent joining a Salon will not "
            "speak: it connects, the room looks normal, and nobody is answered. There is no "
            "error visible anywhere in Vocaliz.\n\n"
            f"What xAI said:\n{detail}\n\n"
            "Most often this is credit. xAI publishes no balance endpoint, so this cannot say "
            "how much is left — check console.x.ai. A revoked or mistyped key produces the "
            "same silence.\n\n"
            "You will get one more email when it recovers."
        )
    if voice:
        # The voice result comes from a real agent that really tried to connect, not from a
        # probe standing in for one. Saying so changes what the reader should do: this is not a
        # warning about what might happen, it is a report that a Salon just failed.
        body += (
            "\n\nThis was reported by an agent joining an actual Salon, so somebody was "
            "already affected."
        )
    try:
        # SES directly, the same way the participant report sends. Plain text on purpose: this
        # is read on a phone at an awkward hour, and the only thing that matters is the first
        # line.
        boto3.client("ses", region_name=settings.aws_region).send_email(
            Source=settings.ses_from_address,
            Destination={"ToAddresses": [recipient]},
            Message={
                "Subject": {"Data": subject},
                "Body": {"Text": {"Data": body}},
            },
        )
        logger.info("xAI health alert sent to %s (healthy=%s)", recipient, healthy)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not send the xAI health alert: %s", exc)
