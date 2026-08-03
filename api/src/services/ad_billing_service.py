"""Recording broadcasts, and invoicing advertisers for them.

Two halves that deliberately do not touch each other.

Recording happens in the conversation. It must be fast, it must never fail an ad that was
about to be spoken, and it must not talk to Stripe — a network call on that path would put a
payment processor between a participant and a sentence.

Invoicing happens on a schedule, over rows that already exist. Batched, because Stripe takes
roughly 2.9% plus thirty cents per transaction: charging a few cents per broadcast would cost
more in fees than it collects. One invoice per advertiser per run, with a line per broadcast.
"""
import logging
from datetime import datetime, timezone

import stripe
from sqlalchemy.orm import Session as DbSession

from src.config import settings
from src.models.ad import Ad
from src.models.ad_broadcast import AdBroadcast
from src.models.advertiser import Advertiser

logger = logging.getLogger(__name__)


def record_broadcast(db: DbSession, *, ad: Ad, session=None) -> AdBroadcast | None:
    """Note that an ad was spoken, and spend one of its allowance.

    Returns None when the ad had nothing left. That is the caller's signal not to speak it —
    checked here rather than trusted to the caller, because the counter and the record have to
    move together or an advertiser is billed for a broadcast they did not buy.

    The price is copied onto the row, not referenced. Rates change, and an invoice has to
    charge what was agreed when the ad ran.

    No Stripe call. This runs while somebody is waiting to hear a sentence.
    """
    if ad.number_of_broadcasts_left <= 0:
        return None

    try:
        row = AdBroadcast(
            ad_id=ad.ad_id,
            advertiser_id=ad.advertiser_id,
            session_id=getattr(session, "id", None),
            salon_name=getattr(session, "livekit_room_name", "") or "",
            amount_cents=settings.ad_broadcast_rate_cents,
            currency=settings.billing_currency,
            broadcast_at=datetime.now(tz=timezone.utc),
            # Delivered on the spot: this path records an ad at the moment it is spoken, unlike
            # the auction, which reserves one when the salon opens.
            delivered_at=datetime.now(tz=timezone.utc),
        )
        db.add(row)
        # Decremented in the same transaction as the record. Two statements, one commit: an
        # allowance spent without a record would be revenue lost, and a record without a
        # decrement would let one purchase play forever.
        ad.number_of_broadcasts_left = ad.number_of_broadcasts_left - 1
        db.commit()
        db.refresh(row)
        return row
    except Exception:  # noqa: BLE001
        db.rollback()
        logger.warning("Could not record a broadcast of ad %s", ad.ad_id, exc_info=True)
        return None


def _stripe_customer(advertiser: Advertiser, db: DbSession) -> str:
    """The advertiser's Stripe customer, created on first use.

    Same pattern as hosts: nothing is created until there is something to bill, so an
    advertiser who never runs an ad leaves no trace in Stripe.
    """
    if advertiser.stripe_customer_id:
        return advertiser.stripe_customer_id

    customer = stripe.Customer.create(
        email=advertiser.email,
        name=advertiser.company,
        metadata={"advertiser_id": str(advertiser.advertiser_id)},
    )
    advertiser.stripe_customer_id = customer.id
    db.commit()
    return customer.id


