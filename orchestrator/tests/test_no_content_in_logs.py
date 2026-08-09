"""No conversation content ever reaches a log.

The encryption half of Story 6.12 was delivered by the Aurora cluster's KMS key, which
covers the storage, the snapshots and the backups together. This is the half that was not,
and it is the one that is easy to break by accident: a diagnostic line that echoes a message
body puts in clear, in CloudWatch, exactly what the database is encrypting.

Two guards, because either alone is weak. A static one that fails the build when a logging
call is handed something content-shaped — cheap, and it catches the mistake at the moment
it is written. And a live one that runs a whole multilingual Salon with every logger turned
up to DEBUG and asserts that not one word anybody said appears anywhere in the output.
"""
import logging
import re
from pathlib import Path

import pytest

from src.interprete import InterpreteFake, Participant
from src.journal import InMemoryJournalStore, SalonLog
from src.salon import HistoryAccess, InMemoryRoomProvisioner, Salon

SOURCE = Path(__file__).resolve().parents[1] / "src"
REPO = Path(__file__).resolve().parents[2]

MARIE = Participant(id="marie", language="fr", name="Marie")
HANS = Participant(id="hans", language="de", name="Hans")
RHYS = Participant(id="rhys", language="cy", name="Rhys")

# Deliberately distinctive: if any of these turns up in a log line, it came from the
# conversation and nowhere else.
SECRETS = (
    "zarfblat",
    "quimmerly",
    "vondracek",
)


async def translate(text, *, source, target):
    return f"{text} [{target}]"


# ── The live guard ────────────────────────────────────────────────────────────


async def test_nothing_anybody_said_reaches_a_log(caplog):
    """A whole Salon, three languages, introductions, a condensation and a microphone cut —
    with every logger at DEBUG. Not one word of it may appear in the output."""
    log = SalonLog(salon_id="salon-1", store=InMemoryJournalStore(), translate=translate)
    salon = Salon(
        log=log,
        rooms=InMemoryRoomProvisioner(),
        host_id=MARIE.id,
        condensation_threshold_seconds=0.5,
    )

    with caplog.at_level(logging.DEBUG):
        await salon.join(MARIE, InterpreteFake(participant=MARIE))
        await salon.join(HANS, InterpreteFake(participant=HANS))

        await salon.ingest(MARIE.id, f"Bonjour {SECRETS[0]}", language="fr", duration_seconds=30)
        await salon.ingest(HANS.id, f"Guten Tag {SECRETS[1]}", language="de", duration_seconds=30)
        await salon.deliver_all()

        # A late arrival given the history, which condenses the backlog.
        await salon.join(
            RHYS, InterpreteFake(participant=RHYS), history=HistoryAccess.GRANTED
        )
        await salon.deliver_all()

        await salon.mute(HANS.id, by=MARIE.id)
        await salon.ingest(MARIE.id, f"encore {SECRETS[2]}", language="fr")
        await salon.deliver_all()
        await salon.aclose()

    logged = "\n".join(record.getMessage() for record in caplog.records)
    for secret in SECRETS:
        assert secret not in logged


async def test_no_translation_reaches_a_log(caplog):
    """A translation is conversation content too. It is derived from what somebody said,
    which makes it exactly as private as the original."""
    log = SalonLog(salon_id="salon-1", store=InMemoryJournalStore(), translate=translate)
    salon = Salon(log=log, rooms=InMemoryRoomProvisioner())

    with caplog.at_level(logging.DEBUG):
        await salon.join(MARIE, InterpreteFake(participant=MARIE))
        (entry,) = await salon.ingest(MARIE.id, f"Bonjour {SECRETS[0]}", language="fr")
        await salon.log.render(entry, "de")

    logged = "\n".join(record.getMessage() for record in caplog.records)
    assert SECRETS[0] not in logged


async def test_a_pause_marker_does_not_reach_a_log_either(caplog):
    """Named explicitly by the acceptance criterion. A marker says how long somebody
    hesitated, which is a fact about them even though it is not a word."""
    log = SalonLog(salon_id="salon-1", store=InMemoryJournalStore(), translate=translate)
    salon = Salon(log=log, rooms=InMemoryRoomProvisioner())

    with caplog.at_level(logging.DEBUG):
        await salon.join(MARIE, InterpreteFake(participant=MARIE))
        await salon.ingest(MARIE.id, "Alors [pause=4000] voilà", language="fr")

    logged = "\n".join(record.getMessage() for record in caplog.records)
    assert "[pause=" not in logged


