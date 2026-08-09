"""Stripe billing service — customer creation and payment method attachment."""
import logging

import stripe

from src.config import settings
from src.models.billing_event import BillingEvent  # noqa: F401 — ensure table is registered
from src.services.stripe_metadata import namespaced

logger = logging.getLogger(__name__)


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
            metadata=namespaced(user_id=user.id),
        )
        customer_id = customer.id
        logger.info("Stripe customer created: %s for user %s", customer_id, user.id)

    stripe.PaymentMethod.attach(payment_method_id, customer=customer_id)
    logger.info("Payment method %s attached to customer %s", payment_method_id, customer_id)

    user.stripe_customer_id = customer_id
    user.stripe_payment_method_id = payment_method_id
    db.commit()


# `bill_host_for_usage` and its two helpers lived here until the Epic 8 cutover. They
# charged, at the end of a Salon, for host seconds beyond a free trial hour — a model that
# no longer exists. Consumption is settled as it happens now, against a prepaid balance
# (see `coverage`, `metering` and the heartbeat), so there is nothing left to collect when
# a Salon closes.
#
# Removed rather than left unused, and the difference matters: while it was still wired it
# would have taken the same conversation twice — once from the balance tick by tick, and
# again from a card at the end. Nothing that can double-bill is safe to keep around on the
# grounds that nobody calls it today.
#
# What stays here is what the prepaid model still needs: creating the customer and
# attaching the payment method a top-up will draw on.
