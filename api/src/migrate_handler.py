"""Lambda entry point that applies Alembic migrations against Aurora.

Invoked manually after a deploy (`aws lambda invoke --function-name salon-api-migrate …`)
rather than on every cold start, so a failed migration cannot take the API down with it.
"""
import logging
import os

from alembic import command
from alembic.config import Config

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def _participant_report(recipient: str) -> dict:
    """Mail the participant table to an administrator.

    Invoked hourly by EventBridge, and by hand when somebody wants it now. The recipient is a
    parameter rather than a constant so a schedule can be pointed elsewhere without a deploy —
    and defaulted, so an invocation that forgets it still reaches the person who asked for it.
    """
    from src.database import SessionLocal
    from src.services import participant_report

    db = SessionLocal()
    try:
        return participant_report.send(db, recipient)
    finally:
        db.close()


def _reset_trial(email: str) -> dict:
    """Clear a test account's metered time.

    Only reachable through lambda:InvokeFunction — this function sits behind IAM and is
    not wired to API Gateway, so it is not an endpoint anyone can call. It exists because
    exhausting the trial is the expected outcome of heavy testing, and the alternative
    was attaching a real payment method to keep testing.
    """
    from src.database import SessionLocal
    from src.models.user import User

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email.strip().lower()).first()
        if user is None:
            return {"status": "not_found", "email": email}
        before = user.trial_seconds_used
        user.trial_seconds_used = 0
        user.billed_seconds = 0
        db.commit()
        return {"status": "ok", "email": email, "secondsCleared": before}
    finally:
        db.close()


def _sweep_expired_sessions() -> dict:
    """Close every session that has outlived its cap, whatever its heartbeats say.

    Runs on a schedule rather than on a request, because the thing it fixes is the absence
    of requests: the per-session cap used to be evaluated only when a heartbeat arrived, so
    a host who closed their laptop left a session active for good — with its telephone code
    reserved and its metered time never settled.

    Carried by this function rather than a new one: it already has database access, already
    sits behind IAM, and adding a Lambda to run twenty lines would be infrastructure in
    search of a home.
    """
    import asyncio

    from src.database import SessionLocal
    from src.services import session_lifecycle

    db = SessionLocal()
    try:
        closed = asyncio.run(session_lifecycle.close_expired_sessions(db))
        return {"status": "ok", "closed": len(closed), "sessionIds": closed}
    finally:
        db.close()


def _invoice_advertisers() -> dict:
    """Put every uninvoiced broadcast on a Stripe invoice.

    On a schedule rather than per broadcast, and that is the whole point. Stripe takes roughly
    2.9% plus thirty cents per transaction, so charging twenty-five cents individually would
    lose money on every single one. One invoice per advertiser per run, with a line per
    broadcast so a dispute can be answered without asking.

    Idempotent by construction: a broadcast is marked the instant its invoice line exists, so a
    run interrupted halfway bills nothing twice and leaves nothing behind.

    Carried here for the same reason as the session sweep — this function already has database
    access and already sits behind IAM.
    """
    from src.database import SessionLocal
    from src.services import ad_billing_service

    db = SessionLocal()
    try:
        return ad_billing_service.invoice_all(db)
    finally:
        db.close()


def _seed_house_ads() -> dict:
    """Create or refresh the platform's own two ads, in French and English.

    Idempotent, and deliberately more than a one-time insert: it also rewrites the copy, so the
    function is the definition of what a house ad says rather than something somebody has to
    remember editing in the database.
    """
    from src.database import SessionLocal
    from src.services import house_ads

    db = SessionLocal()
    try:
        return house_ads.seed(db)
    finally:
        db.close()


def handler(event, context):
    """Run `alembic upgrade head`, or a named maintenance action.

    event = {"action": "participant_report"} mails the participant table; EventBridge does
    this every hour, and the recipient can be overridden with a "recipient" field.
    event = {"action": "reset_trial", "email": "..."} clears metered time for one account.
    event = {"action": "sweep_sessions"} closes sessions past the per-session cap; this is
    what EventBridge invokes every five minutes.
    event = {"action": "invoice_advertisers"} bills every uninvoiced ad broadcast; EventBridge
    invokes it daily.
    Any other event runs migrations.
    """
    action = (event or {}).get("action")
    if action == "participant_report":
        return _participant_report(
            event.get("recipient") or "s.degrandpre@vocaliz.net"
        )
    if action == "reset_trial":
        result = _reset_trial(event["email"])
        logger.info("reset_trial: %s", result)
        return result
    if action == "sweep_sessions":
        result = _sweep_expired_sessions()
        logger.info("sweep_sessions: %s", result)
        return result
    if action == "seed_house_ads":
        result = _seed_house_ads()
        logger.info("seed_house_ads: %s", result)
        return result
    if action == "invoice_advertisers":
        result = _invoice_advertisers()
        logger.info("invoice_advertisers: %s", result)
        return result

    # settings resolves DATABASE_URL from the Aurora secret; import after env is in place.
    from src.config import settings

    target = (event or {}).get("revision", "head")

    config = Config("/var/task/alembic.ini")
    config.set_main_option("script_location", "/var/task/migrations")
    # set_main_option routes through configparser, which treats '%' as interpolation.
    # Aurora passwords are percent-encoded, so '%' must be doubled to survive.
    config.set_main_option("sqlalchemy.url", settings.database_url.replace("%", "%%"))

    logger.info("Applying migrations up to %s", target)
    command.upgrade(config, target)
    logger.info("Migrations applied")

    return {"status": "ok", "revision": target, "region": os.environ.get("AWS_REGION")}
