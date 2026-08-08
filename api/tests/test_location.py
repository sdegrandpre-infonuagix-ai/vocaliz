"""Positions are stored as neighbourhood-scale Plus Codes, never as points."""
import pytest

from src.config import settings
from src.models.salon_event import SalonEvent
from src.models.salon import Salon
from src.models.user import User
from src.services import location_service, salon_event_service

# Place Ville-Marie, Montréal.
LAT, LON = 45.5019, -73.5674


@pytest.fixture
def salon(db):
    user = User(email="geo@example.com")
    db.add(user)
    db.commit()
    db.refresh(user)
    s = Salon(
        host_user_id=user.id,
        livekit_room_name="salon-geo",
        source_type="url",
        source_content="c",
        status="active",
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


# ─── Encoding ─────────────────────────────────────────────────────────────────

def test_a_position_becomes_a_plus_code():
    code = location_service.plus_code(LAT, LON)
    assert code
    assert "+" in code


def test_no_position_is_an_empty_string_not_none():
    """It shares a table with the identity columns, which use the same convention: absent
    is a value that compares, not a NULL that behaves differently in every query."""
    assert location_service.plus_code(None, None) == ""
    assert location_service.plus_code(LAT, None) == ""
    assert location_service.plus_code(None, LON) == ""


def test_the_cell_is_neighbourhood_scale_not_a_point():
    """Six digits is about five and a half kilometres. The point of the change is that a
    stored position cannot lead to a doorstep."""
    centre = location_service.approximate_centre(location_service.plus_code(LAT, LON))
    assert centre is not None
    # Within the cell, but deliberately not the exact coordinates that went in.
    assert abs(centre[0] - LAT) < 0.05
    assert (centre[0], centre[1]) != (LAT, LON)


def test_nearby_positions_share_a_cell():
    """Two people a few hundred metres apart must be indistinguishable at this scale."""
    a = location_service.plus_code(LAT, LON)
    b = location_service.plus_code(LAT + 0.002, LON + 0.002)  # ~250 m away
    assert a == b


def test_distant_positions_do_not():
    quebec = location_service.plus_code(46.8139, -71.2080)
    assert quebec != location_service.plus_code(LAT, LON)


def test_an_impossible_position_yields_nothing_rather_than_raising():
    """Losing a row's location costs a location. Raising would cost the participation."""
    assert location_service.plus_code(999.0, 999.0) == ""


def test_precision_follows_the_setting():
    """Compared by cell size, not by string length: Plus Codes shorter than eight digits
    are padded with zeros, so a coarser code is exactly as many characters long."""
    from openlocationcode import openlocationcode as olc

    def cell_km(code: str) -> float:
        area = olc.decode(code)
        return (area.latitudeHi - area.latitudeLo) * 111

    original = settings.location_code_length
    settings.location_code_length = 8
    try:
        fine = cell_km(location_service.plus_code(LAT, LON))
    finally:
        settings.location_code_length = original
    coarse = cell_km(location_service.plus_code(LAT, LON))
    assert fine < coarse
    # The default is the borough-scale rung, not the block-scale one.
    assert coarse > 1.0


def test_decoding_nothing_returns_nothing():
    assert location_service.approximate_centre("") is None
    assert location_service.approximate_centre("not-a-code") is None


# ─── What actually reaches the database ───────────────────────────────────────

def test_the_precise_coordinates_never_reach_the_row(db, salon):
    """The whole point: encoding happens at ingestion, so there is nothing precise at
    rest to round on the way out."""
    salon_event_service.record_entry(
        db,
        participant_identity="test-identity",
        email="geo@example.com",
        user_type="host",
        salon_name=salon.livekit_room_name,
        latitude=LAT,
        longitude=LON,
    )
    row = db.query(SalonEvent).one()
    assert row.plus_code == location_service.plus_code(LAT, LON)
    # The columns that used to hold a point are gone, not merely unused.
    assert not hasattr(row, "gps_latitude")
    assert not hasattr(row, "client_ip")


def test_declining_the_prompt_leaves_no_location(db, salon):
    """The common case, and not an error."""
    salon_event_service.record_entry(
        db,
        participant_identity="test-identity",
        email="geo@example.com", user_type="host", salon_name=salon.livekit_room_name
    )
    assert db.query(SalonEvent).one().plus_code == ""


def test_a_position_granted_on_re_entry_is_filled_in(db, salon):
    salon_event_service.record_entry(
        db,
        participant_identity="test-identity",
        email="geo@example.com", user_type="host", salon_name=salon.livekit_room_name
    )
    salon_event_service.record_entry(
        db,
        participant_identity="test-identity",
        email="geo@example.com",
        user_type="host",
        salon_name=salon.livekit_room_name,
        latitude=LAT,
        longitude=LON,
    )
    assert db.query(SalonEvent).one().plus_code == location_service.plus_code(LAT, LON)


def test_a_second_reading_does_not_replace_the_first(db, salon):
    """Someone who moves during a salon keeps the cell they arrived in — a participation
    has one location, and the last reading is no truer than the first."""
    salon_event_service.record_entry(
        db,
        participant_identity="test-identity",
        email="geo@example.com",
        user_type="host",
        salon_name=salon.livekit_room_name,
        latitude=LAT,
        longitude=LON,
    )
    first = db.query(SalonEvent).one().plus_code
    salon_event_service.record_entry(
        db,
        participant_identity="test-identity",
        email="geo@example.com",
        user_type="host",
        salon_name=salon.livekit_room_name,
        latitude=46.8139,
        longitude=-71.2080,
    )
    assert db.query(SalonEvent).one().plus_code == first


# ─── Purging participations nobody was heard in ───────────────────────────────

def _entry(db, salon, email, *, language=None, role="guest"):
    salon_event_service.record_entry(
        db,
        participant_identity="test-identity",
        email=email,
        user_type=role,
        salon_name=salon,
        first_spoken_language=language,
    )


def test_the_purge_is_a_dry_run_by_default(db, salon):
    """Destructive and irreversible, so the count comes before the deletion."""
    _entry(db, "salon-a", "silent@example.com")
    result = salon_event_service.purge_silent_participations(db)
    assert result["status"] == "dry_run"
    assert result["matched"] == 1
    assert result["deleted"] == 0
    assert db.query(SalonEvent).count() == 1, "nothing removed"


def test_the_dry_run_names_whose_history_is_at_stake(db, salon):
    """The point of a dry run is recognising the contacts, not just counting rows."""
    _entry(db, "salon-a", "silent@example.com")
    assert salon_event_service.purge_silent_participations(db)["contacts"] == [
        "silent@example.com"
    ]


def test_the_purge_removes_only_the_silent(db, salon):
    _entry(db, "salon-a", "spoke@example.com", language="fr")
    _entry(db, "salon-b", "silent@example.com")

    result = salon_event_service.purge_silent_participations(db, confirm=True)
    assert result["deleted"] == 1
    remaining = db.query(SalonEvent).all()
    assert [row.email for row in remaining] == ["spoke@example.com"]


def test_the_purge_reaches_host_rows_too(db, salon):
    """The scope nobody expects: the admin listing aggregates languages across a person's salons,
    so somebody shown as speaking French may still have silent rows."""
    _entry(db, "salon-a", "host@example.com", language="fr", role="host")
    _entry(db, "salon-b", "host@example.com", role="host")
    _entry(db, "salon-c", "host@example.com", role="host")

    result = salon_event_service.purge_silent_participations(db)
    assert result["matched"] == 2
    assert result["byRole"] == {"host": 2}


def test_a_purge_with_nothing_silent_is_not_an_error(db, salon):
    _entry(db, "salon-a", "spoke@example.com", language="en")
    result = salon_event_service.purge_silent_participations(db, confirm=True)
    assert result["status"] == "purged"
    assert result["deleted"] == 0
