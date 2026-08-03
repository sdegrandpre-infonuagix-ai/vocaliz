"""Recording broadcasts, and invoicing advertisers for them.

The table exists because ads.number_of_broadcasts_left destroyed information by consuming it:
a counter that only decrements cannot say how many broadcasts happened, when, or where — so
nothing could invoice an advertiser or answer one who disputed a charge.
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.exc import IntegrityError

from src.config import settings
from src.models.ad import Ad
from src.models.ad_broadcast import AdBroadcast
from src.models.advertiser import Advertiser
from src.models.session import SessionModel
from src.models.user import User
from src.services import ad_billing_service


@pytest.fixture
def advertiser(db):
    row = Advertiser(company="Café Rivard", email="ads@caferivard.example")
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@pytest.fixture
def ad(db, advertiser):
    row = Ad(
        advertiser_id=advertiser.advertiser_id,
        sales_pitch="Come for the coffee.",
        number_of_broadcasts_left=3,
        topic="coffee",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@pytest.fixture
def salon(db):
    user = User(email="adhost@example.com")
    db.add(user)
    db.commit()
    db.refresh(user)
    s = SessionModel(
        host_user_id=user.id,
        livekit_room_name="salon-ads",
        source_type="url",
        source_content="c",
        status="active",
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


# ─── Recording ────────────────────────────────────────────────────────────────

def test_a_broadcast_is_recorded_with_its_salon(db, ad, salon):
    row = ad_billing_service.record_broadcast(db, ad=ad, session=salon)
    assert row is not None
    assert row.session_id == salon.id
    assert row.salon_name == "salon-ads"
    assert row.advertiser_id == ad.advertiser_id


def test_the_price_is_copied_not_referenced(db, ad, salon):
    """Rates change. An invoice has to charge what was agreed when the ad ran, so reading the
    setting at billing time would silently reprice history."""
    original = settings.ad_broadcast_rate_cents
    settings.ad_broadcast_rate_cents = 40
    try:
        row = ad_billing_service.record_broadcast(db, ad=ad, session=salon)
    finally:
        settings.ad_broadcast_rate_cents = original

    db.expire_all()
    assert db.get(AdBroadcast, row.id).amount_cents == 40, "the rate at the time, not now"


def test_recording_spends_one_of_the_allowance(db, ad, salon):
    ad_billing_service.record_broadcast(db, ad=ad, session=salon)
    db.expire_all()
    assert db.get(Ad, ad.ad_id).number_of_broadcasts_left == 2


def test_an_exhausted_ad_is_not_broadcast(db, ad, salon):
    """Checked here rather than trusted to the caller: the counter and the record have to move
    together, or an advertiser is billed for a broadcast they did not buy."""
    ad.number_of_broadcasts_left = 0
    db.commit()
    assert ad_billing_service.record_broadcast(db, ad=ad, session=salon) is None
    assert db.query(AdBroadcast).count() == 0


def test_recording_makes_no_stripe_call(db, ad, salon):
    """This runs while somebody is waiting to hear a sentence. A payment processor has no
    business on that path."""
    with patch("src.services.ad_billing_service.stripe") as stripe_mock:
        ad_billing_service.record_broadcast(db, ad=ad, session=salon)
    assert not stripe_mock.method_calls


def test_a_broadcast_survives_its_salon(db, ad, salon):
    """A salon is ephemeral; the billing record is not. The name is kept as text so an invoice
    line can still say where the ad played."""
    row = ad_billing_service.record_broadcast(db, ad=ad, session=salon)
    db.delete(salon)
    db.commit()
    db.expire_all()
    kept = db.get(AdBroadcast, row.id)
    assert kept is not None
    assert kept.session_id is None
    assert kept.salon_name == "salon-ads"


def test_a_broadcast_ad_cannot_be_deleted(db, ad, salon):
    """These rows are the evidence an advertiser could dispute. A cascade would make history
    depend on whether anyone had tidied up."""
    ad_billing_service.record_broadcast(db, ad=ad, session=salon)
    db.delete(ad)
    with pytest.raises(IntegrityError):
        db.commit()


# ─── What the schema forbids ──────────────────────────────────────────────────

def test_a_negative_amount_is_refused(db, ad):
    """A free broadcast is a real case — a promotion, a make-good. A negative one is a credit,
    and credits do not belong in a table of things that happened."""
    db.add(
        AdBroadcast(ad_id=ad.ad_id, advertiser_id=ad.advertiser_id, amount_cents=-1)
    )
    with pytest.raises(IntegrityError):
        db.commit()


def test_an_invoice_item_without_a_timestamp_is_refused(db, ad):
    """Such a row could not be reconciled against Stripe."""
    db.add(
        AdBroadcast(
            ad_id=ad.ad_id,
            advertiser_id=ad.advertiser_id,
            amount_cents=25,
            stripe_invoice_item_id="ii_x",
            invoiced_at=None,
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()


def test_a_timestamp_without_an_invoice_item_is_refused(db, ad):
    """Such a row claims to have been billed but names no charge."""
    db.add(
        AdBroadcast(
            ad_id=ad.ad_id,
            advertiser_id=ad.advertiser_id,
            amount_cents=25,
            invoiced_at=datetime.now(tz=timezone.utc),
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()


# ─── Invoicing ────────────────────────────────────────────────────────────────

def _stripe_double():
    """A Stripe module that accepts everything and hands back distinguishable ids."""
    mock = MagicMock()
    mock.Customer.create.return_value = MagicMock(id="cus_1")
    mock.InvoiceItem.create.side_effect = [
        MagicMock(id=f"ii_{n}") for n in range(1, 50)
    ]
    mock.Invoice.create.return_value = MagicMock(id="in_1")
    mock.StripeError = Exception
    return mock


def test_each_broadcast_becomes_its_own_invoice_line(db, ad, salon, advertiser):
    """An advertiser disputing a charge should see what they are charged for without asking."""
    for _ in range(3):
        ad_billing_service.record_broadcast(db, ad=ad, session=salon)

    with patch("src.services.ad_billing_service.stripe", _stripe_double()) as stripe_mock:
        result = ad_billing_service.invoice_advertiser(db, advertiser)

    assert result["status"] == "invoiced"
    assert result["broadcasts"] == 3
    assert stripe_mock.InvoiceItem.create.call_count == 3
    # One invoice, not three charges: Stripe's per-transaction fee would exceed the amount.
    assert stripe_mock.Invoice.create.call_count == 1


def test_an_invoice_line_names_the_salon_and_the_date(db, ad, salon, advertiser):
    ad_billing_service.record_broadcast(db, ad=ad, session=salon)
    with patch("src.services.ad_billing_service.stripe", _stripe_double()) as stripe_mock:
        ad_billing_service.invoice_advertiser(db, advertiser)
    description = stripe_mock.InvoiceItem.create.call_args.kwargs["description"]
    assert "salon-ads" in description


def test_invoicing_is_idempotent(db, ad, salon, advertiser):
    """A row is marked the moment its line exists, so a second run finds nothing to bill."""
    ad_billing_service.record_broadcast(db, ad=ad, session=salon)

    with patch("src.services.ad_billing_service.stripe", _stripe_double()):
        first = ad_billing_service.invoice_advertiser(db, advertiser)
    with patch("src.services.ad_billing_service.stripe", _stripe_double()) as second_stripe:
        second = ad_billing_service.invoice_advertiser(db, advertiser)

    assert first["broadcasts"] == 1
    assert second["status"] == "nothing_to_invoice"
    assert second_stripe.InvoiceItem.create.call_count == 0


def test_a_failure_partway_leaves_the_rest_for_the_next_run(db, ad, salon, advertiser):
    """No double billing and no gap: what was marked is billed, what was not is picked up."""
    ad.number_of_broadcasts_left = 3
    db.commit()
    for _ in range(3):
        ad_billing_service.record_broadcast(db, ad=ad, session=salon)

    failing = _stripe_double()
    failing.InvoiceItem.create.side_effect = [MagicMock(id="ii_1"), Exception("boom")]
    with patch("src.services.ad_billing_service.stripe", failing):
        ad_billing_service.invoice_advertiser(db, advertiser)

    db.expire_all()
    remaining = (
        db.query(AdBroadcast)
        .filter(AdBroadcast.stripe_invoice_item_id.is_(None))
        .count()
    )
    assert remaining == 2, "the two that never got a line are still waiting"


def test_a_free_broadcast_is_recorded_but_never_sent_to_stripe(db, ad, salon, advertiser):
    """A line worth nothing costs an API call and clutters an invoice."""
    original = settings.ad_broadcast_rate_cents
    settings.ad_broadcast_rate_cents = 0
    try:
        ad_billing_service.record_broadcast(db, ad=ad, session=salon)
    finally:
        settings.ad_broadcast_rate_cents = original

    assert db.query(AdBroadcast).count() == 1
    with patch("src.services.ad_billing_service.stripe", _stripe_double()) as stripe_mock:
        result = ad_billing_service.invoice_advertiser(db, advertiser)
    assert result["status"] == "nothing_to_invoice"
    assert stripe_mock.InvoiceItem.create.call_count == 0


def test_a_customer_is_created_only_when_there_is_something_to_bill(db, advertiser):
    """An advertiser who never runs an ad leaves no trace in Stripe."""
    with patch("src.services.ad_billing_service.stripe", _stripe_double()) as stripe_mock:
        ad_billing_service.invoice_advertiser(db, advertiser)
    assert stripe_mock.Customer.create.call_count == 0
    assert advertiser.stripe_customer_id is None


def test_the_customer_is_reused_on_the_second_invoice(db, ad, salon, advertiser):
    ad.number_of_broadcasts_left = 2
    db.commit()
    ad_billing_service.record_broadcast(db, ad=ad, session=salon)
    with patch("src.services.ad_billing_service.stripe", _stripe_double()):
        ad_billing_service.invoice_advertiser(db, advertiser)

    ad_billing_service.record_broadcast(db, ad=ad, session=salon)
    with patch("src.services.ad_billing_service.stripe", _stripe_double()) as second:
        ad_billing_service.invoice_advertiser(db, advertiser)
    assert second.Customer.create.call_count == 0


def test_one_advertiser_failing_does_not_stop_the_others(db, ad, salon, advertiser):
    """A run that aborted partway would skip the same remainder on every pass, and nobody
    would notice until an advertiser was months behind."""
    other = Advertiser(company="Second", email="two@example.com")
    db.add(other)
    db.commit()
    db.refresh(other)
    other_ad = Ad(
        advertiser_id=other.advertiser_id, sales_pitch="Second pitch.", number_of_broadcasts_left=1
    )
    db.add(other_ad)
    db.commit()
    db.refresh(other_ad)

    ad_billing_service.record_broadcast(db, ad=ad, session=salon)
    ad_billing_service.record_broadcast(db, ad=other_ad, session=salon)

    with patch("src.services.ad_billing_service.stripe", _stripe_double()):
        with patch.object(
            ad_billing_service,
            "invoice_advertiser",
            side_effect=[Exception("boom"), {"status": "invoiced", "broadcasts": 1, "amountCents": 25}],
        ):
            result = ad_billing_service.invoice_all(db)

    assert result["advertisers"] == 2
    assert {r["status"] for r in result["results"]} == {"error", "invoiced"}


def test_invoice_all_reports_what_it_collected(db, ad, salon, advertiser):
    ad_billing_service.record_broadcast(db, ad=ad, session=salon)
    with patch("src.services.ad_billing_service.stripe", _stripe_double()):
        result = ad_billing_service.invoice_all(db)
    assert result["advertisers"] == 1
    assert result["amountCents"] == settings.ad_broadcast_rate_cents


def test_the_handler_action_invoices_and_reports(db, ad, salon, advertiser):
    """EventBridge invokes this daily; the reported total is how anyone knows it collected."""
    from src import migrate_handler

    ad_billing_service.record_broadcast(db, ad=ad, session=salon)

    with patch("src.services.ad_billing_service.stripe", _stripe_double()), \
         patch("src.database.SessionLocal", return_value=db), patch.object(db, "close"):
        result = migrate_handler.handler({"action": "invoice_advertisers"}, None)

    assert result["advertisers"] == 1
    assert result["amountCents"] == settings.ad_broadcast_rate_cents


# ─── Reserved is not delivered ────────────────────────────────────────────────

def test_a_reservation_costs_the_advertiser_nothing(db, ad, salon):
    """The salon opens, the ad is set aside, and then nobody hears it — the host closed their tab
    before the greeting ended. Charging for that is the one outcome this must not produce."""
    from src.services import ad_auction_service

    ad.bid_cents = 500
    db.commit()
    row = ad_auction_service.broadcast_winner(db, session=salon, salon_topics=[""])
    assert row is not None
    assert row.delivered_at is None

    db.expire_all()
    assert db.get(Ad, ad.ad_id).number_of_broadcasts_left == 3, "no allowance spent"

    advertiser_row = db.get(Advertiser, ad.advertiser_id)
    with patch("src.services.ad_billing_service.stripe", _stripe_double()) as stripe_mock:
        result = ad_billing_service.invoice_advertiser(db, advertiser_row)
    assert result["status"] == "nothing_to_invoice"
    assert stripe_mock.InvoiceItem.create.call_count == 0


def test_delivery_is_what_spends_and_bills(db, ad, salon):
    from src.services import ad_auction_service

    ad.bid_cents = 500
    db.commit()
    row = ad_auction_service.broadcast_winner(db, session=salon, salon_topics=[""])
    assert ad_auction_service.mark_delivered(db, row)

    db.expire_all()
    assert db.get(Ad, ad.ad_id).number_of_broadcasts_left == 2
    assert db.get(AdBroadcast, row.id).delivered_at is not None

    advertiser_row = db.get(Advertiser, ad.advertiser_id)
    with patch("src.services.ad_billing_service.stripe", _stripe_double()):
        result = ad_billing_service.invoice_advertiser(db, advertiser_row)
    assert result["broadcasts"] == 1


def test_confirming_twice_spends_once(db, ad, salon):
    """The agent may retry, and a retry must not cost two of a purchase."""
    from src.services import ad_auction_service

    ad.bid_cents = 500
    db.commit()
    row = ad_auction_service.broadcast_winner(db, session=salon, salon_topics=[""])
    ad_auction_service.mark_delivered(db, row)
    ad_auction_service.mark_delivered(db, row)

    db.expire_all()
    assert db.get(Ad, ad.ad_id).number_of_broadcasts_left == 2


def test_the_schema_refuses_a_charge_for_something_unspoken(db, ad):
    """The guarantee lives in the database, not in a query somebody has to write correctly."""
    db.add(
        AdBroadcast(
            ad_id=ad.ad_id,
            advertiser_id=ad.advertiser_id,
            amount_cents=25,
            delivered_at=None,
            stripe_invoice_item_id="ii_x",
            invoiced_at=datetime.now(tz=timezone.utc),
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()
