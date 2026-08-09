"""Logging for a service that must never print what people said.

Story 6.12 states it as an acceptance criterion, and it is the easiest one in the whole
epic to violate by accident: a diagnostic line that echoes a message body puts in clear,
in CloudWatch, the very content the database encrypts at rest. So the rule for every line
written from this service is identifiers and lengths, never text.

The formatter itself cannot enforce that — it is a rule about what is passed in. What this
module does is make the shape of a line uniform enough that a line carrying a payload
stands out when read.
"""
from __future__ import annotations

import logging
import sys

LOGGER_NAME = "orchestrator"

# Container logs are collected by the awslogs driver from stdout, one line per record.
_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"


def configure_logging(level: str = "INFO") -> logging.Logger:
    """Attach a single stdout handler to the orchestrator logger and return it.

    Idempotent: calling it twice — which happens when an application is created more than
    once in the same process, as the tests do — must not double every line.
    """
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(level.upper())

    if not any(getattr(handler, "_orchestrator", False) for handler in logger.handlers):
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter(_FORMAT))
        handler._orchestrator = True  # type: ignore[attr-defined]
        logger.addHandler(handler)

    return logger


def about(entry) -> str:
    """A journal message, described without quoting it.

    What Story 6.12 allows a diagnostic to carry: identifiers and lengths, never text. There
    is a right way to say "this message went wrong" and this is it — the wrong way is one
    f-string away, which is why it is worth having the right one close at hand.

    Lengths are of the speech alone; a pause marker is metadata and its duration is reported
    separately, because "how long somebody hesitated" is a fact about them too.
    """
    from src.journal.cleaning import pause_seconds, spoken_length

    return (
        f"seq={entry.sequence} participant={entry.participant_id} "
        f"language={entry.language} chars={spoken_length(entry.text)} "
        f"pause={pause_seconds(entry.text):.1f}s part={entry.part}/{entry.parts}"
    )
