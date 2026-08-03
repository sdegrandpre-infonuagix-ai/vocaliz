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

    # SES sender for OTP emails — must be a verified identity in this region.
    ses_from_address: str = "no-reply@salon.app"

    # SNS sender ID, still used for the guest invitation / install-link SMS.
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

    # App installation link sent to guests without an account after their first session
    salon_install_url: str = "https://salon.app/install"

    # Free trial cap: 1 hour (3 600 s) of cumulative host-role time per account
    free_trial_limit_seconds: int = 3600

    # ── Source summarisation ──────────────────────────────────────────────────
    # A document reached the agent as its first 2 500 characters and no further: a
    # forty-page PDF was accepted, extracted, stored, then silently cut to a page and a
    # half. Summarising once replaces that truncation — the agent gets the substance of
    # the whole document, and the full text stays searchable for detailed questions.
    xai_api_key: str = ""
    # Non-reasoning on purpose. Measured against grok-4.5 on the same document: 1.0 s
    # versus 3.5 s, for a longer and more concrete summary. Condensing text is not a
    # reasoning task, and this call sits in the path of a host waiting to start.
    summary_model: str = "grok-4.20-0309-non-reasoning"
    # Room for the substance of a long document while staying a fraction of what the raw
    # text would cost, since the prompt is processed on every turn of the conversation.
    summary_target_chars: int = 3000

    # Hard cap on a single conversation, independent of the trial above. The trial bounds
    # what one account can spend in total; this bounds what one runaway session can spend
    # in one go — a room left open with the agent talking bills realtime voice by the
    # minute. Ten minutes while the product is being tested.
    max_session_seconds: int = 600

    # Upper bound on the span billed after the last heartbeat when a session ends.
    # Heartbeats arrive every 30 s, so a gap beyond this means the session was already
    # dead — a closed laptop, a killed app, a crashed worker. Without this clamp the
    # whole abandoned period would be billed the moment the session is finally ended.
    metering_grace_seconds: int = 90

    # How precise a recorded position is allowed to be, as an Open Location Code length.
    # The grid is base 20, so each rung is twenty times the last and there is no
    # neighbourhood-sized one: 6 is a borough (5.5 km), 8 is a block (275 m).
    #
    # Six by default. Eight is nearer the literal size of a neighbourhood, but outside a
    # dense city it narrows to a handful of houses — an approximate address rather than
    # an approximate area.
    location_code_length: int = 6

    # The number guests call to join a salon by telephone. One number for everyone: a
    # salon lasts ten minutes and a number is leased by the month, so one per salon is
    # impossible. Routing happens after the call is answered, on the six-digit code the
    # guest received.
    #
    # Empty until a SIP-capable number exists, and every message omits the telephone
    # option while it is: promising a way in that does not answer is worse than silence.
    # Note that the toll-free number leased for SMS cannot serve this — AWS End User
    # Messaging does not offer a SIP trunk.
    salon_phone_number: str = ""

    # The LiveKit inbound SIP trunk that number terminates on. Empty disables the dispatch
    # rules entirely, so the code below is inert rather than failing on every invitation.
    sip_trunk_id: str = ""

    # How long after a guest is invited the agent opens the conversation by itself.
    #
    # Published in the guest_invited message rather than compiled into each client, so the
    # countdown a host watches and the delay the agent actually waits are the same number.
    # Three codebases each holding their own 15 would drift, and the failure would be a
    # counter reaching zero in silence — the most alarming way for this to break.
    invitation_opening_seconds: int = 15

    # Whether the clients offer to invite by text message.
    #
    # A flag rather than markup commented out, because the thing it waits on is an AWS
    # review and not a decision of ours: hiding the field in the app would mean a store
    # build to bring it back, days after the capability actually arrives. Flipping this
    # is one secret change and one API deployment, and every client picks it up on its
    # next launch.
    #
    # The API keeps accepting a phone number regardless. This governs what is offered,
    # not what is allowed — a request that arrives with one is still honoured, and the
    # host still gets the link to share by hand when the send fails.
    sms_enabled: bool = False

    # ── Administration ────────────────────────────────────────────────────────
    # Who may read the participation records. Comma-separated, compared without regard
    # to case. Kept in configuration rather than in a database column on purpose: a
    # column would mean a way to grant this privilege at runtime, and there is no screen
    # to review such a grant. Changing this list requires a deploy, which leaves a trace.
    #
    # Worth stating plainly: whoever receives mail at one of these addresses can obtain
    # the full list of participant emails, because authentication is a one-time code sent
    # to that mailbox. The mailbox is the credential.
    admin_emails: str = "s.degrandpre@vocaliz.net"

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
