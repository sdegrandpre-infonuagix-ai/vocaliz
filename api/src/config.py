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

    # Salon settings
    # Two humans and the agent. Down from four, and the reduction is what makes the room
    # trustworthy rather than merely smaller.
    #
    # Caption attribution is the reason. The realtime model hears every participant mixed into
    # one stream, so who spoke comes from LiveKit's active-speaker detection — right when one
    # person talks, a guess when two overlap. With two humans there is only ever one other
    # voice to confuse yours with, and for an interpreter that is not a nicety: mistaking who
    # spoke reverses the direction of a translation and says somebody's own words back to them.
    livekit_room_max_participants: int = 3
    # How long an empty room survives before LiveKit closes it — and with it, the agent.
    #
    # Thirty seconds, down from five minutes. This is the setting that actually stops an
    # abandoned Salon costing money: the agent holds a live connection to the realtime model
    # for as long as its room exists, and a room nobody is in was costing five more minutes of
    # it every time. LiveKit enforces this itself, at the moment the last participant leaves —
    # no polling, nothing to miss it.
    #
    # The price is paid by a bad connection. Somebody whose phone drops into a tunnel has
    # half a minute to come back before the Salon is gone, where they used to have five. That
    # is still a regression for a caller on mobile data — it was fifteen seconds for an hour,
    # which left no room at all for a reconnect — and it is the reason this is a setting
    # rather than a constant: raise it the moment a dropped call costs more than the idle
    # minutes it saves.
    livekit_room_empty_timeout: int = 30

    # Invitation join links sent via SMS to non-registered contacts
    salon_web_base_url: str = "https://salon.app"

    # App installation link sent to guests without an account after their first salon
    salon_install_url: str = "https://salon.app/install"

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

    # How long a Salon may go unheard-from before it is closed as abandoned.
    #
    # This replaced a ten-minute cap on a conversation's *age*, whose two stated premises
    # both stopped being true at the Epic 8 cutover: the trial it complemented is retired,
    # and what one Salon can spend is now bounded by the payer's balance, tick by tick.
    # An age cap on top of that cut off somebody who had paid for three hours of Mode C
    # after ten minutes — the answer to "how long may this run?" is the balance, and it
    # depends on the mode, which is exactly what a fixed number cannot express.
    #
    # What the cap also did, and what is still needed, is close rooms nobody is in. A
    # crashed worker or a closed laptop stops the heartbeats, and the room would otherwise
    # stay open with an agent talking into it. Silence is the honest signal for that, where
    # age was a proxy that also caught healthy conversations.
    #
    # Ten missed heartbeats at thirty seconds — long enough for a host to actually wait for
    # a friend to arrive, not just survive a reconnection. Raised from 120s: two minutes
    # closed a Salon out from under a host who had opened it and was simply waiting for a
    # guest to click the link, which reads as the product failing before the conversation
    # even started. Still short enough that an abandoned room is not billed for long.
    abandoned_salon_seconds: int = 300

    # How long a call to the front desk rings before it is given up on.
    #
    # Ringing opens a Salon and mails the desk an invitation. Nobody clicking it means nobody
    # answered, and the caller would otherwise sit alone with an agent for as long as their
    # balance held — realtime-model time billed for a call that was never picked up. Five
    # minutes is long enough to notice an email and short enough that the unanswered case is
    # not the most expensive one.
    #
    # Kept on age rather than silence, unlike abandonment above, and the difference is the
    # point: the caller *is* there and heartbeating. Nobody joined them, which silence
    # cannot see.
    unanswered_call_seconds: int = 300

    # Upper bound on the span billed after the last heartbeat when a salon ends.
    # Heartbeats arrive every 30 s, so a gap beyond this means the salon was already
    # dead — a closed laptop, a killed app, a crashed worker. Without this clamp the
    # whole abandoned period would be billed the moment the salon is finally ended.
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

    # Where the orchestrator that holds a Salon's text can be reached.
    #
    # One address rather than a list, because there is one instance: a Salon is stateful —
    # the journal, every reader's position — and the agents of one Salon must all reach the
    # instance that holds it. When there is a fleet this becomes the address of whatever
    # hands out instances, never a balancer distributing each request afresh.
    #
    # Empty until the ECS service is deployed, and empty is inert: no request is made and
    # `salons.orchestrator_url` stays null. A default address resolving to nothing would turn
    # every salon creation into a wait for a connection refused, which is a worse way of
    # saying "not built yet" than doing nothing at all.
    orchestrator_base_url: str = ""

    # What proves a call to POST /orchestrator/wake really came from the orchestrator
    # holding this Salon, rather than from anybody who found the path. Empty means the
    # route refuses every call — see `orchestrator_relay.wake` — which is the safe default:
    # a wake nobody can send is a missed shortcut, never a Salon anybody can reach into.
    orchestrator_callback_secret: str = ""

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

    # Who answers a call placed from the front page.
    #
    # "Call Vocaliz" opens a Salon owned by this address and mails it the invitation, so the
    # desk is reachable by somebody who has no account, no link and no code. A setting rather
    # than a constant because the desk is a role, not a person — the address changes when
    # somebody else is on shift, and that should not be a deploy.
    front_desk_email: str = "s.degrandpre@vocaliz.net"

    # How many calls the front page will place in an hour, across everybody.
    #
    # The endpoint is public: it creates a Salon and sends an email with no authentication at
    # all, which is precisely the shape somebody automates. The cap is deliberately low —
    # a real desk fields a handful of calls an hour, and the failure this prevents is a
    # thousand Salons and a thousand emails arriving overnight.
    front_desk_calls_per_hour: int = 20

    # Stripe billing — set STRIPE_SECRET_KEY in production
    stripe_secret_key: str = "sk_test_placeholder"

    # ── The auction ───────────────────────────────────────────────────────────
    # How an ad's bid is distributed across the two things that make it relevant to a salon.
    # They are normalised before use, so 3 and 1 means the same as 0.75 and 0.25 — what matters
    # is their ratio, not that they sum to one.
    #
    # Equal by default, which is a claim about nothing: it says region and subject matter the
    # same amount, because there is no traffic yet to say otherwise. Raise the region weight to
    # favour local businesses, the topic weight to favour relevance over geography.
    bid_region_weight: float = 1.0
    bid_topic_weight: float = 1.0

    # What an advertiser pays for one broadcast, in cents. Copied onto each ad_broadcasts
    # row at the moment it is spoken, never read back at billing time — an invoice has to
    # charge what was agreed then, and reading this later would silently reprice history.
    #
    # Invoiced in batches, not per broadcast: Stripe takes roughly 2.9% plus thirty cents per
    # transaction, so charging twenty-five cents individually would lose money on every one.
    #
    # With the auction above this is the reserve: the floor an ad must clear to be eligible at
    # all, and the price charged when it won without anyone to outbid.
    ad_broadcast_rate_cents: int = 25

    # The tier rates live in `credit.TIER_RATES_CENTS_PER_HOUR`, not here, and that is
    # deliberate: what an hour costs is a product decision that differs per mode, where this
    # file holds what differs per deployment. A single `hourly_rate_cents` sat here until the
    # Epic 8 cutover and could only ever have named one of the four.
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
