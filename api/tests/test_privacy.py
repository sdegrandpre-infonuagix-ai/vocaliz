"""Getting your data, and getting it erased (Story 10.8 / FR66).

Two rights that look symmetrical and are not. An export hands somebody a copy of what is
already theirs; an erasure changes a record that other people are also in. So the second one
has a shape the first does not need.

**A journal is a joint record.** Erasing "the conversation" would erase what other participants
said, which is not the requester's to remove. Only their own words go, and their presence is
**pseudonymised rather than deleted**: the others' exchanges have to stay intelligible, and a
conversation with a hole where a speaker was is a conversation nobody can follow.

**The accounting is kept and pseudonymised too**, for the opposite reason: those rows carry no
conversation content at all, and they answer to obligations that outlive anybody's preference.
An event stream whose whole point is that it is append-only cannot honour a deletion without
ceasing to be what it is.

**The burned registry keeps a one-way hash.** It has to go on refusing a second welcome credit
for an identifier that already had one — erasure is not a way to be paid twice — and it can do
that without holding the address in clear.

And an unverified erasure is a weapon. Somebody who can ask on another person's behalf can
destroy their account, so identity is proved by one of Story 10.7's routes before anything runs.
"""
import uuid
from datetime import datetime, timezone

import pytest

from src.credit import WELCOME_CREDIT_CENTS, balance, grant_welcome_credit
from src.ledger import EventType, Pool, append
from src.models.burned_identifier import BurnedIdentifier
from src.models.erasure import Erasure
from src.models.ledger_event import LedgerEvent
from src.models.salon import Salon
from src.models.user import User
from src.models.utterance import Utterance
from src.privacy import (
    ERASURE_DEADLINE,
    ErasureRefused,
    burned_lookup_key,
    erase,
    export_data,
    pseudonym_for,
    refund_owed_cents,
)
from src.signup import find_by_identifier, register

NOW = datetime(2026, 8, 1, tzinfo=timezone.utc)


@pytest.fixture
def person(db):
    row = register(db, email="marie@example.com", phone="+15145550123")
    db.commit()
    return row


