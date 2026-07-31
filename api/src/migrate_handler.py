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


def handler(event, context):
    """Run `alembic upgrade head`, or a named maintenance action.

    event = {"action": "reset_trial", "email": "..."} clears metered time for one account.
    Any other event runs migrations.
    """
    action = (event or {}).get("action")
    if action == "reset_trial":
        result = _reset_trial(event["email"])
        logger.info("reset_trial: %s", result)
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
