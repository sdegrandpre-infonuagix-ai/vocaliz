"""Recording what was said, and handing it back in the language someone asked for."""
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

from src.models.utterance import Utterance
from src.services import livekit_service, translation_service

logger = logging.getLogger(__name__)

AGENT_IDENTITY = "agent"


def display_label(identity: str, role: str) -> str:
    """What a viewer sees next to a caption.

    A guest is shown as "Guest 3F2A", never as their address: the host typed that address
    to invite them, and the other participants have no business reading it. The label is
    derived from the invitation id, which is what the rest of the product already shows,
    so the name on a caption matches the name in the room.
    """
    if role == "agent":
        return "Vocaliz"
    if identity.startswith("guest-"):
        return livekit_service.guest_display_name(identity.removeprefix("guest-"))
    return identity


def record(
    db: DbSession,
    *,
    salon_id: uuid.UUID,
    speaker_identity: str,
    speaker_role: str,
    text: str,
    language: str | None = None,
    spoken_at: datetime | None = None,
) -> Utterance | None:
    """Store one final turn of speech.

    The sequence is read and written in the same transaction, and a collision is retried
    once: the agent is the only writer for a given salon, so a clash means two turns
    committed at the same instant rather than genuine contention.

    Returns None on failure. Losing a caption must never interrupt a conversation.
    """
    text = (text or "").strip()
    if not text:
        return None

    for attempt in (1, 2):
        try:
            highest = (
                db.query(func.max(Utterance.sequence))
                .filter(Utterance.salon_id == salon_id)
                .scalar()
            )
            utterance = Utterance(
                salon_id=salon_id,
                speaker_identity=speaker_identity,
                speaker_role=speaker_role,
                text=text,
                language=language,
                sequence=(highest or 0) + 1,
                spoken_at=spoken_at or datetime.now(tz=timezone.utc),
            )
            db.add(utterance)
            db.commit()
            db.refresh(utterance)
            return utterance
        except IntegrityError:
            db.rollback()
            if attempt == 2:
                logger.warning(
                    "Could not record an utterance for salon %s", salon_id, exc_info=True
                )
                return None
        except Exception:  # noqa: BLE001
            db.rollback()
            logger.warning(
                "Could not record an utterance for salon %s", salon_id, exc_info=True
            )
            return None
    return None


def transcript(
    db: DbSession, *, salon_id: uuid.UUID, language: str | None = None, after: int = 0
) -> list[dict]:
    """A salon's turns in order, translated when a language is asked for.

    `after` is a sequence number, not a timestamp: a client that has seen turn 12 asks for
    everything above 12 and cannot miss one to a clock skew. It exists for the viewer who
    joins late or reloads — live captions travel over the room's data channel, not here.
    """
    rows = (
        db.query(Utterance)
        .filter(Utterance.salon_id == salon_id, Utterance.sequence > after)
        .order_by(Utterance.sequence)
        .all()
    )

    result = []
    for row in rows:
        rendered = (
            translation_service.translated_text(db, row, language) if language else row.text
        )
        result.append(
            {
                "sequence": row.sequence,
                "speaker": display_label(row.speaker_identity, row.speaker_role),
                "role": row.speaker_role,
                "text": rendered,
                # The spoken words travel alongside the translation so a viewer can check
                # a rendering that reads oddly. A translation with no original is a claim.
                "originalText": row.text,
                "language": row.language,
                "spokenAt": row.spoken_at.isoformat() if row.spoken_at else None,
            }
        )
    return result