@pytest.fixture
def salon(db, person):
    row = Salon(
        host_user_id=person.id,
        livekit_room_name="salon-privacy",
        source_type="url",
        source_content="c",
        status="ended",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _said(db, salon, who, text, *, sequence):
    row = Utterance(
        salon_id=salon.id,
        speaker_identity=who,
        speaker_role="host",
        text=text,
        language="fr",
        sequence=sequence,
        spoken_at=NOW,
    )
    db.add(row)
    db.flush()
    return row


# ── What an export contains ───────────────────────────────────────────────────


def test_the_export_carries_the_account(db, person):
    data = export_data(db, person)

    assert data["account"]["email"] == "marie@example.com"
    assert data["account"]["phone"] == "+15145550123"


def test_it_carries_both_balances(db, person):
    grant_welcome_credit(db, subject_id=person.id, identifiers=["marie@example.com"], now=NOW)
    append(db, type=EventType.RECHARGED, subject_id=person.id, amount_cents=2500,
           pool=Pool.PAID, occurred_at=NOW)
    db.flush()

    data = export_data(db, person)

    assert data["balances"]["giftedCents"] == WELCOME_CREDIT_CENTS
    assert data["balances"]["paidCents"] == 2500


def test_it_carries_the_recharges(db, person):
    append(db, type=EventType.RECHARGED, subject_id=person.id, amount_cents=2500,
           pool=Pool.PAID, occurred_at=NOW)
    db.flush()

    recharges = export_data(db, person)["recharges"]

    assert len(recharges) == 1
    assert recharges[0]["amountCents"] == 2500


def test_it_carries_their_own_words(db, person, salon):
    _said(db, salon, str(person.id), "Bonjour à tous.", sequence=1)

    words = export_data(db, person)["words"]

    assert [line["text"] for line in words] == ["Bonjour à tous."]


def test_it_carries_nobody_else_s(db, person, salon):
    """An export is a copy of what is already theirs. Handing somebody the other half of a
    conversation would be answering one person's right with another person's words."""
    _said(db, salon, str(person.id), "Bonjour à tous.", sequence=1)
    _said(db, salon, "someone-else", "Guten Tag.", sequence=2)

    words = export_data(db, person)["words"]

    assert [line["text"] for line in words] == ["Bonjour à tous."]


def test_it_is_json_serialisable(db, person, salon):
    """Readable and exportable means a file somebody can open, not an object graph."""
    import json

    _said(db, salon, str(person.id), "Bonjour à tous.", sequence=1)

    assert json.loads(json.dumps(export_data(db, person)))["account"]["email"]


def test_an_export_changes_nothing(db, person, salon):
    _said(db, salon, str(person.id), "Bonjour à tous.", sequence=1)
    export_data(db, person)

    assert db.query(Utterance).count() == 1
    assert db.get(User, person.id).email == "marie@example.com"


# ── Erasure needs a proved identity ───────────────────────────────────────────


def test_an_unverified_erasure_is_refused(db, person):
    """An erasure request is a weapon if anybody can make one on somebody else's behalf."""
    with pytest.raises(ErasureRefused) as raised:
        erase(db, person, verified=False, now=NOW)

    assert "verif" in str(raised.value).lower()


def test_nothing_is_touched_by_a_refused_request(db, person, salon):
    _said(db, salon, str(person.id), "Bonjour à tous.", sequence=1)

    with pytest.raises(ErasureRefused):
        erase(db, person, verified=False, now=NOW)

    assert db.query(Utterance).one().text == "Bonjour à tous."


# ── Money before erasure ──────────────────────────────────────────────────────


def test_a_positive_paid_balance_is_owed_back(db, person):
    """Erasing an account must never make the money in it disappear."""
    append(db, type=EventType.RECHARGED, subject_id=person.id, amount_cents=2500,
           pool=Pool.PAID, occurred_at=NOW)
    db.flush()

    assert refund_owed_cents(db, person.id) == 2500


def test_the_gift_is_not_owed_back(db, person):
    """It was never their money."""
    grant_welcome_credit(db, subject_id=person.id, identifiers=["marie@example.com"], now=NOW)
    db.flush()

    assert refund_owed_cents(db, person.id) == 0


def test_erasing_over_a_positive_balance_is_refused_until_it_is_settled(db, person):
    append(db, type=EventType.RECHARGED, subject_id=person.id, amount_cents=2500,
           pool=Pool.PAID, occurred_at=NOW)
    db.flush()

    with pytest.raises(ErasureRefused) as raised:
        erase(db, person, verified=True, now=NOW)

    assert "25.00" in str(raised.value)


def test_it_proceeds_once_the_balance_is_settled(db, person):
    append(db, type=EventType.RECHARGED, subject_id=person.id, amount_cents=2500,
           pool=Pool.PAID, occurred_at=NOW)
    append(db, type=EventType.REFUNDED, subject_id=person.id, amount_cents=-2500,
           pool=Pool.PAID, occurred_at=NOW)
    db.flush()

    assert erase(db, person, verified=True, now=NOW) is not None


def test_the_refund_may_be_waived_deliberately(db, person):
    """Somebody who knows and says so. Refusing forever would trap an account nobody can
    close over an amount its holder does not want."""
    append(db, type=EventType.RECHARGED, subject_id=person.id, amount_cents=2500,
           pool=Pool.PAID, occurred_at=NOW)
    db.flush()

    assert erase(db, person, verified=True, waive_refund=True, now=NOW) is not None


# ── The journal is a joint record ─────────────────────────────────────────────


def test_only_the_requester_s_words_go(db, person, salon):
    _said(db, salon, str(person.id), "Bonjour à tous.", sequence=1)
    _said(db, salon, "someone-else", "Guten Tag.", sequence=2)

    erase(db, person, verified=True, now=NOW)
    db.flush()

    remaining = {row.text for row in db.query(Utterance).all()}
    assert "Guten Tag." in remaining
    assert "Bonjour à tous." not in remaining


def test_their_presence_is_pseudonymised_rather_than_removed(db, person, salon):
    """A conversation with a hole where a speaker was is one nobody can follow. The turn
    stays, in its place, saying that somebody spoke and no longer who."""
    _said(db, salon, str(person.id), "Bonjour à tous.", sequence=1)
    _said(db, salon, "someone-else", "Guten Tag.", sequence=2)

    erase(db, person, verified=True, now=NOW)
    db.flush()

    theirs = db.query(Utterance).filter(Utterance.sequence == 1).one()
    assert theirs.speaker_identity == pseudonym_for(person.id)
    assert theirs.text == ""


def test_the_pseudonym_is_stable_across_a_conversation(db, person, salon):
    """Two turns by one erased person must still read as one person, or the exchange stops
    making sense in a different way."""
    _said(db, salon, str(person.id), "Bonjour.", sequence=1)
    _said(db, salon, str(person.id), "Et donc voilà.", sequence=3)

    erase(db, person, verified=True, now=NOW)
    db.flush()

    identities = {row.speaker_identity for row in db.query(Utterance).all()}
    assert len(identities) == 1


def test_the_pseudonym_does_not_name_them(db, person):
    handle = pseudonym_for(person.id)

    assert str(person.id) not in handle
    assert "marie" not in handle.lower()


def test_the_pseudonym_is_one_way(db, person):
    """Derived with a keyed hash, so holding the table is not holding the account ids."""
    assert pseudonym_for(person.id) == pseudonym_for(person.id)
    assert pseudonym_for(person.id) != pseudonym_for(uuid.uuid4())


# ── The accounting is kept ────────────────────────────────────────────────────


def test_the_ledger_keeps_every_row(db, person):
    """Append-only means append-only. A stream that honoured a deletion would stop being
    the thing every figure is folded out of."""
    grant_welcome_credit(db, subject_id=person.id, identifiers=["marie@example.com"], now=NOW)
    db.flush()
    before = db.query(LedgerEvent).count()

    erase(db, person, verified=True, now=NOW)
    db.flush()

    assert db.query(LedgerEvent).count() == before


def test_the_ledger_rows_no_longer_resolve_to_a_person(db, person):
    """Not rewritten — Story 8.1 made the stream append-only and refuses that, correctly.
    What made `subject_id` name somebody was the account row and the identifier registry, and
    both are gone. A sum of money against a subject nobody can resolve is pseudonymous."""
    grant_welcome_credit(db, subject_id=person.id, identifiers=["marie@example.com"], now=NOW)
    db.flush()
    subject = person.id

    erase(db, person, verified=True, now=NOW)
    db.flush()

    assert db.query(LedgerEvent).filter(LedgerEvent.subject_id == subject).count() > 0
    # The row that made the subject a person is emptied, and no identifier reaches it.
    assert db.get(User, subject).email.endswith("@erased.invalid")
    assert find_by_identifier(db, "marie@example.com") is None


def test_the_totals_still_add_up_afterwards(db, person):
    """The point of keeping them. A period close must produce the same figures before and
    after somebody exercised a right."""
    grant_welcome_credit(db, subject_id=person.id, identifiers=["marie@example.com"], now=NOW)
    db.flush()
    before = sum(row.amount_cents or 0 for row in db.query(LedgerEvent).all())

    erase(db, person, verified=True, now=NOW)
    db.flush()

    assert sum(row.amount_cents or 0 for row in db.query(LedgerEvent).all()) == before


# ── The burned registry goes on working ───────────────────────────────────────


def test_the_identifier_is_kept_as_a_one_way_hash(db, person):
    grant_welcome_credit(db, subject_id=person.id, identifiers=["marie@example.com"], now=NOW)
    db.flush()

    erase(db, person, verified=True, now=NOW)
    db.flush()

    kept = {row.identifier for row in db.query(BurnedIdentifier).all()}
    assert "marie@example.com" not in kept
    assert burned_lookup_key("marie@example.com") in kept


def test_erasure_never_restores_the_welcome_credit(db, person):
    """The acceptance criterion this whole hashing exists for: erasing and signing up again
    must not be a way to be paid twice."""
    grant_welcome_credit(db, subject_id=person.id, identifiers=["marie@example.com"], now=NOW)
    db.flush()
    erase(db, person, verified=True, now=NOW)
    db.flush()

    returning = register(db, email="marie@example.com")
    db.flush()
    again = grant_welcome_credit(
        db, subject_id=returning.id, identifiers=["marie@example.com"], now=NOW
    )

    assert again.granted_cents == 0
    assert again.refused_because


def test_an_identifier_never_burned_is_unaffected(db, person):
    """Nothing is invented. Erasing somebody who never had a credit must not make one look
    as though it had been given."""
    erase(db, person, verified=True, now=NOW)
    db.flush()

    assert db.query(BurnedIdentifier).count() == 0


# ── The account itself ────────────────────────────────────────────────────────


def test_the_identifiers_stop_pointing_at_anybody(db, person):
    erase(db, person, verified=True, now=NOW)
    db.flush()

    assert find_by_identifier(db, "marie@example.com") is None
    assert find_by_identifier(db, "+15145550123") is None


def test_the_account_holds_nothing_personal_afterwards(db, person):
    """Emptied rather than dropped, and that is not a softening. `salons.host_user_id`
    cascades, so deleting a host would take their Salons — and every other participant's
    words inside them. Erasing one person by destroying three people's conversation is what a
    joint record forbids."""
    erase(db, person, verified=True, now=NOW)
    db.flush()

    left = db.get(User, person.id)
    assert left is not None
    assert "marie" not in (left.email or "")
    assert left.phone_number is None
    assert left.username is None
    assert left.password_hash is None
    assert left.stripe_customer_id is None


def test_erasing_a_host_does_not_destroy_the_conversation(db, person, salon):
    """The reason the row is kept. Another participant's words must survive somebody else
    exercising their right."""
    _said(db, salon, "someone-else", "Guten Tag.", sequence=2)

    erase(db, person, verified=True, now=NOW)
    db.flush()

    assert db.query(Utterance).filter(Utterance.text == "Guten Tag.").count() == 1


# ── Proof that it happened ────────────────────────────────────────────────────


def test_an_erasure_is_written_down(db, person):
    record = erase(db, person, verified=True, now=NOW)
    db.flush()

    from src.ledger import as_utc

    row = db.query(Erasure).one()
    assert row.subject_pseudonym == pseudonym_for(person.id)
    assert as_utc(row.requested_at) == NOW
    assert record.scope


def test_the_record_names_the_scope(db, person, salon):
    _said(db, salon, str(person.id), "Bonjour à tous.", sequence=1)

    erase(db, person, verified=True, now=NOW)
    db.flush()

    scope = db.query(Erasure).one().scope
    assert "utterances" in scope and "users" in scope


def test_the_record_does_not_name_the_person(db, person):
    """Proof that a request was honoured, not a list of who asked. A log naming everybody who
    exercised the right would be a new personal record created by honouring the old one."""
    erase(db, person, verified=True, now=NOW)
    db.flush()

    row = db.query(Erasure).one()
    assert str(person.id) not in str(row.subject_pseudonym)
    assert "marie" not in row.scope.lower()


def test_a_deadline_is_carried_with_the_record(db, person):
    """Bounded, and the bound is written down rather than promised. The requester is told
    when it will be done, and the row says whether it was."""
    erase(db, person, verified=True, now=NOW)
    db.flush()

    from src.ledger import as_utc

    assert as_utc(db.query(Erasure).one().due_by) == NOW + ERASURE_DEADLINE


def test_the_completion_is_recorded(db, person):
    erase(db, person, verified=True, now=NOW)
    db.flush()

    from src.ledger import as_utc

    assert as_utc(db.query(Erasure).one().completed_at) == NOW


# ── The doors ─────────────────────────────────────────────────────────────────


@pytest.fixture
def signed_in(db, person):
    from src.services.jwt_service import issue_token

    return {"Authorization": f"Bearer {issue_token(str(person.id))}"}


def test_the_export_can_be_fetched(client, db, person, salon, signed_in):
    _said(db, salon, str(person.id), "Bonjour à tous.", sequence=1)
    db.commit()

    body = client.get("/me/data", headers=signed_in).json()

    assert body["account"]["email"] == "marie@example.com"
    assert [line["text"] for line in body["words"]] == ["Bonjour à tous."]


def test_a_stranger_gets_no_export(client, db, person):
    assert client.get("/me/data").status_code in (401, 403)


def test_erasure_runs_for_a_signed_in_person(client, db, person, signed_in):
    resp = client.post("/me/erasure", json={"waiveRefund": False}, headers=signed_in)

    assert resp.status_code == 200
    assert "users" in resp.json()["scope"]
    db.expire_all()
    assert db.get(User, person.id).email.endswith("@erased.invalid")


def test_a_positive_balance_stops_it_with_an_explanation(client, db, person, signed_in):
    append(db, type=EventType.RECHARGED, subject_id=person.id, amount_cents=2500,
           pool=Pool.PAID, occurred_at=NOW)
    db.commit()

    resp = client.post("/me/erasure", json={"waiveRefund": False}, headers=signed_in)

    assert resp.status_code == 409
    assert "25.00" in resp.json()["detail"]


def test_it_can_be_waived_knowingly(client, db, person, signed_in):
    append(db, type=EventType.RECHARGED, subject_id=person.id, amount_cents=2500,
           pool=Pool.PAID, occurred_at=NOW)
    db.commit()

    resp = client.post("/me/erasure", json={"waiveRefund": True}, headers=signed_in)

    assert resp.status_code == 200


def test_a_stranger_cannot_erase_anybody(client, db, person):
    """The criterion's whole point: an erasure request is a weapon if anybody can make one."""
    assert client.post("/me/erasure", json={"waiveRefund": True}).status_code in (401, 403)
