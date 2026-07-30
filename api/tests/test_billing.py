"""Tests for Story 4.4 — Facturation à l'Heure Après l'Essai Gratuit.

A host with a saved payment method is charged $5/hr, prorated to the second,
for time used beyond their free trial hour. Guests are never billed.
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
import stripe

from src.config import settings
from src.models.billing_event import BillingEvent
from src.models.invitation import Invitation
from src.models.session import SessionModel
from src.models.user import User
from src.services import stripe_service
from src.services.jwt_service import issue_token


# ─── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def paid_host(db):
    """A host who has exhausted the free hour and has a saved payment method."""
    u = User(
        phone_number="+15148880030",
        trial_seconds_used=settings.free_trial_limit_seconds,  # exactly at the cap
        billed_seconds=0,
        stripe_customer_id="cus_paid1",
        stripe_payment_method_id="pm_paid1",
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u, issue_token(str(u.id))


def _active_session(db, host, *, created_offset_s=0, heartbeat_offset_s=None):
    """Create an active session for a host with controllable timestamps."""
    now = datetime.now(tz=timezone.utc)
    s = SessionModel(
        host_user_id=host.id,
        livekit_room_name=f"salon-room-{host.phone_number[-4:]}-{created_offset_s}",
        source_type="url",
        source_url="https://example.com/x",
        source_content="content",
        status="active",
        created_at=now - timedelta(seconds=created_offset_s),
    )
    if heartbeat_offset_s is not None:
        s.last_heartbeat_at = now - timedelta(seconds=heartbeat_offset_s)
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def _mock_intent(intent_id="pi_test123"):
    m = MagicMock()
    m.id = intent_id
    return m


# ─── Prorating math (unit) ───────────────────────────────────────────────────

def test_amount_cents_full_hour():
    """One hour of billable time == the full hourly rate."""
    assert stripe_service._amount_cents(3600) == settings.hourly_rate_cents


def test_amount_cents_prorated_half_hour():
    """Thirty minutes == half the hourly rate."""
    assert stripe_service._amount_cents(1800) == round(settings.hourly_rate_cents / 2)


def test_amount_cents_prorated_to_the_second():
    """Prorating is per-second, not per-minute (720 s → 100 cents at $5/hr)."""
    assert stripe_service._amount_cents(720) == 100


def test_billable_seconds_only_counts_beyond_trial():
    """Only host seconds past the free-trial cap are billable."""
    host = User(
        phone_number="+1",
        trial_seconds_used=settings.free_trial_limit_seconds + 900,
        billed_seconds=0,
    )
    assert stripe_service._billable_seconds(host) == 900


def test_billable_seconds_subtracts_already_billed():
    """Seconds already charged are not billed twice."""
    host = User(
        phone_number="+1",
        trial_seconds_used=settings.free_trial_limit_seconds + 900,
        billed_seconds=600,
    )
    assert stripe_service._billable_seconds(host) == 300


# ─── end_session billing (integration) ───────────────────────────────────────

def test_host_charged_for_overage_on_session_end(client, db, paid_host):
    """A host past their free hour is charged at $5/hr prorated for overage."""
    host, token = paid_host
    # 720 s of host time already accumulated beyond the cap, no heartbeat gap.
    host.trial_seconds_used = settings.free_trial_limit_seconds + 720
    db.commit()
    session = _active_session(db, host, created_offset_s=0, heartbeat_offset_s=0)

    with patch("stripe.PaymentIntent.create", return_value=_mock_intent()) as mock_create:
        resp = client.post(
            f"/sessions/{session.id}/end",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert resp.status_code == 200
    billing = resp.json()["billing"]
    assert billing is not None
    assert billing["billedSeconds"] == 720
    assert billing["amountCents"] == 100  # 720 s at $5/hr
    assert billing["status"] == "succeeded"

    # Stripe was charged off-session against the saved method.
    kwargs = mock_create.call_args.kwargs
    assert kwargs["amount"] == 100
    assert kwargs["currency"] == settings.billing_currency
    assert kwargs["customer"] == "cus_paid1"
    assert kwargs["payment_method"] == "pm_paid1"
    assert kwargs["off_session"] is True
    assert kwargs["confirm"] is True


def test_billed_seconds_advances_and_prevents_double_billing(client, db, paid_host):
    """billed_seconds advances so the same span is never charged twice."""
    host, token = paid_host
    host.trial_seconds_used = settings.free_trial_limit_seconds + 720
    db.commit()
    session = _active_session(db, host, created_offset_s=0, heartbeat_offset_s=0)

    with patch("stripe.PaymentIntent.create", return_value=_mock_intent()):
        client.post(f"/sessions/{session.id}/end", headers={"Authorization": f"Bearer {token}"})

    db.expire(host)
    db.refresh(host)
    assert host.billed_seconds == 720

    # A BillingEvent audit row was recorded.
    events = db.query(BillingEvent).filter(BillingEvent.host_user_id == host.id).all()
    assert len(events) == 1
    assert events[0].status == "succeeded"
    assert events[0].amount_cents == 100
    assert events[0].stripe_payment_intent_id == "pi_test123"


def test_no_charge_when_within_free_trial(client, db):
    """A host still within the free hour is not charged."""
    u = User(
        phone_number="+15148880031",
        trial_seconds_used=100,
        stripe_customer_id="cus_x",
        stripe_payment_method_id="pm_x",
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    token = issue_token(str(u.id))
    session = _active_session(db, u, created_offset_s=0, heartbeat_offset_s=0)

    with patch("stripe.PaymentIntent.create") as mock_create:
        resp = client.post(f"/sessions/{session.id}/end", headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 200
    assert resp.json()["billing"] is None
    mock_create.assert_not_called()


def test_no_charge_without_payment_method_carries_forward(client, db):
    """A host who crossed into paid usage but has no card is not charged;
    billed_seconds stays at 0 so the span is captured on a later session."""
    u = User(
        phone_number="+15148880032",
        trial_seconds_used=settings.free_trial_limit_seconds + 600,
        billed_seconds=0,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    token = issue_token(str(u.id))
    session = _active_session(db, u, created_offset_s=0, heartbeat_offset_s=0)

    with patch("stripe.PaymentIntent.create") as mock_create:
        resp = client.post(f"/sessions/{session.id}/end", headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 200
    assert resp.json()["billing"] is None
    mock_create.assert_not_called()
    db.expire(u)
    db.refresh(u)
    assert u.billed_seconds == 0


def test_stripe_failure_does_not_block_session_end(client, db, paid_host):
    """A Stripe charge failure is swallowed: the session still ends, a failed
    BillingEvent is recorded, and billed_seconds is NOT advanced (retried later)."""
    host, token = paid_host
    host.trial_seconds_used = settings.free_trial_limit_seconds + 720
    db.commit()
    session = _active_session(db, host, created_offset_s=0, heartbeat_offset_s=0)

    with patch("stripe.PaymentIntent.create", side_effect=stripe.CardError("declined", "card", "card_declined")):
        resp = client.post(f"/sessions/{session.id}/end", headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 200
    assert resp.json()["status"] == "ended"
    assert resp.json()["billing"] is None

    db.expire(host)
    db.refresh(host)
    assert host.billed_seconds == 0  # not advanced — will retry next session

    events = db.query(BillingEvent).filter(BillingEvent.host_user_id == host.id).all()
    assert len(events) == 1
    assert events[0].status == "failed"
    assert events[0].stripe_payment_intent_id is None


def test_guest_is_never_billed(client, db, paid_host):
    """A guest joining a billed session accrues no trial time and is never charged.

    The guest ends the host's session; only the host (who has the overage and the
    card) is charged — the guest has no billable seconds and no Stripe method."""
    host, host_token = paid_host
    host.trial_seconds_used = settings.free_trial_limit_seconds + 720
    db.commit()

    guest = User(phone_number="+15148880099", trial_seconds_used=0, billed_seconds=0)
    db.add(guest)
    db.commit()
    db.refresh(guest)

    session = _active_session(db, host, created_offset_s=0, heartbeat_offset_s=0)

    with patch("stripe.PaymentIntent.create", return_value=_mock_intent()) as mock_create:
        # Host ends the session (only the host may end it).
        client.post(f"/sessions/{session.id}/end", headers={"Authorization": f"Bearer {host_token}"})

    # Only ONE charge was made — for the host — and it targeted the host's method.
    assert mock_create.call_count == 1
    assert mock_create.call_args.kwargs["customer"] == "cus_paid1"

    # The guest was never billed and accumulated no billable seconds.
    db.expire(guest)
    db.refresh(guest)
    assert guest.trial_seconds_used == 0
    assert guest.billed_seconds == 0
    guest_events = db.query(BillingEvent).filter(BillingEvent.host_user_id == guest.id).all()
    assert guest_events == []


def test_sub_cent_overage_not_charged(client, db, paid_host):
    """An overage that prorates to less than 1¢ is not charged and carries forward."""
    host, token = paid_host
    # 5 s at $5/hr ≈ 0.69¢ → rounds to 1¢ actually; use 3 s → 0.417¢ → 0¢.
    host.trial_seconds_used = settings.free_trial_limit_seconds + 3
    db.commit()
    session = _active_session(db, host, created_offset_s=0, heartbeat_offset_s=0)

    with patch("stripe.PaymentIntent.create") as mock_create:
        resp = client.post(f"/sessions/{session.id}/end", headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 200
    assert resp.json()["billing"] is None
    mock_create.assert_not_called()
    db.expire(host)
    db.refresh(host)
    assert host.billed_seconds == 0  # carried forward
