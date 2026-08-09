"""Tests for the advertisers table — who wants to reach whom."""
import pytest
from sqlalchemy.exc import IntegrityError

from src.models.advertiser import Advertiser


def _advertiser(db, **overrides):
    fields = {"company": "Café Rivard", "email": "ads@caferivard.example"}
    fields.update(overrides)
    row = Advertiser(**fields)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


# ─── Defaults ─────────────────────────────────────────────────────────────────

def test_new_advertiser_is_paused(db):
    """Nothing goes live before someone has read what it wants to say."""
    assert _advertiser(db).status == "paused"


def test_targeting_defaults_to_empty_lists_not_null(db):
    """[] means unrestricted. NULL would mean the same thing and sort differently."""
    row = _advertiser(db)
    for dimension in (row.target_languages, row.target_keywords):
        assert dimension == []


# ─── The dimensions the advertiser chooses ────────────────────────────────────

def test_geography_is_said_in_cells_and_nowhere_else(db):
    """The JSONB country and subdivision lists and the circle were dropped in Story 9.2.
    They were storable and never applicable: salon_events holds a grid cell, not a political
    boundary, and naming the country a cell falls in needs reverse geocoding that does not
    exist here. Where an advertiser wants to be heard is `advertisers_regions`."""
    columns = set(Advertiser.__table__.c.keys())

    assert not columns & {
        "target_countries",
        "target_regions",
        "target_latitude",
        "target_longitude",
        "target_radius_km",
    }


def test_stores_a_language_list(db):
    """The one dimension with participant data behind it today."""
    row = _advertiser(db, target_languages=["fr", "en"])
    db.expire_all()
    assert db.get(Advertiser, row.advertiser_id).target_languages == ["fr", "en"]


def test_stores_a_keyword_list(db):
    row = _advertiser(db, target_keywords=["coffee", "pastry", "montreal"])
    db.expire_all()
    assert db.get(Advertiser, row.advertiser_id).target_keywords == ["coffee", "pastry", "montreal"]


# ─── Constraints ──────────────────────────────────────────────────────────────

def test_status_is_constrained(db):
    with pytest.raises(IntegrityError):
        _advertiser(db, status="running")


def test_company_is_required(db):
    with pytest.raises(IntegrityError):
        _advertiser(db, company=None)


def test_email_is_required(db):
    with pytest.raises(IntegrityError):
        _advertiser(db, email=None)


def test_contact_details_are_optional(db):
    """A business may have no street address, and demanding a website before there is one
    invites a placeholder that is worse than blank."""
    row = _advertiser(db)
    assert (row.phone_number, row.address, row.website) == ("", "", "")


def test_stores_the_contact_details_when_given(db):
    row = _advertiser(
        db,
        phone_number="+15145550123",
        address="1 rue Rivard, Montréal",
        website="https://caferivard.example",
    )
    assert row.phone_number == "+15145550123"
    assert row.address == "1 rue Rivard, Montréal"
    assert row.website == "https://caferivard.example"
