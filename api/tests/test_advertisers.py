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
    for dimension in (
        row.target_countries,
        row.target_regions,
        row.target_languages,
        row.target_keywords,
    ):
        assert dimension == []


def test_no_circle_by_default(db):
    row = _advertiser(db)
    assert row.target_latitude is None
    assert row.target_longitude is None
    assert row.target_radius_km is None


# ─── The three dimensions the advertiser chooses ──────────────────────────────

def test_stores_a_country_and_region_list(db):
    row = _advertiser(db, target_countries=["CA", "FR"], target_regions=["CA-QC"])
    db.expire_all()
    fetched = db.get(Advertiser, row.advertiser_id)
    assert fetched.target_countries == ["CA", "FR"]
    assert fetched.target_regions == ["CA-QC"]


def test_stores_a_language_list(db):
    """The one dimension with participant data behind it today."""
    row = _advertiser(db, target_languages=["fr", "en"])
    db.expire_all()
    assert db.get(Advertiser, row.advertiser_id).target_languages == ["fr", "en"]


def test_stores_a_keyword_list(db):
    row = _advertiser(db, target_keywords=["coffee", "pastry", "montreal"])
    db.expire_all()
    assert db.get(Advertiser, row.advertiser_id).target_keywords == ["coffee", "pastry", "montreal"]


def test_stores_a_targeting_circle(db):
    row = _advertiser(
        db, target_latitude=45.5019, target_longitude=-73.5674, target_radius_km=2.5
    )
    db.expire_all()
    fetched = db.get(Advertiser, row.advertiser_id)
    assert float(fetched.target_latitude) == pytest.approx(45.5019)
    assert float(fetched.target_longitude) == pytest.approx(-73.5674)
    assert float(fetched.target_radius_km) == pytest.approx(2.5)


# ─── Constraints ──────────────────────────────────────────────────────────────

def test_status_is_constrained(db):
    with pytest.raises(IntegrityError):
        _advertiser(db, status="running")


def test_half_a_circle_is_rejected(db):
    """Two of the three numbers describes nothing — it must not be storable."""
    with pytest.raises(IntegrityError):
        _advertiser(db, target_latitude=45.5019, target_longitude=-73.5674)


def test_a_circle_needs_its_centre(db):
    with pytest.raises(IntegrityError):
        _advertiser(db, target_radius_km=5.0)


def test_radius_must_be_positive(db):
    """A radius of zero matches nobody while looking like a deliberate choice."""
    with pytest.raises(IntegrityError):
        _advertiser(
            db, target_latitude=45.5019, target_longitude=-73.5674, target_radius_km=0
        )


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
