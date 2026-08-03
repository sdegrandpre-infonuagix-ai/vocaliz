"""Positions are stored as neighbourhood-scale Plus Codes, never as points."""
import pytest

from src.config import settings
from src.models.salon_event import SalonEvent
from src.models.session import SessionModel
from src.models.user import User
from src.services import location_service, salon_event_service

# Place Ville-Marie, Montréal.
LAT, LON = 45.5019, -73.5674


@pytest.fixture
def session(db):
    user = User(email="geo@example.com")
    db.add(user)
    db.commit()
    db.refresh(user)
    s = SessionModel(
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

def test_the_precise_coordinates_never_reach_the_row(db, session):
    """The whole point: encoding happens at ingestion, so there is nothing precise at
    rest to round on the way out."""
    salon_event_service.record_entry(
        db,
        email="geo@example.com",
        user_type="host",
        salon_name=session.livekit_room_name,
        latitude=LAT,
        longitude=LON,
    )
    row = db.query(SalonEvent).one()
    assert row.plus_code == location_service.plus_code(LAT, LON)
    # The columns that used to hold a point are gone, not merely unused.
    assert not hasattr(row, "gps_latitude")
    assert not hasattr(row, "client_ip")


def test_declining_the_prompt_leaves_no_location(db, session):
    """The common case, and not an error."""
    salon_event_service.record_entry(
        db, email="geo@example.com", user_type="host", salon_name=session.livekit_room_name
    )
    assert db.query(SalonEvent).one().plus_code == ""


def test_a_position_granted_on_re_entry_is_filled_in(db, session):
    salon_event_service.record_entry(
        db, email="geo@example.com", user_type="host", salon_name=session.livekit_room_name
    )
    salon_event_service.record_entry(
        db,
        email="geo@example.com",
        user_type="host",
        salon_name=session.livekit_room_name,
        latitude=LAT,
        longitude=LON,
    )
    assert db.query(SalonEvent).one().plus_code == location_service.plus_code(LAT, LON)


def test_a_second_reading_does_not_replace_the_first(db, session):
    """Someone who moves during a salon keeps the cell they arrived in — a participation
    has one location, and the last reading is no truer than the first."""
    salon_event_service.record_entry(
        db,
        email="geo@example.com",
        user_type="host",
        salon_name=session.livekit_room_name,
        latitude=LAT,
        longitude=LON,
    )
    first = db.query(SalonEvent).one().plus_code
    salon_event_service.record_entry(
        db,
        email="geo@example.com",
        user_type="host",
        salon_name=session.livekit_room_name,
        latitude=46.8139,
        longitude=-71.2080,
    )
    assert db.query(SalonEvent).one().plus_code == first
