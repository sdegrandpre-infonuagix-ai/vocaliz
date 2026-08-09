"""Getting your data, and getting it erased (Story 10.8 / FR66).

Two rights that look symmetrical and are not. An export hands somebody a copy of what is
already theirs. An erasure changes a record other people are also in, so it needs a shape the
export does not.

**A journal is a joint record.** Erasing "the conversation" would erase what other participants
said, which is not the requester's to remove. Only their own words go, and their presence is
**pseudonymised rather than deleted**: the others' exchanges must stay intelligible, and a
conversation with a hole where a speaker was is one nobody can follow.

**The accounting is kept and pseudonymised**, for the opposite reason. Those rows carry no
conversation content and answer to obligations that outlive anybody's preference — and an
append-only stream that honoured a deletion would stop being the thing every figure is folded
out of. What goes is the name, not the row.

**The burned registry keeps a one-way hash.** It has to go on refusing a second welcome credit
for an identifier that already had one — erasure is not a route to being paid twice — and it
can do that without holding an address in clear.

**An unverified erasure is a weapon**, so identity is proved by one of Story 10.7's routes
first. And money is settled first too: erasing an account must never be how the money in it
disappears.
"""
from __future__ import annotations

import hashlib
import hmac
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from src.config import settings
from src.credit import balance
from src.ledger import EventType, Pool, as_utc
from src.models.burned_identifier import BurnedIdentifier
from src.models.erasure import Erasure
from src.models.ledger_event import LedgerEvent
from src.models.participant_identifier import ParticipantIdentifier
from src.models.user import User
from src.models.utterance import Utterance

# What a requester is told the work will be finished by. Written onto the record rather than
# promised in a policy: a bounded delay nobody can show was met is not bounded.
ERASURE_DEADLINE = timedelta(days=30)

_PSEUDONYM_PREFIX = "erased-"
_BURNED_PREFIX = "sha256:"


class ErasureRefused(ValueError):
    """An erasure that cannot run yet, with the reason a person can act on."""


def _key() -> bytes:
    """The secret the pseudonyms are keyed with.

    The JWT secret, because it already has to exist and is already fatal to leak. A second
    secret would be a second thing to rotate and a second thing to forget.
    """
    return settings.jwt_secret.encode("utf-8")


