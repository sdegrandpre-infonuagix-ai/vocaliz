"""The inventory an interpreter draws from: languages, substitutions, and what was heard.

Story 9.2 leaves the inherited exchange alone — the auction, the billing and the proof of
delivery are all untouched. What it adds is the half the multi-rooms topology needs: an ad
carries a set of target *languages* as well as a set of target cells, and may carry a verbatim
substitution for one language, read word for word.

Sets of rows rather than lists on the ad, for the same reason `ads_regions` already is: one ad
addresses several regions and several languages without a row per combination.

The third way of describing geography goes at the same time. `advertisers.target_countries`,
`target_regions` and the circle never had data behind them, and never could: naming the country
a cell falls in needs reverse geocoding that does not exist here.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from src.ad_selection import Advertisement, choose_ad, heard_in_salon, inventory
from src.models.ad import Ad, AdLanguage, AdRegion, AdSubstitution
from src.models.ad_broadcast import AdBroadcast
from src.models.advertiser import Advertiser
from src.models.salon import Salon
from src.models.user import User

MONTREAL = "87Q8GC"
QUEBEC = "87RCQ2"
NOW = datetime(2026, 3, 1, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def advertiser(db):
    row = Advertiser(company="Café Rivard", email="ads@caferivard.example")
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _ad(db, *, pitch="Come for the coffee.", cells=(), languages=(),
        substitutions=None, broadcasts=100, seconds=0, spoken_language="en"):
    row = Ad(
        advertiser_id=db.query(Advertiser).one().advertiser_id,
        sales_pitch=pitch,
        spoken_language=spoken_language,
        number_of_broadcasts_left=broadcasts,
        indicative_seconds=seconds,
    )
    db.add(row)
    db.flush()
    for cell in cells:
        db.add(AdRegion(ad_id=row.ad_id, google_plus_code=cell))
    for language in languages:
        db.add(AdLanguage(ad_id=row.ad_id, language=language))
    for language, text in (substitutions or {}).items():
        db.add(AdSubstitution(ad_id=row.ad_id, language=language, text=text))
    db.commit()
    db.refresh(row)
    return row


def _salon(db, name="salon-ads"):
    user = User(email=f"{uuid.uuid4()}@example.com")
    db.add(user)
    db.flush()
    row = Salon(
        host_user_id=user.id,
        livekit_room_name=name,
        source_type="url",
        source_content="c",
        status="active",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


# ── Target languages, as rows ─────────────────────────────────────────────────


def test_one_ad_addresses_several_languages_without_duplicating_the_row(db):
    """A row per combination is how an inventory table becomes unmaintainable."""
    ad = _ad(db, cells=(MONTREAL, QUEBEC), languages=("fr", "en", "es"))

    assert db.query(Ad).count() == 1
    assert {row.language for row in db.query(AdLanguage).all()} == {"fr", "en", "es"}
    assert {row.ad_id for row in db.query(AdLanguage).all()} == {ad.ad_id}


def test_a_language_is_named_once_per_ad(db):
    """The pair is the key: listing a language twice would double nothing but the joins."""
    ad = _ad(db, languages=("fr",))

    db.add(AdLanguage(ad_id=ad.ad_id, language="fr"))
    with pytest.raises(IntegrityError):
        db.commit()


def test_a_blank_language_is_refused(db):
    ad = _ad(db)

    db.add(AdLanguage(ad_id=ad.ad_id, language="  "))
    with pytest.raises(IntegrityError):
        db.commit()


def test_the_target_languages_go_with_the_ad(db):
    """Targeting rows are part of the ad, not evidence of anything — CASCADE, unlike a
    broadcast, which is billing evidence and must survive."""
    ad = _ad(db, languages=("fr", "en"))

    db.delete(ad)
    db.commit()

    assert db.query(AdLanguage).count() == 0


# ── Verbatim substitutions ────────────────────────────────────────────────────


def test_a_substitution_is_stored_for_one_language(db):
    ad = _ad(db, substitutions={"fr": "Achetez notre pain."})

    row = db.query(AdSubstitution).one()

    assert (row.ad_id, row.language, row.text) == (ad.ad_id, "fr", "Achetez notre pain.")


def test_a_substitution_is_named_once_per_language(db):
    """Two verbatim texts for one language is two answers to a question with one answer."""
    ad = _ad(db, substitutions={"fr": "Achetez notre pain."})

    db.add(AdSubstitution(ad_id=ad.ad_id, language="fr", text="Autre chose."))
    with pytest.raises(IntegrityError):
        db.commit()


def test_a_blank_substitution_is_refused(db):
    """It would be read out as a silence where the canonical creative would have been said."""
    ad = _ad(db)

    db.add(AdSubstitution(ad_id=ad.ad_id, language="fr", text="   "))
    with pytest.raises(IntegrityError):
        db.commit()


def test_substitutions_go_with_the_ad(db):
    ad = _ad(db, substitutions={"fr": "Achetez notre pain."})

    db.delete(ad)
    db.commit()

    assert db.query(AdSubstitution).count() == 0


# ── An indicative duration ────────────────────────────────────────────────────


def test_the_duration_is_unset_by_default(db):
    """Zero means nobody estimated it, which is honest. It is indicative and never
    contractual: the same text translated runs to different lengths, and what counts in the
    interpreter's lag is the duration actually rendered."""
    assert _ad(db).indicative_seconds == 0


