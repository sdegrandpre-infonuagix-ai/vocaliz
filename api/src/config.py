import json
import os
from urllib.parse import quote_plus

from pydantic_settings import BaseSettings, SettingsConfigDict


def _load_app_secret_into_env(secret_arn: str) -> None:
    """Merge a Secrets Manager JSON secret into os.environ before Settings is built.

    Keeps JWT/LiveKit/Stripe credentials out of the CloudFormation template and the
    Lambda console: CDK passes only the secret ARN. Existing env vars win, so a local
    override is still possible.
    """
    import boto3

    client = boto3.client("secretsmanager", region_name=os.environ.get("AWS_REGION"))
    payload = json.loads(client.get_secret_value(SecretId=secret_arn)["SecretString"])

    for key, value in payload.items():
        if value != "" and key not in os.environ:
            os.environ[key] = str(value)


def _database_url_from_secret(secret_arn: str) -> str:
    """Build a Postgres URL from an RDS-managed Secrets Manager secret.

    On Lambda the Aurora credentials are rotated by AWS, so the URL cannot be a static
    env var — it is assembled at cold start from the secret CDK wired to the function.
    """
    import boto3  # imported here so local runs never need AWS credentials

    client = boto3.client("secretsmanager", region_name=os.environ.get("AWS_REGION"))
    secret = json.loads(client.get_secret_value(SecretId=secret_arn)["SecretString"])

    host = secret.get("host") or os.environ["DB_HOST"]
    port = secret.get("port", 5432)
    dbname = secret.get("dbname") or os.environ.get("DB_NAME", "salon")
    user = quote_plus(secret["username"])
    password = quote_plus(secret["password"])

    return f"postgresql://{user}:{password}@{host}:{port}/{dbname}"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql://salon:password@localhost:5432/salon"
    jwt_secret: str  # required — set JWT_SECRET env var; no default to prevent forged-token deploys
    jwt_algorithm: str = "HS256"
    jwt_expiry_hours: int = 24
    aws_region: str = "ca-central-1"
    sns_sender_id: str = "Salon"
    otp_expiry_minutes: int = 10
    otp_max_attempts: int = 5

    # Local device testing only: skip AWS SNS and print the OTP to the API log
    # instead of texting it. Never enable outside development.
    dev_mode: bool = False

    # LiveKit Cloud
    livekit_url: str = "wss://your-project.livekit.cloud"
    livekit_api_key: str = "devkey"
    livekit_api_secret: str  # required — set LIVEKIT_API_SECRET env var

    # Session settings
    livekit_room_max_participants: int = 3  # host + guest + agent
    livekit_room_empty_timeout: int = 300   # 5 min (auto-close if no one joins)

    # Invitation join links sent via SMS to non-registered contacts
    salon_web_base_url: str = "https://salon.app"

    # App installation link sent to anonymous guests after their first session
    salon_install_url: str = "https://salon.app/install"

    # Free trial cap: 1 hour (3 600 s) of cumulative host-role time per account
    free_trial_limit_seconds: int = 3600

    # Stripe billing — set STRIPE_SECRET_KEY in production
    stripe_secret_key: str = "sk_test_placeholder"

    # Post-trial billing: 5 USD per host-hour, prorated to the second.
    # 500 cents / 3600 s → charged per second of host usage beyond the free trial.
    hourly_rate_cents: int = 500
    billing_currency: str = "usd"


# Must run before Settings() so the merged values are picked up as env vars.
_app_secret_arn = os.environ.get("APP_SECRET_ARN")
if _app_secret_arn:
    _load_app_secret_into_env(_app_secret_arn)

settings = Settings()

# On Lambda, Aurora credentials come from the secret CDK attached to the function.
# Locally DB_SECRET_ARN is unset and DATABASE_URL from .env is used as-is.
_db_secret_arn = os.environ.get("DB_SECRET_ARN")
if _db_secret_arn:
    settings.database_url = _database_url_from_secret(_db_secret_arn)
