"""Nothing is billed when a Salon ends.

This file used to test the opposite. Story 4.4 charged a host $5/hr at the end of a Salon
for time beyond a free trial hour, and twelve tests here pinned every corner of it: the
proration, the sub-cent carry-forward, the advance of `billed_seconds` so a span was never
charged twice.

That model is gone. Consumption is settled as it happens, on the heartbeat, against a
prepaid balance — so by the time a Salon closes there is nothing left to collect.

What is worth testing now is the **absence**, which is not the same as deleting the file and
moving on. While both paths were wired, the same conversation would have been taken twice:
once from the balance tick by tick, and again from a card at the end. That is the defect
these tests exist to keep from coming back, and it is invisible in any test that only
watches the balance go down correctly.
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from src.ledger import EventType, Pool, append
from src.models.billing_event import BillingEvent
from src.models.salon import Salon
from src.models.user import User
from src.services import stripe_service
from src.services.jwt_service import issue_token


@pytest.fixture
def host_with_a_card(db):
    """A host who has spent time and has a card on file — the exact account the retired
    path would have charged."""
    u = User(
        email="15148880030@example.com",
        phone_number="+15148880030",
        trial_seconds_used=7200,
        billed_seconds=0,
        stripe_customer_id="cus_paid1",
        stripe_payment_method_id="pm_paid1",
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    append(
        db,
        type=EventType.RECHARGED,
        subject_id=u.id,
        amount_cents=1000,
        pool=Pool.PAID,
    )
    db.commit()
    return u, issue_token(str(u.id))


def _active_salon(db, host):
    salon = Salon(
        host_user_id=host.id,
        livekit_room_name="salon-billing",
        source_type="url",
        source_content="c",
        status="active",
        created_at=datetime.now(tz=timezone.utc) - timedelta(seconds=600),
    )
    db.add(salon)
    db.commit()
    db.refresh(salon)
    return salon


# ─── The absence ──────────────────────────────────────────────────────────────


def test_ending_a_salon_charges_no_card(client, db, host_with_a_card):
    """The whole point. Two hours of use, a card on file, and Stripe is not called —
    because the money was already taken as the conversation happened."""
    host, token = host_with_a_card
    salon = _active_salon(db, host)

    with patch("stripe.PaymentIntent.create") as create:
        resp = client.post(
            f"/salons/{salon.id}/end", headers={"Authorization": f"Bearer {token}"}
        )

    assert resp.status_code == 200
    create.assert_not_called()


def test_ending_a_salon_reports_no_billing(client, db, host_with_a_card):
    host, token = host_with_a_card
    salon = _active_salon(db, host)

    body = client.post(
        f"/salons/{salon.id}/end", headers={"Authorization": f"Bearer {token}"}
    ).json()

    assert body["billing"] is None


def test_ending_a_salon_writes_no_billing_event(client, db, host_with_a_card):
    """`billing_events` recorded charge attempts. No attempt, no row — and an empty table
    here is what says the end-of-Salon charge is really gone rather than merely failing."""
    host, token = host_with_a_card
    salon = _active_salon(db, host)

    client.post(f"/salons/{salon.id}/end", headers={"Authorization": f"Bearer {token}"})

    assert db.query(BillingEvent).count() == 0


def test_the_balance_is_not_touched_by_ending_a_salon(client, db, host_with_a_card):
    """Ending settles nothing financial. Whatever was consumed came off during the
    conversation; taking more here would be charging twice for one span."""
    from src.credit import balance

    host, token = host_with_a_card
    salon = _active_salon(db, host)
    before = balance(db, host.id).total_cents

    client.post(f"/salons/{salon.id}/end", headers={"Authorization": f"Bearer {token}"})

    assert balance(db, host.id).total_cents == before


def test_the_post_paid_entry_point_is_gone_rather_than_unused(db):
    """Removed, not left lying about. A function that can double-bill is not made safe by
    nobody calling it today — the next person to wire it up would have no way to know."""
    assert not hasattr(stripe_service, "bill_host_for_usage")
    assert not hasattr(stripe_service, "_billable_seconds")


def test_what_the_prepaid_model_still_needs_is_kept(db):
    """Creating the customer and attaching the card a top-up will draw on. Removing the
    charge must not remove the means to take a payment at all."""
    assert hasattr(stripe_service, "attach_payment_method")