def test_the_duration_is_stored_when_given(db):
    assert _ad(db, seconds=12).indicative_seconds == 12


def test_a_negative_duration_is_refused(db):
    with pytest.raises(IntegrityError):
        _ad(db, seconds=-1)


# ── Reading the inventory ─────────────────────────────────────────────────────


def test_an_ad_becomes_an_advertisement_carrying_its_targeting(db):
    ad = _ad(
        db,
        pitch="Come for the coffee.",
        cells=(MONTREAL,),
        languages=("fr", "en"),
        substitutions={"fr": "Venez pour le café."},
        seconds=9,
    )

    entry, = inventory(db)

    assert entry.id == ad.ad_id
    assert entry.cells == frozenset({MONTREAL})
    assert entry.languages == frozenset({"fr", "en"})
    assert entry.sales_pitch == "Come for the coffee."
    assert entry.substitutions == {"fr": "Venez pour le café."}
    assert entry.indicative_seconds == 9


def test_an_exhausted_ad_is_not_in_the_inventory(db):
    """Zero broadcasts left is an ad that has done what it was paid for."""
    _ad(db, broadcasts=0)

    assert inventory(db) == []


def test_an_ad_with_no_targeting_at_all_is_generic(db):
    """Empty on both dimensions is the only thing that means unrestricted — which is what a
    generic ad is."""
    _ad(db, cells=(), languages=())

    entry, = inventory(db)

    assert entry.generic is True


def test_an_ad_targeted_on_one_dimension_is_not_generic(db):
    """Language-only targeting reaches anybody who speaks it, including somebody who refused
    geolocation. It is still a choice about who hears it, so it is not generic."""
    _ad(db, cells=(), languages=("fr",))

    entry, = inventory(db)

    assert entry.generic is False
    assert choose_ad(inventory(db), cell="", language="fr", heard={}) is not None


def test_selection_runs_against_the_real_inventory(db):
    """The end of the wire: rows in, one advertisement out."""
    _ad(db, pitch="elsewhere", cells=(QUEBEC,), languages=("fr",))
    local = _ad(db, pitch="local", cells=(MONTREAL,), languages=("fr",))

    chosen = choose_ad(inventory(db), cell=MONTREAL, language="fr", heard={})

    assert chosen.id == local.ad_id


# ── What was already heard here ───────────────────────────────────────────────


