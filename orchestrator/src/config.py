"""Orchestrator configuration.

Everything comes from the environment. Credentials come from AWS Secrets Manager when
ORCHESTRATOR_SECRET_ARN is set — the same shape the API already uses for APP_SECRET_ARN,
so there is one way to hold a secret in this repository rather than two.

The whole point of this module is that it fails at *startup*. A credential that is only
noticed when the first participant speaks turns a deploy mistake into a broken Salon, and
the person who finds it is a customer rather than the pipeline.
"""
from __future__ import annotations

import json
import os
from typing import Callable, Mapping, MutableMapping, Sequence

from pydantic import ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

# The environment variable the ECS task definition points at the Secrets Manager entry
# with. The task carries the ARN; this process reads the values itself at startup, exactly
# as the API Lambda does with APP_SECRET_ARN.
SECRET_ARN_ENV = "ORCHESTRATOR_SECRET_ARN"

# How long a draining instance waits for the Salons it hosts before stopping anyway.
#
# Under the ECS `stopTimeout`, which Fargate caps at 120 s: past that the platform sends
# SIGKILL regardless, and a drain still waiting at that moment would be cut off rather
# than finish. The margin is what makes the wait mean something.
DEFAULT_DRAIN_TIMEOUT_SECONDS = 90

# The fields with no default. Naming them here rather than inferring them keeps the error
# message stable and lets the deployment tests check the task definition supplies them.
REQUIRED_SECRET_FIELDS: tuple[str, ...] = (
    "livekit_url",
    "livekit_api_key",
    "livekit_api_secret",
    "database_url",
)

# The same list as it appears in the environment and in the Secrets Manager entry.
REQUIRED_SECRETS: tuple[str, ...] = tuple(field.upper() for field in REQUIRED_SECRET_FIELDS)

SecretsLoader = Callable[[str, str], Mapping[str, object]]


class MissingConfigurationError(RuntimeError):
    """Raised at startup when the orchestrator has not been given what it needs.

    Carries the *names* of what is missing and never a value: this message reaches
    CloudWatch, and a message that quoted the credential it was complaining about would
    publish it in clear next to the reason it mattered.
    """

    def __init__(self, missing: Sequence[str], *, detail: str | None = None) -> None:
        self.missing = list(missing)
        message = (
            "Orchestrator cannot start: missing required configuration "
            f"{', '.join(self.missing)}."
        )
        if detail:
            message = f"{message} {detail}"
        super().__init__(
            f"{message} Set them in the environment, or point {SECRET_ARN_ENV} at "
            "an AWS Secrets Manager entry holding them."
        )


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # ── Service ───────────────────────────────────────────────────────────────
    host: str = "0.0.0.0"
    port: int = 8080
    log_level: str = "INFO"
    # Which deployment this is. Only ever used in logs and health output, so a free string
    # rather than an enum — an unknown value should not stop a service from starting.
    environment: str = "local"
    aws_region: str = "ca-central-1"

    # Ninety seconds, under the task definition's stopTimeout so the drain finishes on its
    # own terms rather than being cut short by SIGKILL. It cannot simply be raised to
    # match: Fargate caps stopTimeout at 120 s, and that ceiling is the real constraint.
    drain_timeout_seconds: int = DEFAULT_DRAIN_TIMEOUT_SECONDS

    # ── Credentials (no defaults on purpose — see MissingConfigurationError) ──
    livekit_url: str
    livekit_api_key: str
    livekit_api_secret: str
    database_url: str


def fetch_secret(secret_arn: str, region: str) -> Mapping[str, object]:
    """Read a JSON secret from AWS Secrets Manager.

    boto3 is imported here rather than at module scope so a local run never needs AWS
    credentials, nor the import.
    """
    import boto3

    client = boto3.client("secretsmanager", region_name=region)
    return json.loads(client.get_secret_value(SecretId=secret_arn)["SecretString"])


def load_settings(
    *,
    env: MutableMapping[str, str] | None = None,
    env_file: str | None = ".env",
    secrets_loader: SecretsLoader | None = None,
) -> Settings:
    """Build the settings, resolving Secrets Manager first when an ARN is configured.

    Values already present in the environment win over the secret, which keeps a local
    override possible and mirrors `api/src/config.py`.
    """
    env = os.environ if env is None else env
    secret_arn = env.get(SECRET_ARN_ENV)

    if secret_arn:
        loader = secrets_loader or fetch_secret
        region = env.get("AWS_REGION") or Settings.model_fields["aws_region"].default
        try:
            payload = loader(secret_arn, region)
        except Exception as exc:  # noqa: BLE001 — any failure here is a startup failure
            raise MissingConfigurationError(
                REQUIRED_SECRETS,
                detail=(
                    f"AWS Secrets Manager entry {secret_arn} could not be read "
                    f"({type(exc).__name__})."
                ),
            ) from exc

        for key, value in payload.items():
            # An empty string in the secret is an unset key, not a valid credential.
            if value != "" and value is not None and key not in env:
                env[key] = str(value)

    try:
        return Settings(_env_file=env_file)
    except ValidationError as exc:
        missing = sorted(
            {
                str(error["loc"][0]).upper()
                for error in exc.errors()
                if error["type"] == "missing" and error["loc"]
            }
        )
        if missing:
            raise MissingConfigurationError(missing) from exc
        raise
