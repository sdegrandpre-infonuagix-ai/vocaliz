"""A participation belongs to a Salon, not to a room.

`salon_events` was keyed on `(participant_identity, salon_name)`, where salon_name is the
LiveKit room. That was the same thing while a Salon was one room. Under the new topology a
Salon is one room per human-interpreter pair, so the two come apart — and every place that
counted rooms started counting three conversations where there was one.

The first test below is the one that had no equivalent, and its absence is why
record_first_language spent its whole life returning False: it looked the row up with a
four-value tuple against a two-column key, SQLAlchemy raised, and a blanket `except`
turned the failure into a quiet "nothing written".
"""
import pytest

from src.models.salon import Salon
from src.models.salon_event import SalonEvent
from src.models.user import User
from src.services import salon_event_service


@pytest.fixture
def salon(db):
    host = User(email="host@example.com")
    db.add(host)
    db.flush()
    row = Salon(
        host_user_id=host.id,
        livekit_room_name="room-host",
        source_type="none",
        status="active",
    )
    db.add(row)
    db.commit()
    return row


def _enter(db, salon, identity, room):
    salon_event_service.record_entry(
        db,
        participant_identity=identity,
        email=f"{identity}@example.com",
        user_type="guest",
        salon_name=room,
        salon_id=salon.id,
    )


# ── The defect this rekey uncovered ──────────────────────────────────────────────────

def test_the_first_language_is_actually_written(db, salon):
    """It never was. The lookup passed (email, phone, user_type, salon_name) to a key of
    (participant_identity, salon_name) — four values for two columns."""
    _enter(db, salon, "alice", "room-alice")

    written = salon_event_service.record_first_language(
        db,
        salon_name="room-alice",
        salon_id=salon.id,
        participant_identity="alice",
        language="fr",
    )

    assert written is True
    row = db.query(SalonEvent).filter(SalonEvent.participant_identity == "alice").one()
    assert row.first_spoken_language == "fr"


def test_the_first_language_is_written_once(db, salon):
    """The column says "first spoken". A second value would quietly make that false."""
    _enter(db, salon, "alice", "room-alice")
    salon_event_service.record_first_language(
        db, salon_name="room-alice", salon_id=salon.id, participant_identity="alice", language="fr"
    )

    again = salon_event_service.record_first_language(
        db, salon_name="room-alice", salon_id=salon.id, participant_identity="alice", language="en"
    )

    assert again is False
    row = db.query(SalonEvent).filter(SalonEvent.participant_identity == "alice").one()
    assert row.first_spoken_language == "fr"


def test_a_language_for_somebody_who_never_entered_is_refused(db, salon):
    assert (
        salon_event_service.record_first_language(
            db,
            salon_name="room-ghost",
            salon_id=salon.id,
            participant_identity="ghost",
            language="fr",
        )
        is False
    )


# ── What the rekey is for ────────────────────────────────────────────────────────────

def test_reconnecting_into_a_different_room_is_the_same_participation(db, salon):
    """The case the old key could not express. A reconnection lands in a fresh LiveKit
    room, so keyed on the room name it read as a second person arriving."""
    _enter(db, salon, "alice", "room-alice")
    _enter(db, salon, "alice", "room-alice-retry")

    rows = db.query(SalonEvent).filter(SalonEvent.participant_identity == "alice").all()
    assert len(rows) == 1
    # The room they arrived in, not the one they came back through.
    assert rows[0].salon_name == "room-alice"
    assert rows[0].salon_id == salon.id


def test_three_participants_of_one_salon_share_one_salon_id(db, salon):
    """Three rooms, one conversation. Counting rooms would report three Salons."""
    for name, room in [("alice", "room-alice"), ("bob", "room-bob"), ("cleo", "room-cleo")]:
        _enter(db, salon, name, room)

    rows = db.query(SalonEvent).all()
    assert len(rows) == 3
    assert {r.salon_id for r in rows} == {salon.id}
    assert len({r.salon_name for r in rows}) == 3


def test_closing_a_salon_closes_every_room_in_it(db, salon):
    """Keyed on the room, this closed one participation out of three and left the other
    two open for ever."""
    for name, room in [("alice", "room-alice"), ("bob", "room-bob"), ("cleo", "room-cleo")]:
        _enter(db, salon, name, room)

    closed = salon_event_service.record_salon_exit(
        db, "room-alice", salon_id=salon.id, enjoyed=True
    )

    assert closed == 3
    assert all(r.exited_at is not None for r in db.query(SalonEvent).all())


def test_deleting_a_salon_takes_its_participations(db, salon):
    """ON DELETE CASCADE, so orphaned rows stop accumulating. Account deletion has to mean
    this too."""
    _enter(db, salon, "alice", "room-alice")

    db.delete(salon)
    db.commit()

    assert db.query(SalonEvent).count() == 0