def _broadcast(db, ad, salon, *, delivered_at):
    row = AdBroadcast(
        ad_id=ad.ad_id,
        advertiser_id=ad.advertiser_id,
        salon_id=salon.id,
        salon_name=salon.livekit_room_name,
        amount_cents=5,
        delivered_at=delivered_at,
    )
    db.add(row)
    db.commit()
    return row


def test_a_delivered_broadcast_counts_as_heard(db):
    ad = _ad(db, languages=("fr",))
    salon = _salon(db)
    _broadcast(db, ad, salon, delivered_at=NOW)

    assert heard_in_salon(db, salon.id) == {ad.ad_id: NOW}


def test_a_reserved_broadcast_that_was_never_spoken_was_never_heard(db):
    """The same distinction the billing already makes: charging for a sentence nobody heard
    is the outcome this must not produce, and replaying one nobody heard is the same error
    from the participant's side."""
    ad = _ad(db, languages=("fr",))
    salon = _salon(db)
    _broadcast(db, ad, salon, delivered_at=None)

    assert heard_in_salon(db, salon.id) == {}


def test_the_most_recent_delivery_is_the_one_that_counts(db):
    """Replay order is oldest-heard first, so an ad heard twice is as fresh as its last
    airing rather than its first."""
    ad = _ad(db, languages=("fr",))
    salon = _salon(db)
    _broadcast(db, ad, salon, delivered_at=NOW - timedelta(hours=2))
    _broadcast(db, ad, salon, delivered_at=NOW)

    assert heard_in_salon(db, salon.id) == {ad.ad_id: NOW}


def test_another_salon_is_a_clean_slate(db):
    """What somebody heard elsewhere is not something this room has to work around."""
    ad = _ad(db, languages=("fr",))
    theirs = _salon(db, "salon-theirs")
    mine = _salon(db, "salon-mine")
    _broadcast(db, ad, theirs, delivered_at=NOW)

    assert heard_in_salon(db, mine.id) == {}


def test_an_ad_heard_here_gives_way_to_one_that_was_not(db):
    """The whole point of reading the deliveries: selection against a real history."""
    already = _ad(db, pitch="already", cells=(MONTREAL,), languages=("fr",))
    fresh = _ad(db, pitch="fresh", cells=(MONTREAL,), languages=("fr",))
    salon = _salon(db)
    _broadcast(db, already, salon, delivered_at=NOW)

    chosen = choose_ad(
        inventory(db), cell=MONTREAL, language="fr", heard=heard_in_salon(db, salon.id)
    )

    assert chosen.id == fresh.ad_id


# ── The third geography is gone ───────────────────────────────────────────────


def test_the_dead_jsonb_geography_is_removed(db):
    """It never had data behind it and never could: naming the country a cell falls in needs
    reverse geocoding that does not exist here. Two ways of saying where an ad may be heard
    are enough — cells on the ad, and cells reached through the advertiser's regions."""
    columns = set(Advertiser.__table__.c.keys())

    assert "target_countries" not in columns
    assert "target_regions" not in columns
    assert {"target_latitude", "target_longitude", "target_radius_km"} & columns == set()


def test_the_two_surviving_geographies_still_resolve_to_cells(db):
    """Both answer the same question at different grains, and both are strings comparable
    against `salon_events.plus_code` with no geometry involved."""
    from src.models.region import RegionGooglePlusCode

    assert "google_plus_code" in AdRegion.__table__.c
    assert "google_plus_code" in RegionGooglePlusCode.__table__.c


def test_an_advertisement_is_a_plain_value(db):
    """Selection never holds an ORM row: it is a pure function over what it is given, and a
    detached instance lazy-loading a relationship mid-Salon is not a failure worth having."""
    _ad(db, languages=("fr",))

    entry, = inventory(db)

    assert isinstance(entry, Advertisement)
    with pytest.raises(Exception):
        entry.sales_pitch = "changed"
