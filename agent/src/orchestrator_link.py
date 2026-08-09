"""The agent's end of the text-only boundary.

`orchestrator/src/serving.py` is the other end. This is what an agent uses to take part in a
Salon it does not hold: it reports what its human said, and asks what it owes them.

**The agent is the only thing here that touches audio, and this module touches none of it.**
What crosses is text — a sentence out, an ordered list of lines back — and the interpreter
that turns those lines into speech sits beside the microphone, in this process, which is the
whole reason the boundary was drawn where it was.

Two calls carry the conversation, and only two:

    report(...)   what this human just said, once it is final
    script()      what to say to them, in their language, in order

There is no third call confirming what was spoken. The orchestrator advances the reading
position when it hands the script over, because in this topology a room holds one human and
their agent — an agent that dies takes the room with it, and there is nobody left to have
missed anything.

**Nothing here raises into a conversation.** A Salon whose orchestrator has gone quiet is a
Salon where translation stops; it is not a Salon that ends. Every method answers with an
empty result and logs the reason, and the caller goes on holding a room with a human in it.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import aiohttp

logger = logging.getLogger("agent.orchestrator")

# Short. Every one of these sits between a person speaking and somebody else hearing it, so a
# slow answer is worse than no answer — the conversation has moved on by the time it arrives.
TIMEOUT_SECONDS = 5.0


@dataclass(frozen=True)
class Line:
    """One thing to say, as the orchestrator wrote it down.

    `text` is what was said and `source_language` the language it is in; `language` is the
    language to say it in. Kept apart deliberately: a realtime model translates and speaks in
    one movement, and handing it a string somebody else already translated throws away the
    thing that makes speech-to-speech worth paying for.

    `verbatim` is the case where those two agree — a turn already in the listener's language,
    or an announcement composed for them. It costs no translation at all, which is why the
    price of a Salon follows the number of languages in it rather than its length.
    """

    kind: str
    text: str
    language: str
    source_language: str = ""
    speaker_id: str = ""
    sequence: int | None = None

    @property
    def verbatim(self) -> bool:
        return bool(self.source_language) and self.source_language == self.language


def _line_from_json(payload: dict[str, Any], listener_language: str) -> Line | None:
    """One wire object into one `Line`, or `None` for a kind this agent does not know.

    Skipped rather than raised. A line this version cannot say is one line missing from one
    delivery; an exception here would stop the whole script, including everything after it
    that this agent understands perfectly well.
    """
    kind = payload.get("kind", "")
    language = payload.get("language") or listener_language

    if kind == "tour":
        tour = payload.get("tour") or {}
        return Line(
            kind=kind,
            text=tour.get("text", ""),
            language=language,
            source_language=tour.get("language", ""),
            speaker_id=tour.get("participantId", ""),
            sequence=tour.get("sequence"),
        )

    if kind == "annonce":
        # Composed in the listener's language already, so there is nothing left to translate.
        return Line(
            kind=kind,
            text=payload.get("text", ""),
            language=language,
            source_language=language,
        )

    if kind == "condensation":
        covered = payload.get("covers") or []
        # Joined here rather than in the orchestrator, which keeps the interval as the turns
        # it was made of — a caller that wanted to say them one at a time still can.
        return Line(
            kind=kind,
            text=" ".join(turn.get("text", "") for turn in covered).strip(),
            language=language,
            # Empty on purpose: an interval spoken in several languages has no single one,
            # so it can never be verbatim.
            source_language="",
        )

    logger.warning("skipping a line of unknown kind %r", kind)
    return None


class OrchestratorLink:
    """One participant's connection to the Salon they are in.

    Holds no session between calls. Each opens one and closes it, which is what
    `aiohttp.ClientSession` is for in a process whose lifetime is a conversation — and this
    is not a hot loop: it runs at the pace of people speaking.
    """

    def __init__(
        self,
        *,
        base_url: str,
        salon_id: str,
        participant_id: str,
        language: str,
        token: str | None = None,
    ) -> None:
        self._base = (base_url or "").rstrip("/")
        self._salon_id = salon_id
        self._participant_id = participant_id
        self._language = language
        # Sent when the address needs one, which today it does: the orchestrator answers
        # inside the VPC and this worker does not run there, so the calls go through the
        # API's relay — already public, already authenticated. The paths are identical on
        # both sides on purpose, so pointing this at the orchestrator directly, the day the
        # worker moves into the VPC, is one changed base URL and nothing else.
        self._headers = {"Authorization": f"Bearer {token}"} if token else {}

    @property
    def configured(self) -> bool:
        """Whether there is an orchestrator to talk to at all.

        Empty is inert rather than broken: an agent given no address runs the conversation it
        can — one room, one human — instead of failing to start.
        """
        return bool(self._base)

    def _url(self, suffix: str = "") -> str:
        return (
            f"{self._base}/salons/{self._salon_id}"
            f"/participants/{self._participant_id}{suffix}"
        )

    async def join(self, *, name: str | None = None, by_telephone: bool = False) -> bool:
        """Take a seat. The interpreter stays here; what the Salon needs is the language."""
        if not self.configured:
            return False
        body = {
            "participantId": self._participant_id,
            "language": self._language,
            "name": name,
            "byTelephone": by_telephone,
        }
        return await self._post(f"{self._base}/salons/{self._salon_id}/participants", body) is not None

    async def report(
        self, text: str, *, language: str | None = None, duration_seconds: float | None = None
    ) -> int:
        """What this human just said, for the journal. Returns how many messages it became.

        A long intervention is cut into several so that nobody waits for the end of it, and
        nothing is recorded at all from somebody whose microphone the host has cut or whose
        room has fallen too far behind — which is why zero is an ordinary answer and not a
        failure.
        """
        if not self.configured or not text.strip():
            return 0
        payload = await self._post(
            self._url("/utterances"),
            {
                "text": text,
                "language": language or self._language,
                "durationSeconds": duration_seconds,
            },
        )
        return int((payload or {}).get("recorded", 0))

    async def script(self) -> list[Line]:
        """What this human is owed, in their language, in order.

        The reading position moves when this answers, so a line handed over is a line this
        agent is responsible for saying. Empty is the ordinary case: most of the time nobody
        has said anything since the last ask.
        """
        if not self.configured:
            return []
        payload = await self._get(self._url("/script"))
        lines = (payload or {}).get("lines") or []
        return [
            line
            for line in (_line_from_json(raw, self._language) for raw in lines)
            if line is not None
        ]

    async def leave(self) -> None:
        """This human is gone. Their room closes and nothing else does — what they said stays
        in the journal, because leaving is not a reason for everybody else to lose half the
        conversation."""
        if not self.configured:
            return
        try:
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=TIMEOUT_SECONDS)
            ) as session:
                await session.delete(self._url(), headers=self._headers)
        except Exception:  # noqa: BLE001
            # Logged and dropped. A departure the orchestrator did not hear about costs an
            # idle seat until the Salon ends; raising here would happen during teardown,
            # where there is nothing left to handle it.
            logger.warning("could not report that %s left", self._participant_id)

    # ── The two verbs underneath ──────────────────────────────────────────────

    async def _post(self, url: str, body: dict) -> dict | None:
        return await self._request("POST", url, body)

    async def _get(self, url: str) -> dict | None:
        return await self._request("GET", url, None)

    async def _request(self, method: str, url: str, body: dict | None) -> dict | None:
        """One call, and never an exception out of this module.

        The class of the failure is logged as well as its message: a connect timeout writes
        itself as nothing at all, and whether it was DNS, a closed port or a slow answer is
        the entire question when something cannot be reached.
        """
        try:
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=TIMEOUT_SECONDS)
            ) as session:
                async with session.request(
                    method, url, json=body, headers=self._headers
                ) as response:
                    if response.status >= 400:
                        logger.warning(
                            "orchestrator answered %d to %s %s",
                            response.status,
                            method,
                            url,
                        )
                        return None
                    return await response.json()
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "orchestrator unreachable for %s %s: %s(%s)",
                method,
                url,
                type(exc).__name__,
                exc,
            )
            return None
