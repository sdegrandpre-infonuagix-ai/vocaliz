"""Each participant's own options, settled as they join (FR35 / FR42).

The whole point of the epic is that a Salon does not have a mode — the people in it do. Three
participants therefore hold three independent sets of choices, and nothing about one of them
reaches another: a different tier, video on or off, a top-up amount of their own. The host
picking Mode C obliges nobody.

The one exception is the host offering to pay. Then the guest is placed in Mode B and not
asked at all, because asking somebody to choose a budget they are not spending is asking a
question with no meaning. FR42 outranks FR35, and only ever **upward**: an override that
could lower somebody's existing choice would be a host quietly downgrading a guest, which is
the thing this epic exists to make impossible.
"""
import uuid
from datetime import datetime, timezone

import pytest

from src.credit import Tier, grant_welcome_credit
from src.models.participant_options import ParticipantOptions
from src.participation import HOST_PAYS_TIER, join_options

SALON = uuid.uuid4()
HOST = uuid.uuid4()
GUEST = uuid.uuid4()
THIRD = uuid.uuid4()
NOW = datetime(2026, 3, 1, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _people_and_salon(db):
    """Real rows, because the options table really does reference them.

    Unlike the ledger, these are live preferences rather than evidence: they are meaningless
    once the account is gone, so the foreign keys belong — and the suite enforces them, which
    is why bare identifiers will not do here.
    """
    from src.models.salon import Salon
    from src.models.user import User

    for person in (HOST, GUEST, THIRD):
        db.add(User(id=person, email=f"{person}@example.com"))
    db.flush()
    db.add(
        Salon(
            id=SALON,
            host_user_id=HOST,
            livekit_room_name=f"room-{SALON}",
            source_type="none",
        )
    )
    db.flush()


def _another_salon(db):
    from src.models.salon import Salon

    other = uuid.uuid4()
    db.add(
        Salon(
            id=other, host_user_id=HOST, livekit_room_name=f"room-{other}", source_type="none"
        )
    )
    db.flush()
    return other


def _with_credit(db, person):
    grant_welcome_credit(
        db, subject_id=person, identifiers=[f"{uuid.uuid4()}@example.com"], now=NOW
    )
    db.flush()


# ── The guest configures their own ────────────────────────────────────────────


def test_a_guest_chooses_their_own_tier(db):
    options = join_options(
        db, salon_id=SALON, user_id=GUEST, chosen_tier=Tier.MODE_A, now=NOW
    )
    db.flush()

    assert options.tier == Tier.MODE_A.value


def test_a_guest_chooses_video_for_themselves(db):
    options = join_options(
        db, salon_id=SALON, user_id=GUEST, chosen_tier=Tier.BASE, video=True, now=NOW
    )
    db.flush()

    assert options.video is True


def test_a_guest_chooses_their_own_top_up_amount(db):
    options = join_options(
        db, salon_id=SALON, user_id=GUEST, chosen_tier=Tier.BASE, top_up_cents=2000, now=NOW
    )
    db.flush()

    assert options.top_up_cents == 2000


def test_choosing_nothing_lands_on_the_floor(db):
    """Base is what applies when nobody chose, which is different from choosing Base — but
    at the moment of joining, somebody has to be somewhere."""
    options = join_options(db, salon_id=SALON, user_id=GUEST, now=NOW)
    db.flush()

    assert options.tier == Tier.BASE.value


# ── Three sets of choices, no interaction ─────────────────────────────────────


def test_three_participants_hold_three_independent_sets(db):
    join_options(db, salon_id=SALON, user_id=HOST, chosen_tier=Tier.MODE_C, video=True, now=NOW)
    join_options(db, salon_id=SALON, user_id=GUEST, chosen_tier=Tier.BASE, video=False, now=NOW)
    join_options(
        db, salon_id=SALON, user_id=THIRD, chosen_tier=Tier.MODE_A, top_up_cents=500, now=NOW
    )
    db.flush()

    rows = {row.user_id: row for row in db.query(ParticipantOptions).all()}

    assert rows[HOST].tier == Tier.MODE_C.value
    assert rows[GUEST].tier == Tier.BASE.value
    assert rows[THIRD].tier == Tier.MODE_A.value
    assert (rows[HOST].video, rows[GUEST].video) == (True, False)
    assert rows[THIRD].top_up_cents == 500


def test_the_hosts_choice_does_not_reach_a_guest(db):
    join_options(db, salon_id=SALON, user_id=HOST, chosen_tier=Tier.MODE_C, now=NOW)

    guest = join_options(db, salon_id=SALON, user_id=GUEST, now=NOW)
    db.flush()

    assert guest.tier == Tier.BASE.value


def test_the_same_person_in_two_salons_chooses_twice(db):
    """Options belong to a person *in a Salon*, not to a person. Somebody may want Mode C for
    a client call and Base for a chat with a friend."""
    other_salon = _another_salon(db)
    join_options(db, salon_id=SALON, user_id=GUEST, chosen_tier=Tier.MODE_C, now=NOW)
    join_options(db, salon_id=other_salon, user_id=GUEST, chosen_tier=Tier.BASE, now=NOW)
    db.flush()

    assert db.query(ParticipantOptions).count() == 2


def test_rejoining_replaces_rather_than_duplicates(db):
    join_options(db, salon_id=SALON, user_id=GUEST, chosen_tier=Tier.BASE, now=NOW)
    db.flush()

    join_options(db, salon_id=SALON, user_id=GUEST, chosen_tier=Tier.MODE_A, now=NOW)
    db.flush()

    rows = db.query(ParticipantOptions).all()
    assert len(rows) == 1
    assert rows[0].tier == Tier.MODE_A.value


# ── The welcome credit comes first ────────────────────────────────────────────


def test_a_newcomers_credit_is_applied_before_any_payment_is_asked_for(db):
    """Asking somebody to pay while five dollars of theirs sits unspent is asking for money
    that is not needed yet."""
    _with_credit(db, GUEST)

    options = join_options(db, salon_id=SALON, user_id=GUEST, chosen_tier=Tier.MODE_A, now=NOW)
    db.flush()

    assert options.covered_by_credit_minutes == 40
    assert options.payment_required is False


def test_somebody_with_no_credit_is_asked_to_pay(db):
    options = join_options(db, salon_id=SALON, user_id=GUEST, chosen_tier=Tier.MODE_A, now=NOW)
    db.flush()

    assert options.covered_by_credit_minutes is None
    assert options.payment_required is True


def test_a_top_up_removes_the_need_to_pay_on_the_spot(db):
    options = join_options(
        db, salon_id=SALON, user_id=GUEST, chosen_tier=Tier.MODE_A, top_up_cents=2000, now=NOW
    )
    db.flush()

    assert options.payment_required is False


# ── The host paying overrides, and only upward ────────────────────────────────


def test_the_host_paying_places_a_guest_in_mode_b(db):
    assert HOST_PAYS_TIER is Tier.MODE_B

    options = join_options(db, salon_id=SALON, user_id=GUEST, host_pays=True, now=NOW)
    db.flush()

    assert options.tier == Tier.MODE_B.value


def test_a_guest_the_host_pays_for_is_not_asked_to_choose(db):
    """Asking somebody to pick a budget they are not spending is a question with no meaning."""
    options = join_options(db, salon_id=SALON, user_id=GUEST, host_pays=True, now=NOW)
    db.flush()

    assert options.choice_offered is False


def test_the_host_paying_never_lowers_an_existing_higher_choice(db):
    """Only ever upward. An override able to lower somebody's choice would be a host quietly
    downgrading a guest, which is the thing this epic exists to make impossible."""
    options = join_options(
        db, salon_id=SALON, user_id=GUEST, chosen_tier=Tier.MODE_C, host_pays=True, now=NOW
    )
    db.flush()

    assert options.tier == Tier.MODE_C.value


def test_the_host_paying_lifts_somebody_off_the_floor(db):
    options = join_options(
        db, salon_id=SALON, user_id=GUEST, chosen_tier=Tier.BASE, host_pays=True, now=NOW
    )
    db.flush()

    assert options.tier == Tier.MODE_B.value


def test_a_guest_the_host_pays_for_is_never_asked_for_money(db):
    options = join_options(db, salon_id=SALON, user_id=GUEST, host_pays=True, now=NOW)
    db.flush()

    assert options.payment_required is False


def test_the_host_paying_carries_no_advertising(db):
    """Mode B and not Mode A. Somebody whose participation is a gift should not also be the
    product being sold to."""
    from src.tiers import TierOffer

    assert TierOffer.of(HOST_PAYS_TIER).advertising is False


def test_the_choice_is_offered_when_the_host_does_not_pay(db):
    options = join_options(db, salon_id=SALON, user_id=GUEST, now=NOW)
    db.flush()

    assert options.choice_offered is True


def test_the_host_paying_for_one_guest_leaves_another_untouched(db):
    """The flag belongs to the Salon; what it produces still lands per participant."""
    join_options(db, salon_id=SALON, user_id=GUEST, host_pays=True, now=NOW)
    third = join_options(db, salon_id=SALON, user_id=THIRD, chosen_tier=Tier.BASE, now=NOW)
    db.flush()

    assert third.tier == Tier.BASE.value
    assert third.choice_offered is True


def test_the_offer_to_pay_lives_on_the_salon_but_the_mode_never_does(db):
    """One offer made once, so the flag belongs to the Salon. What it produces still lands
    per participant — a mode column here would assert in the schema the very thing this epic
    denies."""
    from src.models.salon import Salon

    assert "host_pays_all" in Salon.__table__.c
    assert "tier" not in Salon.__table__.c
    assert "mode" not in Salon.__table__.c


def test_nobody_pays_for_anybody_unless_the_host_said_so(db):
    from src.models.salon import Salon

    salon = db.query(Salon).filter(Salon.id == SALON).one()

    assert salon.host_pays_all is False
