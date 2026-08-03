"""Tests for the ads tables — what to say, where, and how many times."""
import pytest
from sqlalchemy.exc import IntegrityError

from src.models.ad import SALES_PITCH_MAX, Ad, AdRegion
from src.models.advertiser import Advertiser
from src.services import location_service

MONTREAL = location_service.plus_code(45.5019, -73.5674)


@pytest.fixture(autouse=True)
def advertiser(db):
    """Every ad has an owner. Nullable was never the right shape: an ad nobody can be
    invoiced for or held responsible for should not be storable."""
    row = Advertiser(company="Café Rivard", email="ads@caferivard.example")
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _ad(db, **overrides):
    fields = {
        # The autouse fixture above guarantees exactly one, so no test has to thread an
        # owner through just to exercise a pitch or a cell.
        "advertiser_id": db.query(Advertiser).one().advertiser_id,
        "sales_pitch": "Come for the coffee, stay for the pastry.",
        "spoken_language": "en",
        "number_of_broadcasts_left": 100,
        "topic": "coffee",
    }
    fields.update(overrides)
    row = Ad(**fields)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


# ─── The pitch ────────────────────────────────────────────────────────────────

def test_an_ad_stores_its_pitch_verbatim(db):
    """The agent renders it for the listener, so the words stored must be the words given."""
    pitch = "Chez Rivard, le café est torréfié sur place."
    assert _ad(db, sales_pitch=pitch).sales_pitch == pitch


def test_a_pitch_may_fill_the_whole_limit(db):
    assert len(_ad(db, sales_pitch="x" * SALES_PITCH_MAX).sales_pitch) == SALES_PITCH_MAX


def test_a_longer_pitch_is_refused(db):
    """Refused by a constraint rather than truncated: half a claim is worse than none."""
    with pytest.raises(IntegrityError):
        _ad(db, sales_pitch="x" * (SALES_PITCH_MAX + 1))


def test_an_empty_pitch_is_refused(db):
    with pytest.raises(IntegrityError):
        _ad(db, sales_pitch="")


def test_a_space_only_pitch_is_refused(db):
    """Spaces would be broadcast as silence, which is worse than an error."""
    with pytest.raises(IntegrityError):
        _ad(db, sales_pitch="     ")


def test_tabs_and_newlines_are_not_caught_by_the_database(db):
    """Documents a real limit rather than implying one that does not exist.

    trim() strips spaces and nothing else — on Postgres as much as on SQLite — so a pitch
    made of tabs and newlines satisfies the constraint. Catching it needs a validator on
    whatever input path eventually creates an ad. There is none yet, and a test that
    pretended the database handled it would be the reason nobody ever wrote one.
    """
    assert _ad(db, sales_pitch="\t\n\t").ad_id is not None


# ─── Broadcasts ───────────────────────────────────────────────────────────────

def test_broadcasts_default_to_none_left(db, advertiser):
    """An ad with no paid broadcasts must not be heard by accident."""
    ad = Ad(sales_pitch="Anything.", advertiser_id=advertiser.advertiser_id)
    db.add(ad)
    db.commit()
    db.refresh(ad)
    assert ad.number_of_broadcasts_left == 0


def test_broadcasts_cannot_go_negative(db):
    """This is what stops a concurrent decrement spending a broadcast that was not there."""
    ad = _ad(db, number_of_broadcasts_left=1)
    ad.number_of_broadcasts_left = -1
    with pytest.raises(IntegrityError):
        db.commit()


def test_exhausted_is_zero_not_deleted(db):
    """An ad that has been heard its full count has done what it was paid for; the row
    stays so the history survives."""
    ad = _ad(db, number_of_broadcasts_left=1)
    ad.number_of_broadcasts_left = 0
    db.commit()
    assert db.query(Ad).count() == 1


# ─── Regions ──────────────────────────────────────────────────────────────────

def test_an_ad_can_cover_several_cells(db):
    """An advertiser covering a city names several, which is why this is its own table."""
    ad = _ad(db)
    for code in (MONTREAL, "87Q8GD00+", "87Q8GF00+"):
        db.add(AdRegion(ad_id=ad.ad_id, google_plus_code=code))
    db.commit()
    assert db.query(AdRegion).filter(AdRegion.ad_id == ad.ad_id).count() == 3


def test_the_same_cell_cannot_be_listed_twice(db):
    ad = _ad(db)
    db.add(AdRegion(ad_id=ad.ad_id, google_plus_code=MONTREAL))
    db.commit()
    db.add(AdRegion(ad_id=ad.ad_id, google_plus_code=MONTREAL))
    with pytest.raises(IntegrityError):
        db.commit()


def test_a_blank_cell_is_refused(db):
    ad = _ad(db)
    db.add(AdRegion(ad_id=ad.ad_id, google_plus_code="   "))
    with pytest.raises(IntegrityError):
        db.commit()


def test_regions_match_the_precision_recorded_for_participants(db):
    """A code is compared as a string, so a finer targeting code matches nothing at all
    rather than matching the cell that contains it. This guards the precision agreement."""
    ad = _ad(db)
    db.add(AdRegion(ad_id=ad.ad_id, google_plus_code=MONTREAL))
    db.commit()
    # What a participant standing a few hundred metres away would be recorded as.
    nearby = location_service.plus_code(45.5040, -73.5650)
    assert db.query(AdRegion).filter(AdRegion.google_plus_code == nearby).count() == 1
