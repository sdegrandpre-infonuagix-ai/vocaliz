"""Stripe billing service — customer creation and payment method attachment."""
import logging

import stripe

from src.config import settings
from src.models.billing_event import BillingEvent  # noqa: F401 — ensure table is registered

logger = logging.getLogger("salon.stripe")


def attach_payment_method(user, payment_method_id: str, db) -> None:
    """Attach a Stripe PaymentMethod to the user's account.

    Creates a Stripe Customer on first call, then attaches the PaymentMethod.
    Persists stripe_customer_id and stripe_payment_method_id to the DB.
    Raises stripe.StripeError on any Stripe API failure.
    """
    stripe.api_key = settings.stripe_secret_key

    customer_id = user.stripe_customer_id
    if not customer_id:
        customer = stripe.Customer.create(
            email=user.email,
            metadata={"salon_user_id": str(user.id)},
        )
        customer_id = customer.id
        logger.info("Stripe customer created: %s for user %s", customer_id, user.id)

    stripe.PaymentMethod.attach(payment_method_id, customer=customer_id)
    logger.info("Payment method %s attached to customer %s", payment_method_id, customer_id)

    user.stripe_customer_id = customer_id
    user.stripe_payment_method_id = payment_method_id
    db.commit()


def _billable_seconds(host) -> int:
    """Host seconds beyond the free trial that have not yet been billed."""
    over = max(0, host.trial_seconds_used - settings.free_trial_limit_seconds)
    return max(0, over - host.billed_seconds)


def _amount_cents(seconds: int) -> int:
    """Prorate seconds to cents at the configured hourly rate (rounded to nearest cent)."""
    return round(seconds * settings.hourly_rate_cents / 3600)


def bill_host_for_usage(host, session, db):
    """Charge the host for metered time beyond their free trial hour.

    Called when a session ends. Computes host seconds past the free trial that
    have not yet been billed, prorates them to the hourly rate ($5/hr per second),
    and charges the saved Stripe payment method off-session.

    Guests are never billed — only the session host accumulates billable seconds.

    Returns a dict describing the charge (or None if nothing was charged, e.g.
    still within the free trial, no payment method, or the amount rounds to < 1¢).
    A BillingEvent audit row is written for every actual charge attempt, whether
    it succeeds or fails. Stripe errors are recorded and re-raised swallowing is
    left to the caller — this function never advances billed_seconds on failure,
    so an unbilled span is retried on the next session.
    """
    seconds = _billable_seconds(host)
    if seconds <= 0:
        return None
    if not host.stripe_payment_method_id or not host.stripe_customer_id:
        # Host crossed into paid usage but never added a card (the crossing
        # session was not gated). Leave billed_seconds untouched so this span is
        # captured on a later session once a payment method exists.
        logger.info("Host %s owes %s billable seconds but has no payment method", host.id, seconds)
        return None

    amount = _amount_cents(seconds)
    if amount < 1:
        # Below one cent — carry forward without advancing billed_seconds.
        return None

    stripe.api_key = settings.stripe_secret_key
    total_over = max(0, host.trial_seconds_used - settings.free_trial_limit_seconds)

    try:
        intent = stripe.PaymentIntent.create(
            amount=amount,
            currency=settings.billing_currency,
            customer=host.stripe_customer_id,
            payment_method=host.stripe_payment_method_id,
            off_session=True,
            confirm=True,
            metadata={
                "salon_user_id": str(host.id),
                "salon_session_id": str(session.id) if session is not None else "",
                "billable_seconds": str(seconds),
            },
        )
    except stripe.StripeError as exc:
        message = getattr(exc, "user_message", None) or str(exc)
        logger.warning("Billing failed for host %s: %s", host.id, message)
        db.add(
            BillingEvent(
                host_user_id=host.id,
                session_id=session.id if session is not None else None,
                billable_seconds=seconds,
                amount_cents=amount,
                currency=settings.billing_currency,
                stripe_payment_intent_id=None,
                status="failed",
            )
        )
        db.commit()
        raise

    # Charge succeeded — advance billed_seconds so this span is never re-billed.
    host.billed_seconds = total_over
    db.add(
        BillingEvent(
            host_user_id=host.id,
            session_id=session.id if session is not None else None,
            billable_seconds=seconds,
            amount_cents=amount,
            currency=settings.billing_currency,
            stripe_payment_intent_id=getattr(intent, "id", None),
            status="succeeded",
        )
    )
    db.commit()
    logger.info("Billed host %s: %s¢ for %s s (intent %s)", host.id, amount, seconds, getattr(intent, "id", None))

    return {
        "billedSeconds": seconds,
        "amountCents": amount,
        "currency": settings.billing_currency,
        "paymentIntentId": getattr(intent, "id", None),
        "status": "succeeded",
    }
