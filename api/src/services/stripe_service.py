"""Stripe billing service — customer creation and payment method attachment."""
import logging

import stripe

from src.config import settings

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
            phone=user.phone_number,
            metadata={"salon_user_id": str(user.id)},
        )
        customer_id = customer.id
        logger.info("Stripe customer created: %s for user %s", customer_id, user.id)

    stripe.PaymentMethod.attach(payment_method_id, customer=customer_id)
    logger.info("Payment method %s attached to customer %s", payment_method_id, customer_id)

    user.stripe_customer_id = customer_id
    user.stripe_payment_method_id = payment_method_id
    db.commit()
