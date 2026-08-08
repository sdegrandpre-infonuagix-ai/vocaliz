"""Every key Vocaliz writes onto a Stripe object carries the Vocaliz namespace.

Metadata on a Stripe Customer, PaymentIntent or InvoiceItem is a flat key space shared
with Stripe and with any other integration connected to the account. An unprefixed
`user_id` is a collision waiting for a second writer, and the loser of that race is
whichever wrote first — silently, on an object that bills real money.

Nothing asserted these keys before, which is exactly how a namespace drifts: a new call
site is written by hand, the prefix is forgotten, the write succeeds, and the key is
simply wrong until somebody reconciles a Stripe export by hand.

The call sites are asserted rather than only the helper. A helper nobody calls protects
nothing.
"""
import uuid
from unittest.mock import patch

import pytest

from src.services.stripe_metadata import NAMESPACE, namespaced


def test_every_key_is_prefixed_and_every_value_is_a_string():
    out = namespaced(user_id=uuid.UUID(int=1), billable_seconds=720)

    assert out == {
        "vocaliz_user_id": "00000000-0000-0000-0000-000000000001",
        "vocaliz_billable_seconds": "720",
    }
    assert all(isinstance(v, str) for v in out.values())


def test_none_becomes_the_empty_string_rather_than_reaching_stripe():
    """Stripe rejects a null metadata value. The common accident is an optional foreign
    key that happens to be absent — a charge settling metered time with no Salon left to
    point at — and refusing the whole charge over it would be the wrong trade."""
    assert namespaced(salon_id=None) == {"vocaliz_salon_id": ""}


def test_the_namespace_is_the_company_not_the_entity():
    """It was `salon_` after the project this code came from. That word now names the
    conversation being billed for, so `salon_user_id` read as "the user of a Salon" and
    the Salon's own key would have had to be `salon_salon_id`."""
    assert NAMESPACE == "vocaliz"


def test_the_customer_created_for_a_host_is_namespaced(db):
    from src.models.user import User
    from src.services.stripe_service import attach_payment_method

    user = User(email="host@example.com", stripe_customer_id=None)
    db.add(user)
    db.commit()

    with (
        patch("stripe.Customer.create") as create,
        patch("stripe.PaymentMethod.attach"),
    ):
        create.return_value = type("C", (), {"id": "cus_test"})()
        attach_payment_method(user, "pm_test", db)

    assert create.call_args.kwargs["metadata"] == {"vocaliz_user_id": str(user.id)}


def test_the_customer_created_for_an_advertiser_is_namespaced(db):
    from src.models.advertiser import Advertiser
    from src.services.ad_billing_service import _stripe_customer

    advertiser = Advertiser(email="ads@example.com", company="Acme", stripe_customer_id=None)
    db.add(advertiser)
    db.commit()

    with patch("stripe.Customer.create") as create:
        create.return_value = type("C", (), {"id": "cus_adv"})()
        _stripe_customer(advertiser, db)

    assert create.call_args.kwargs["metadata"] == {
        "vocaliz_advertiser_id": str(advertiser.advertiser_id)
    }


@pytest.mark.parametrize(
    "module, attribute",
    [
        ("src.services.stripe_service", "namespaced"),
        ("src.services.ad_billing_service", "namespaced"),
    ],
)
def test_both_billing_modules_go_through_the_helper(module, attribute):
    """A guard against the shape of the mistake rather than one instance of it: a module
    that stopped importing the helper has started writing raw keys somewhere."""
    import importlib

    assert hasattr(importlib.import_module(module), attribute)