async def test_a_provider_failure_is_reported_without_what_was_being_said(caplog):
    """The most tempting place to leak one: something has gone wrong, and the message being
    rendered is right there. NFR3 needs the participant told, not the sentence recorded."""
    log = SalonLog(salon_id="salon-1", store=InMemoryJournalStore(), translate=translate)
    salon = Salon(log=log, rooms=InMemoryRoomProvisioner())

    with caplog.at_level(logging.DEBUG):
        await salon.join(MARIE, InterpreteFake(participant=MARIE))
        await salon.join(HANS, InterpreteFake(participant=HANS))
        await salon.ingest(MARIE.id, f"Bonjour {SECRETS[0]}", language="fr")
        salon.interpreter_of(HANS.id).fail_with = ConnectionError("model gone")
        await salon.deliver_all()

    logged = "\n".join(record.getMessage() for record in caplog.records)
    assert SECRETS[0] not in logged


# ── The static guard ──────────────────────────────────────────────────────────

_LOG_CALL = re.compile(r"logger\.(?:debug|info|warning|error|exception|critical)\((.*?)\)", re.S)

# Names that hold what somebody said, or something derived from it. A logging call that
# mentions one of these is either leaking content or about to.
_CONTENT = (
    ".text",
    "entry.text",
    "utterance.text",
    "tour.text",
    "annonce.text",
    "spoken_text",
    "words",
    "transcript",
    "heard",
    "cleaned",
)


def test_no_logging_call_is_handed_anything_content_shaped():
    """Cheap, and it catches the mistake in the diff rather than in CloudWatch six months
    later. What a diagnostic may carry is identifiers and lengths — never the text."""
    offenders = []

    for path in SOURCE.rglob("*.py"):
        for call in _LOG_CALL.findall(path.read_text(encoding="utf-8")):
            for name in _CONTENT:
                if name in call:
                    offenders.append((path.name, name, " ".join(call.split())[:60]))

    assert offenders == []


def test_every_logger_in_the_service_is_the_one_that_is_configured():
    """One logger, one place its handlers are set. A module reaching for `logging.info`
    directly writes to the root logger, which nothing here has configured — and which in a
    container means an unformatted line straight to stdout."""
    stray = [
        path.name
        for path in SOURCE.rglob("*.py")
        if re.search(r"^\s*logging\.(?:debug|info|warning|error)\(", path.read_text(encoding="utf-8"), re.M)
    ]

    assert stray == []


# ── The half that was already delivered ───────────────────────────────────────


def test_the_database_the_journal_lives_in_is_encrypted():
    """The journal, the cursors and the translations sit in the Aurora cluster, so its key
    is what encrypts them — along with every snapshot and backup taken of it, which is the
    part a column-level scheme would have missed."""
    stack = (REPO / "infra" / "lib" / "salon-api-stack.ts").read_text(encoding="utf-8")

    assert "storageEncrypted: true" in stack


# ── The right way to say a message went wrong ─────────────────────────────────


def test_a_message_can_be_described_without_being_quoted():
    """The wrong way is one f-string away, so the right one is worth keeping close at hand:
    identifiers and lengths, and not a word of what was said."""
    from datetime import datetime, timezone

    from src.journal import JournalEntry
    from src.logging_config import about

    entry = JournalEntry(
        sequence=7,
        participant_id="marie",
        text=f"Bonjour {SECRETS[0]} [pause=4000]",
        language="fr",
        arrived_at=datetime(2026, 8, 8, tzinfo=timezone.utc),
        duration_seconds=5.0,
        part=2,
        parts=3,
    )

    described = about(entry)

    assert SECRETS[0] not in described
    assert "[pause=" not in described
    assert "seq=7" in described and "participant=marie" in described
    assert "chars=" in described and "2/3" in described


def test_the_length_reported_is_of_the_speech_alone():
    """A marker is not something anybody said, so counting it would misreport how much was."""
    from datetime import datetime, timezone

    from src.journal import JournalEntry
    from src.logging_config import about

    def described(text):
        return about(
            JournalEntry(
                sequence=1,
                participant_id="x",
                text=text,
                language="fr",
                arrived_at=datetime(2026, 8, 8, tzinfo=timezone.utc),
                duration_seconds=1.0,
            )
        )

    assert "chars=7" in described("Bonjour")
    assert "chars=7" in described("Bonjour[pause=4000]")
    assert "pause=4.0s" in described("Bonjour[pause=4000]")
