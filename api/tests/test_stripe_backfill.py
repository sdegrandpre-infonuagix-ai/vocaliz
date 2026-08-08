"""The one-off that moves already-written Stripe metadata into the vocaliz_ namespace.

It writes to live billing records, runs once, and is the kind of code nobody reads again.
Those are the three reasons to test it rather than to run it carefully.

What matters is not that it renames — it is that a second run is free, that a failure
does not strand the rest, and that a dry run touches no write endpoint at all.
"""
from unittest.mock import patch

import stripe

from src.models.advertiser import Advertiser
from src.models.user import User
from src.services import stripe_backfill
from src.services.stripe_backfill import _patch_for


class _Obj:
    def __init__(self, metadata):
        self.metadata = metadata


def _host(db, customer_id="cus_1"):
    user = User(email=f"{customer_id}@example.com", stripe_customer_id=customer_id)
    db.add(user)
    db.commit()
    return user


# ── The rename itself ────────────────────────────────────────────────────────────────

def test_the_old_key_is_blanked_in_the_same_call_that_writes_the_new_one():
    """Stripe merges the dict it is given and reads "" as a delete, so one update does
    both. Two calls would leave a window where an export shows the key twice."""
    assert _patch_for({"salon_user_id": "u-1"}) == {
        "vocaliz_user_id": "u-1",
        "salon_user_id": "",
    }


def test_the_session_era_key_lands_on_the_salon_name():
    assert _patch_for({"salon_session_id": "s-1"}) == {
        "vocaliz_salon_id": "s-1",
        "salon_session_id": "",
    }


def test_bare_advertising_keys_are_namespaced_too():
    assert _patch_for({"ad_id": "a-1", "broadcast_id": "b-1"}) == {
        "vocaliz_ad_id": "a-1",
        "vocaliz_broadcast_id": "b-1",
        "ad_id": "",
        "broadcast_id": "",
    }


def test_an_object_with_nothing_to_rename_yields_no_patch():
    """This is what makes a second run free: no patch means no API call."""
    assert _patch_for({"vocaliz_user_id": "u-1"}) == {}
    assert _patch_for({}) == {}
    assert _patch_for(None) == {}


def test_metadata_belonging_to_someone_else_is_left_alone():
    """The map is explicit precisely so a prefix rule cannot rewrite another
    integration's keys on a customer we happen to share."""
    assert _patch_for({"acme_crm_id": "x", "notes": "hello"}) == {}


def test_a_collision_keeps_the_newer_key_and_drops_the_older():
    """Both spellings present means a run was interrupted between write and delete. The
    namespaced value is what current code writes, so it is the fresher of the two."""
    out = _patch_for({"salon_user_id": "stale", "vocaliz_user_id": "fresh"})
    assert out == {"salon_user_id": ""}


# ── The run ──────────────────────────────────────────────────────────────────────────

def test_a_dry_run_calls_no_write_endpoint(db):
    _host(db)

    with (
        patch("stripe.Customer.retrieve", return_value=_Obj({"salon_user_id": "u-1"})),
        patch("stripe.Customer.modify") as modify,
    ):
        result = stripe_backfill.run(db)

    modify.assert_not_called()
    assert result["status"] == "dry_run"
    assert result["renamed"] == 1
    assert result["keysMoved"] == 1


def test_applying_sends_one_merged_update_per_object(db):
    user = _host(db)

    with (
        patch("stripe.Customer.retrieve", return_value=_Obj({"salon_user_id": str(user.id)})),
        patch("stripe.Customer.modify") as modify,
    ):
        result = stripe_backfill.run(db, apply=True)

    modify.assert_called_once_with(
        "cus_1", metadata={"vocaliz_user_id": str(user.id), "salon_user_id": ""}
    )
    assert result == {
        "status": "applied",
        "examined": 1,
        "renamed": 1,
        "alreadyNamespaced": 0,
        "failed": 0,
        "keysMoved": 1,
    }


def test_a_second_run_changes_nothing(db):
    _host(db)

    with (
        patch("stripe.Customer.retrieve", return_value=_Obj({"vocaliz_user_id": "u-1"})),
        patch("stripe.Customer.modify") as modify,
    ):
        result = stripe_backfill.run(db, apply=True)

    modify.assert_not_called()
    assert result["renamed"] == 0
    assert result["alreadyNamespaced"] == 1


def test_one_unreachable_object_does_not_strand_the_others(db):
    """A customer deleted in the dashboard must not stop the backfill at row three."""
    _host(db, "cus_1")
    _host(db, "cus_2")

    def retrieve(stripe_id):
        if stripe_id == "cus_1":
            raise stripe.StripeError("no such customer")
        return _Obj({"salon_user_id": "u-2"})

    with (
        patch("stripe.Customer.retrieve", side_effect=retrieve),
        patch("stripe.Customer.modify") as modify,
    ):
        result = stripe_backfill.run(db, apply=True)

    assert result["failed"] == 1
    assert result["renamed"] == 1
    modify.assert_called_once()


def test_advertiser_customers_are_swept_alongside_host_customers(db):
    """Both tables hold Stripe customer ids, and an advertiser left behind is the same
    reconciliation problem in a table nobody thinks to check."""
    advertiser = Advertiser(email="ads@example.com", company="Acme", stripe_customer_id="cus_adv")
    db.add(advertiser)
    db.commit()

    with (
        patch("stripe.Customer.retrieve", return_value=_Obj({"advertiser_id": "adv-1"})),
        patch("stripe.Customer.modify") as modify,
    ):
        stripe_backfill.run(db, apply=True)

    modify.assert_called_once_with(
        "cus_adv", metadata={"vocaliz_advertiser_id": "adv-1", "advertiser_id": ""}
    )
