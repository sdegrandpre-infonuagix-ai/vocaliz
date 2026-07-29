"""Tests for Story 4.3 — Ajout de Méthode de Paiement Stripe."""
from unittest.mock import MagicMock, patch

import pytest
import stripe

from src.models.session import SessionModel
from src.models.user import User
from src.services.jwt_service import issue_token


# ─── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def host(db):
    u = User(phone_number="+15148880020")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u, issue_token(str(u.id))


def _mock_stripe_ok(customer_id="cus_test123", pm_attached=True):
    """Return mock objects for stripe.Customer.create and PaymentMethod.attach."""
    mock_customer = MagicMock()
    mock_customer.id = customer_id
    mock_pm = MagicMock()
    return mock_customer, mock_pm


# ─── POST /me/payment-method ─────────────────────────────────────────────────

def test_add_payment_method_returns_200(client, db, host):
    """Valid payment method ID creates a Stripe customer and returns 200."""
    host_user, token = host
    mock_customer, mock_pm = _mock_stripe_ok()

    with (
        patch("stripe.Customer.create", return_value=mock_customer),
        patch("stripe.PaymentMethod.attach", return_value=mock_pm),
    ):
        resp = client.post(
            "/me/payment-method",
            json={"paymentMethodId": "pm_test_abc123"},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["stripeCustomerId"] == "cus_test123"
    assert body["paymentMethodAdded"] is True


def test_add_payment_method_persists_customer_and_pm_ids(client, db, host):
    """stripe_customer_id and stripe_payment_method_id are saved to the user."""
    host_user, token = host
    mock_customer, mock_pm = _mock_stripe_ok()

    with (
        patch("stripe.Customer.create", return_value=mock_customer),
        patch("stripe.PaymentMethod.attach", return_value=mock_pm),
    ):
        client.post(
            "/me/payment-method",
            json={"paymentMethodId": "pm_test_abc123"},
            headers={"Authorization": f"Bearer {token}"},
        )

    db.expire(host_user)
    db.refresh(host_user)
    assert host_user.stripe_customer_id == "cus_test123"
    assert host_user.stripe_payment_method_id == "pm_test_abc123"


def test_add_payment_method_reuses_existing_customer(client, db, host):
    """If stripe_customer_id already exists, Customer.create is NOT called again."""
    host_user, token = host
    host_user.stripe_customer_id = "cus_existing99"
    db.commit()

    mock_pm = MagicMock()
    with (
        patch("stripe.Customer.create") as mock_create,
        patch("stripe.PaymentMethod.attach", return_value=mock_pm),
    ):
        resp = client.post(
            "/me/payment-method",
            json={"paymentMethodId": "pm_new_xyz"},
            headers={"Authorization": f"Bearer {token}"},
        )
        mock_create.assert_not_called()

    assert resp.status_code == 200
    db.expire(host_user)
    db.refresh(host_user)
    assert host_user.stripe_customer_id == "cus_existing99"
    assert host_user.stripe_payment_method_id == "pm_new_xyz"


def test_add_payment_method_stripe_error_returns_402(client, host):
    """A Stripe API error propagates as 402."""
    _, token = host

    with (
        patch("stripe.Customer.create", side_effect=stripe.InvalidRequestError("bad pm", "paymentMethodId")),
    ):
        resp = client.post(
            "/me/payment-method",
            json={"paymentMethodId": "pm_invalid"},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert resp.status_code == 402


def test_add_payment_method_requires_auth(client):
    """Unauthenticated request is rejected."""
    resp = client.post("/me/payment-method", json={"paymentMethodId": "pm_test"})
    assert resp.status_code == 401


# ─── Session creation gating ─────────────────────────────────────────────────

@pytest.fixture
def exhausted_host(db):
    u = User(phone_number="+15148880021", trial_seconds_used=3600)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u, issue_token(str(u.id))


def test_create_session_blocked_when_trial_exhausted_and_no_payment_method(client, exhausted_host):
    """POST /sessions returns 402 when trial is exhausted and no payment method exists."""
    _, token = exhausted_host

    resp = client.post(
        "/sessions",
        data={"source_url": "https://example.com/article"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 402
    assert "essai gratuite" in resp.json()["detail"].lower() or "paiement" in resp.json()["detail"].lower()


def test_create_session_allowed_when_trial_exhausted_with_payment_method(client, db, exhausted_host):
    """POST /sessions succeeds when trial is exhausted but a payment method exists."""
    host_user, token = exhausted_host
    host_user.stripe_payment_method_id = "pm_existing_method"
    db.commit()

    with (
        patch("src.services.content_service.fetch_url_content", return_value="article content"),
        patch("src.services.livekit_service.new_room_name", return_value="salon-room-99"),
        patch("src.services.livekit_service.create_room"),
        patch("src.services.livekit_service.generate_participant_token", return_value="tok"),
    ):
        resp = client.post(
            "/sessions",
            data={"source_url": "https://example.com/article"},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert resp.status_code == 201


def test_create_session_allowed_when_trial_not_exhausted(client, host):
    """POST /sessions is not gated when trial has remaining time."""
    _, token = host

    with (
        patch("src.services.content_service.fetch_url_content", return_value="content"),
        patch("src.services.livekit_service.new_room_name", return_value="salon-room-100"),
        patch("src.services.livekit_service.create_room"),
        patch("src.services.livekit_service.generate_participant_token", return_value="tok"),
    ):
        resp = client.post(
            "/sessions",
            data={"source_url": "https://example.com/article"},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert resp.status_code == 201