def invoice_advertiser(db: DbSession, advertiser: Advertiser) -> dict:
    """Put one advertiser's uninvoiced broadcasts on a Stripe invoice.

    Each broadcast becomes its own invoice line, naming the salon and the date. An advertiser
    disputing a charge should be able to see what they are being charged for without asking.

    Marked one row at a time, right after its line is created. A run interrupted halfway
    therefore leaves some rows invoiced and some not, and the next run picks up exactly what
    is left — no double billing, no gap. Marking them all at the end would risk charging for
    lines that were never created, and marking them first would risk lines nobody is charged
    for.

    Zero-amount broadcasts are recorded but never sent to Stripe: a line worth nothing costs
    an API call and clutters an invoice.
    """
    pending = (
        db.query(AdBroadcast)
        .filter(
            AdBroadcast.advertiser_id == advertiser.advertiser_id,
            AdBroadcast.stripe_invoice_item_id.is_(None),
            AdBroadcast.amount_cents > 0,
            # Reserved but never spoken is not billable. The database refuses such a charge
            # anyway; filtering here is what stops the run from trying and failing.
            AdBroadcast.delivered_at.isnot(None),
        )
        .order_by(AdBroadcast.broadcast_at)
        .all()
    )
    if not pending:
        return {"status": "nothing_to_invoice", "broadcasts": 0, "amountCents": 0}

    stripe.api_key = settings.stripe_secret_key

    try:
        customer_id = _stripe_customer(advertiser, db)
    except stripe.StripeError as exc:
        logger.error("Could not create a Stripe customer for %s: %s", advertiser.email, exc)
        return {"status": "customer_failed", "broadcasts": 0, "amountCents": 0}

    now = datetime.now(tz=timezone.utc)
    billed = 0
    total = 0

    for row in pending:
        when = row.broadcast_at.date().isoformat() if row.broadcast_at else "unknown date"
        description = f"Vocaliz broadcast — {row.salon_name or 'a Salon'} — {when}"
        try:
            item = stripe.InvoiceItem.create(
                customer=customer_id,
                amount=row.amount_cents,
                currency=row.currency,
                description=description,
                metadata={"ad_id": str(row.ad_id), "broadcast_id": str(row.id)},
            )
        except stripe.StripeError as exc:
            # Stop rather than skip. Continuing past a failure would produce an invoice
            # missing arbitrary lines, and the rows left unmarked are picked up next run.
            logger.error("Invoice item failed for broadcast %s: %s", row.id, exc)
            break

        row.stripe_invoice_item_id = item.id
        row.invoiced_at = now
        db.commit()
        billed += 1
        total += row.amount_cents

    if not billed:
        return {"status": "no_items", "broadcasts": 0, "amountCents": 0}

    try:
        invoice = stripe.Invoice.create(
            customer=customer_id,
            auto_advance=True,
            collection_method="charge_automatically",
            description="Vocaliz advertising",
        )
        stripe.Invoice.finalize_invoice(invoice.id)
    except stripe.StripeError as exc:
        # The items survive on the customer as pending charges, so nothing is lost: the next
        # run creates the invoice. Returning the failure keeps that visible rather than
        # reporting a success that did not collect anything.
        logger.error("Could not finalise the invoice for %s: %s", advertiser.email, exc)
        return {
            "status": "invoice_failed",
            "broadcasts": billed,
            "amountCents": total,
        }

    logger.info(
        "Invoiced %s for %d broadcast(s), %d cents", advertiser.email, billed, total
    )
    return {
        "status": "invoiced",
        "broadcasts": billed,
        "amountCents": total,
        "invoiceId": invoice.id,
    }


def invoice_all(db: DbSession) -> dict:
    """Invoice every advertiser with uninvoiced broadcasts.

    One advertiser failing does not stop the others: a run that aborted partway would skip the
    same remainder on every pass, and nobody would notice until an advertiser was months
    behind.
    """
    advertiser_ids = [
        row[0]
        for row in db.query(AdBroadcast.advertiser_id)
        .filter(
            AdBroadcast.stripe_invoice_item_id.is_(None),
            AdBroadcast.amount_cents > 0,
            AdBroadcast.delivered_at.isnot(None),
        )
        .distinct()
        .all()
    ]

    results = []
    for advertiser_id in advertiser_ids:
        advertiser = db.get(Advertiser, advertiser_id)
        if advertiser is None:
            continue
        try:
            outcome = invoice_advertiser(db, advertiser)
        except Exception:  # noqa: BLE001
            db.rollback()
            logger.warning("Invoicing failed for %s", advertiser_id, exc_info=True)
            outcome = {"status": "error", "broadcasts": 0, "amountCents": 0}
        results.append({"advertiserId": str(advertiser_id), **outcome})

    return {
        "advertisers": len(results),
        "amountCents": sum(r["amountCents"] for r in results),
        "results": results,
    }
