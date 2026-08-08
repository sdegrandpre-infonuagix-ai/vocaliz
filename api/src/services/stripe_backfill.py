"""Move metadata already written to Stripe into the `vocaliz_` namespace.

Stripe does not migrate metadata. Every Customer, PaymentIntent and InvoiceItem created
before the namespace change still carries the old keys, and will forever. Until they are
moved, reconciling a Stripe export against our tables means reading two key spellings and
knowing which era each object came from — the exact ambiguity the namespace exists to
remove.

Driven from our own tables rather than by paging Stripe. We store the id of every object
we created, so this touches those and nothing else: an account may hold customers created
by another integration, or by hand in the dashboard, and a sweep over `Customer.list()`
would rewrite metadata on objects that are not ours to rewrite.

Renaming a key is two operations in one call. Stripe merges the metadata dict it is given,
and treats the empty string as a delete — so writing the new key and blanking the old one
is a single atomic update per object. There is no window where a reader sees both or
neither.

Idempotent by construction: an object with nothing left to rename costs no API call at
all. Re-running after a partial run resumes exactly where it stopped.

Dry run unless explicitly told otherwise. This writes to live billing records, and the
count it reports on a dry run is the review that should precede that.
"""
import logging

import stripe

from src.config import settings
from src.models.ad_broadcast import AdBroadcast
from src.models.advertiser import Advertiser
from src.models.billing_event import BillingEvent
from src.models.user import User
from src.services.stripe_metadata import NAMESPACE

logger = logging.getLogger(__name__)

# Old key → new key. Written out rather than derived from a prefix rule: a rule would also
# rewrite keys another integration owns, and the two bare keys below show the old scheme
# was never consistent enough to infer.
RENAMES = {
    "salon_user_id": f"{NAMESPACE}_user_id",
    # The Salon was called a session when these were written.
    "salon_session_id": f"{NAMESPACE}_salon_id",
    "salon_id": f"{NAMESPACE}_salon_id",
    "billable_seconds": f"{NAMESPACE}_billable_seconds",
    "advertiser_id": f"{NAMESPACE}_advertiser_id",
    "ad_id": f"{NAMESPACE}_ad_id",
    "broadcast_id": f"{NAMESPACE}_broadcast_id",
}


def _patch_for(metadata) -> dict[str, str]:
    """The single update that renames every old key on one object, or {} if none are left.

    A collision — both spellings present — keeps the value already under the new key and
    drops the old one. The new key is what current code writes, so it is the fresher of
    the two.
    """
    current = dict(metadata or {})
    patch: dict[str, str] = {}
    for old, new in RENAMES.items():
        if old not in current:
            continue
        if new not in current:
            patch[new] = current[old]
        patch[old] = ""      # empty string is how Stripe deletes a metadata key
    return patch


def _ids(db) -> list[tuple[str, str]]:
    """(kind, stripe id) for every object this platform created, oldest table first."""
    found: list[tuple[str, str]] = []
    for value, in db.query(User.stripe_customer_id).filter(User.stripe_customer_id.isnot(None)):
        found.append(("customer", value))
    for value, in db.query(Advertiser.stripe_customer_id).filter(
        Advertiser.stripe_customer_id.isnot(None)
    ):
        found.append(("customer", value))
    for value, in db.query(BillingEvent.stripe_payment_intent_id).filter(
        BillingEvent.stripe_payment_intent_id.isnot(None)
    ):
        found.append(("payment_intent", value))
    for value, in db.query(AdBroadcast.stripe_invoice_item_id).filter(
        AdBroadcast.stripe_invoice_item_id.isnot(None)
    ):
        found.append(("invoice_item", value))
    # One customer can back many rows; one payment intent cannot, but duplicates cost a
    # retrieve either way and the dedupe is free.
    return sorted(set(found))


_API = {
    "customer": (lambda i: stripe.Customer.retrieve(i), lambda i, m: stripe.Customer.modify(i, metadata=m)),
    "payment_intent": (lambda i: stripe.PaymentIntent.retrieve(i), lambda i, m: stripe.PaymentIntent.modify(i, metadata=m)),
    "invoice_item": (lambda i: stripe.InvoiceItem.retrieve(i), lambda i, m: stripe.InvoiceItem.modify(i, metadata=m)),
}


def run(db, *, apply: bool = False) -> dict:
    """Rename legacy metadata keys on every Stripe object this platform created.

    apply=False (the default) reports what would change and calls no write endpoint.

    Failures are counted, not raised. One unretrievable object — deleted in the dashboard,
    or belonging to a key rotated out from under us — must not strand the rest, and the
    run is resumable, so the right response to failures is to fix them and run again.
    """
    stripe.api_key = settings.stripe_secret_key

    targets = _ids(db)
    examined = renamed = skipped = failed = 0
    keys_moved = 0

    for kind, stripe_id in targets:
        retrieve, modify = _API[kind]
        examined += 1
        try:
            obj = retrieve(stripe_id)
        except stripe.StripeError as exc:
            logger.error("Could not read %s %s: %s", kind, stripe_id, exc)
            failed += 1
            continue

        patch = _patch_for(getattr(obj, "metadata", None))
        if not patch:
            skipped += 1
            continue

        # Half the patch is deletions; only the additions are keys gained.
        moved = sum(1 for v in patch.values() if v != "")

        if not apply:
            logger.info("would rename %d key(s) on %s %s", moved, kind, stripe_id)
            renamed += 1
            keys_moved += moved
            continue

        try:
            modify(stripe_id, patch)
        except stripe.StripeError as exc:
            logger.error("Could not update %s %s: %s", kind, stripe_id, exc)
            failed += 1
            continue

        renamed += 1
        keys_moved += moved

    return {
        "status": "applied" if apply else "dry_run",
        "examined": examined,
        "renamed": renamed,
        "alreadyNamespaced": skipped,
        "failed": failed,
        "keysMoved": keys_moved,
    }
