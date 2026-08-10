"""Mailed the moment a salon closes: who was in it, what they are worth, and what was said.

Read alongside `participant_report.py`, which answers a different question on a different
schedule — one row per person, aggregated across every salon they have ever been in, mailed
hourly regardless of whether anything closed. This is the opposite shape: one salon, every
account that took part in it, mailed the instant `finalize_salon` marks it ended. The two
never share a query — aggregating across salons and reporting on one are different enough
questions that forcing one function to answer both would leave neither reading cleanly.

Never raises. Called from `finalize_salon`, where a report that failed to send must cost
nothing more than the report — the salon is already closed by the time this runs, and an
exception here must not turn a closing salon into a request that failed.
"""
import logging
import uuid as _uuid
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import boto3
from sqlalchemy.orm import Session as DbSession

from src.config import settings
from src.credit import balance
from src.models.salon import Salon
from src.models.salon_event import SalonEvent
from src.models.user import User
from src.services import utterance_service

logger = logging.getLogger(__name__)

# Fixed rather than configurable: this is one person's own request for one person's own
# inbox, not a setting anybody else has a reason to point elsewhere.
RECIPIENT = "s.degrandpre@vocaliz.net"


def _account_for(db: DbSession, identity: str) -> User | None:
    """The registered account behind a participation, if the identity names one.

    A host's identity *is* their account UUID, and so is a registered guest's
    (`livekit_service.identity_for`) — never `guest-<invitation id>`, which is what an
    anonymous guest's identity looks like and what makes this return None for them. There
    is no account row to report a creation date or a balance from, and that is a fact
    about the participant, not a lookup failure.
    """
    try:
        account_id = _uuid.UUID(identity)
    except ValueError:
        return None
    return db.query(User).filter(User.id == account_id).first()


def _participant_rows(db: DbSession, salon: Salon) -> list[dict]:
    """One row per person who was actually in the room, host first.

    Read from `salon_events`, not from the invitation list: an invitation that was never
    opened never seated anyone, and this reports who was there, not who was asked.
    """
    events = (
        db.query(SalonEvent)
        .filter(SalonEvent.salon_id == salon.id)
        .order_by(SalonEvent.user_type.desc(), SalonEvent.entered_at)
        .all()
    )
    rows = []
    for event in events:
        account = _account_for(db, event.participant_identity)
        bal = balance(db, account.id) if account else None
        rows.append(
            {
                "identity": event.participant_identity,
                "email": event.email or (account.email if account else "") or "(anonymous)",
                "role": event.user_type,
                "createdAt": account.created_at if account else None,
                "giftedCents": bal.gifted_cents if bal else None,
                "paidCents": bal.paid_cents if bal else None,
                "totalCents": bal.total_cents if bal else None,
                "language": event.first_spoken_language,
            }
        )
    return rows


def _money(cents: int | None) -> str:
    return "n/a" if cents is None else f"${cents / 100:.2f}"


def _body_text(salon: Salon, rows: list[dict]) -> str:
    lines = [
        f"Salon {salon.id} ended at {salon.ended_at.isoformat() if salon.ended_at else '?'}.",
        f"{len(rows)} participant(s):",
        "",
    ]
    for row in rows:
        created = row["createdAt"].isoformat() if row["createdAt"] else "no account"
        lines.append(
            f"- {row['email']} ({row['role']}) — account created {created} — "
            f"gifted {_money(row['giftedCents'])}, paid {_money(row['paidCents'])}, "
            f"total {_money(row['totalCents'])}"
        )
    lines.append("")
    lines.append("Each participant's own transcript is attached, one file per person.")
    return "\n".join(lines) + "\n"


def _safe_filename(label: str) -> str:
    keep = "".join(c if c.isalnum() or c in "._-" else "_" for c in label)
    return keep or "participant"


def _transcript_attachment(db: DbSession, salon: Salon, row: dict) -> MIMEApplication:
    """One participant's own view of the conversation, rendered in the language they were
    first heard speaking — the closest thing on record to what their own room showed them.
    Falls back to the words exactly as spoken when no language was ever recorded."""
    turns = utterance_service.transcript(
        db, salon_id=salon.id, language=row["language"] or None
    )
    body = "\n".join(
        f"[{turn['spokenAt'] or ''}] {turn['speaker']}: {turn['text']}" for turn in turns
    ) or "(nothing was said)\n"
    part = MIMEApplication(body.encode("utf-8"), _subtype="plain")
    filename = f"{_safe_filename(row['email'] or row['identity'])}.txt"
    part.add_header("Content-Disposition", "attachment", filename=filename)
    return part


def send(db: DbSession, salon: Salon) -> dict:
    """Build the report and mail it. Never raises — see the module docstring."""
    try:
        rows = _participant_rows(db, salon)

        message = MIMEMultipart()
        message["Subject"] = f"Vocaliz — salon closed ({len(rows)} participant(s))"
        message["From"] = settings.ses_from_address
        message["To"] = RECIPIENT
        message.attach(MIMEText(_body_text(salon, rows), "plain", "utf-8"))
        for row in rows:
            message.attach(_transcript_attachment(db, salon, row))

        boto3.client("ses", region_name=settings.aws_region).send_raw_email(
            Source=settings.ses_from_address,
            Destinations=[RECIPIENT],
            RawMessage={"Data": message.as_bytes()},
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("Closure report for salon %s failed: %s", salon.id, exc, exc_info=True)
        return {"status": "send_failed"}
    logger.info("Closure report sent for salon %s (%d participants)", salon.id, len(rows))
    return {"status": "ok", "participants": len(rows)}