def pseudonym_for(subject_id: uuid.UUID) -> str:
    """A stable handle for somebody who is no longer named.

    Keyed rather than plain, so holding the table is not holding the account ids: a plain
    digest of a UUID is reversible by anybody willing to hash the ones they already have.

    Stable, because two turns by one erased person must still read as one person. Losing that
    would keep the conversation legible in the letter and destroy it in fact.
    """
    digest = hmac.new(_key(), str(subject_id).encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{_PSEUDONYM_PREFIX}{digest[:16]}"


def burned_lookup_key(identifier: str) -> str:
    """How an erased identifier is written in the burned registry.

    A plain SHA-256 rather than a keyed one, deliberately: the registry is consulted by
    hashing whatever somebody just typed, which only works if the same input gives the same
    output with no secret in hand. What is being protected here is the address at rest, not
    the fact that some address was once burned.
    """
    digest = hashlib.sha256(identifier.encode("utf-8")).hexdigest()
    return f"{_BURNED_PREFIX}{digest}"


@dataclass(frozen=True)
class ErasureRecord:
    """What was done, as it was written down."""

    pseudonym: str
    scope: str
    requested_at: datetime
    due_by: datetime


def export_data(db: Session, person: User) -> dict:
    """Everything Vocaliz holds about this person, as plain JSON-serialisable data.

    Their own words and nobody else's. Handing somebody the other half of a conversation
    would be answering one person's right with another person's words.
    """
    held = balance(db, person.id)
    events = db.query(LedgerEvent).filter(LedgerEvent.subject_id == person.id).all()
    words = db.query(Utterance).filter(Utterance.speaker_identity == str(person.id)).all()

    return {
        "account": {
            "id": str(person.id),
            "email": person.email or "",
            "phone": person.phone_number or "",
            "username": person.username or "",
            "createdAt": as_utc(person.created_at).isoformat() if person.created_at else None,
        },
        "balances": {"giftedCents": held.gifted_cents, "paidCents": held.paid_cents},
        "recharges": [
            {
                "amountCents": row.amount_cents,
                "occurredAt": as_utc(row.occurred_at).isoformat(),
            }
            for row in events
            if row.type == EventType.RECHARGED.value and row.pool == Pool.PAID.value
        ],
        "words": [
            {
                "salonId": str(row.salon_id),
                "text": row.text,
                "language": row.language or "",
                "spokenAt": as_utc(row.spoken_at).isoformat(),
            }
            for row in sorted(words, key=lambda row: row.sequence)
        ],
    }


def refund_owed_cents(db: Session, subject_id: uuid.UUID) -> int:
    """What is still owed to this person, and would vanish with their account.

    The paid part only. A gifted credit was never their money, so there is nothing of theirs
    to give back.
    """
    db.flush()
    return max(0, balance(db, subject_id).paid_cents)


def erase(
    db: Session,
    person: User,
    *,
    verified: bool,
    waive_refund: bool = False,
    now: datetime,
) -> ErasureRecord:
    """Carry out an erasure, and write down that it happened.

    Refuses unverified requests, because somebody able to ask on another person's behalf can
    destroy their account. Refuses while money is owed, unless the holder gives it up
    knowingly — refusing forever would trap an account nobody can close over an amount its
    holder does not want.
    """
    if not verified:
        raise ErasureRefused(
            "This request has not been verified. Prove the account first — by code, by "
            "password, or by card — because an erasure nobody verified is a way to destroy "
            "somebody else's account."
        )

    owed = refund_owed_cents(db, person.id)
    if owed > 0 and not waive_refund:
        raise ErasureRefused(
            f"There is still {owed / 100:.2f} on this account. Take the refund first, or say "
            "explicitly that you are giving it up — erasing an account must never be how the "
            "money in it disappears."
        )

    handle = pseudonym_for(person.id)
    touched: list[str] = []

    # The journal: their words go, their turn stays, and the speaker becomes a pseudonym.
    spoken = db.query(Utterance).filter(Utterance.speaker_identity == str(person.id)).all()
    for row in spoken:
        row.text = ""
        row.speaker_identity = handle
    if spoken:
        touched.append(f"utterances: {len(spoken)} pseudonymised, text removed")

    # The accounting is left exactly as it is, and that is the pseudonymisation rather than a
    # step skipped. Story 8.1 made the stream append-only in the ORM as well as in Postgres,
    # so rewriting a row is refused — correctly: a stream somebody can rewrite says what was
    # last decided rather than what happened, and every figure in the product is folded out
    # of it.
    #
    # It does not need rewriting. `subject_id` is an opaque UUID with no foreign key and no
    # name, address or conversation content beside it. What made it resolve to a person was
    # the `users` row and the identifier registry, and both are removed below — after which
    # the stream holds sums of money against a subject nobody can resolve, which is what
    # pseudonymous means.
    events = db.query(LedgerEvent).filter(LedgerEvent.subject_id == person.id).all()
    if events:
        touched.append(
            f"ledger_events: {len(events)} kept unchanged and append-only; already "
            "pseudonymous, and unlinked by the removals below"
        )

    # The burned registry: hashed in place, so it goes on refusing a second gift without
    # holding the address. Nothing is invented for somebody who never had a credit.
    identifiers = [value for value in (person.email, person.phone_number) if value]
    burned = (
        db.query(BurnedIdentifier)
        .filter(BurnedIdentifier.identifier.in_(identifiers))
        .all()
    )
    hashed = [(burned_lookup_key(row.identifier), row.burned_at) for row in burned]
    for row in burned:
        db.delete(row)
    db.flush()
    for key, burned_at in hashed:
        db.add(BurnedIdentifier(identifier=key, burned_at=burned_at, granted_to=None))
    if hashed:
        touched.append(f"burned_identifiers: {len(hashed)} hashed, eligibility unchanged")

    db.query(ParticipantIdentifier).filter(
        ParticipantIdentifier.user_id == person.id
    ).delete(synchronize_session=False)
    touched.append("participant_identifiers: removed")

    # The account row is **emptied, not dropped**, and that is a correction found by testing
    # rather than a preference. `salons.host_user_id` cascades, so deleting a host would take
    # their Salons with it — and every other participant's words inside them. Erasing one
    # person's data by destroying three people's conversation is precisely what a joint record
    # forbids.
    #
    # What is left holds nothing personal: no address, no number, no handle, no password, no
    # Stripe identifiers. The CHECK from Story 10.1 still demands one identifier, so it gets
    # the pseudonym — which names nobody and cannot receive anything. The account is
    # unreachable by every route: no identifier resolves to it and no credential opens it.
    person.email = f"{handle}@erased.invalid"
    person.phone_number = None
    person.username = None
    person.password_hash = None
    person.otp_code = None
    person.otp_expires_at = None
    person.stripe_customer_id = None
    person.stripe_payment_method_id = None
    person.detected_language = None
    person.interface_language = None
    person.caption_language = None
    person.location_consent = None
    person.location_consent_at = None
    touched.append("users: emptied and pseudonymised, row kept so joint records survive")

    scope = "; ".join(touched)
    db.add(
        Erasure(
            subject_pseudonym=handle,
            requested_at=now,
            due_by=now + ERASURE_DEADLINE,
            completed_at=now,
            scope=scope,
        )
    )
    db.flush()
    return ErasureRecord(
        pseudonym=handle, scope=scope, requested_at=now, due_by=now + ERASURE_DEADLINE
    )
