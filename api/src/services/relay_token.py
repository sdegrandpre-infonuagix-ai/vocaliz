"""A credential scoped to one participant's one Salon, for talking to the orchestrator relay.

`jwt_service.issue_token` proves *who a Vocaliz account is*. That is the wrong shape for this:
a guest's agent has no account to be, and even where one exists — the host's — a token that
proves an identity says nothing about which Salon it may act in. The first version of the
relay accepted any signed-in user's token for any Salon, which was correct only because
nothing yet minted a second kind of token to tell them apart.

This mints the second kind. It proves nothing about who somebody is and everything about what
they may do: speak as this participant, in this Salon, and nothing else. An agent holding one
cannot read another Salon's journal even if it tried, because there is no Salon that matches.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt

from src.config import settings

PURPOSE = "orchestrator-relay"

# A Salon runs for as long as its balance lasts, which this repository already bounds a
# session to nowhere in particular — Mode C at a generous balance could run for hours. Twelve
# is comfortably past what a paid conversation reaches in practice, and short enough that a
# token copied out of a log is not useful for long.
EXPIRY_HOURS = 12


def issue(*, salon_id: str, participant_id: str) -> str:
    """A token good for exactly one participant's one Salon."""
    payload = {
        "purpose": PURPOSE,
        "salonId": salon_id,
        "participantId": participant_id,
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(hours=EXPIRY_HOURS),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def scope_of(token: str) -> tuple[str, str] | None:
    """The `(salon_id, participant_id)` a token is good for, or `None`.

    `None` covers every way a token fails to apply here: it will not decode, it decodes but
    was signed for something else entirely, or it decodes and was never one of these to begin
    with — a Vocaliz sign-in token, say, which shares the same secret and algorithm and would
    otherwise decode just fine. `purpose` is what tells the two apart.
    """
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError:
        return None
    if payload.get("purpose") != PURPOSE:
        return None
    salon_id = payload.get("salonId")
    participant_id = payload.get("participantId")
    if not salon_id or not participant_id:
        return None
    return salon_id, participant_id
