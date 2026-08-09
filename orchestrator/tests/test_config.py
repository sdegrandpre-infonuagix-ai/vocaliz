"""Configuration and secrets: read from the environment, fail loudly at startup."""
import json
import sys
import types

import pytest
from pydantic import ValidationError

from src.config import (
    MissingConfigurationError,
    REQUIRED_SECRET_FIELDS,
    Settings,
    fetch_secret,
    load_settings,
)

COMPLETE_ENV = {
    "LIVEKIT_URL": "ws://localhost:7880",
    "LIVEKIT_API_KEY": "devkey",
    "LIVEKIT_API_SECRET": "secret",
    "DATABASE_URL": "postgresql://salon:password@localhost:5432/salon",
}


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """Nothing leaks in from the developer's own shell or from a previous test."""
    for name in (
        *COMPLETE_ENV,
        "ORCHESTRATOR_SECRET_ARN",
        "AWS_REGION",
        "ENVIRONMENT",
        "PORT",
        "LOG_LEVEL",
        "DRAIN_TIMEOUT_SECONDS",
    ):
        monkeypatch.delenv(name, raising=False)


def _set(monkeypatch, values):
    for key, value in values.items():
        monkeypatch.setenv(key, value)


def test_settings_are_read_from_the_environment(monkeypatch):
    _set(monkeypatch, COMPLETE_ENV | {"ENVIRONMENT": "production", "PORT": "9001"})

    settings = load_settings(env_file=None)

    assert isinstance(settings, Settings)
    assert settings.livekit_url == "ws://localhost:7880"
    assert settings.livekit_api_secret == "secret"
    assert settings.environment == "production"
    assert settings.port == 9001


def test_defaults_apply_to_everything_that_is_not_a_secret(monkeypatch):
    _set(monkeypatch, COMPLETE_ENV)

    settings = load_settings(env_file=None)

    assert settings.port == 8080
    assert settings.environment == "local"
    assert settings.aws_region == "ca-central-1"
    assert settings.drain_timeout_seconds > 0


def test_a_missing_secret_fails_at_startup_and_names_itself(monkeypatch):
    """Never silently, never at the first request — at startup, with the name."""
    _set(monkeypatch, {k: v for k, v in COMPLETE_ENV.items() if k != "LIVEKIT_API_SECRET"})

    with pytest.raises(MissingConfigurationError) as excinfo:
        load_settings(env_file=None)

    assert excinfo.value.missing == ["LIVEKIT_API_SECRET"]
    assert "LIVEKIT_API_SECRET" in str(excinfo.value)


def test_every_missing_secret_is_reported_at_once(monkeypatch):
    """One restart to learn what is missing, not one restart per secret."""
    with pytest.raises(MissingConfigurationError) as excinfo:
        load_settings(env_file=None)

    assert excinfo.value.missing == sorted(f.upper() for f in REQUIRED_SECRET_FIELDS)


def test_the_error_message_never_repeats_a_secret_value(monkeypatch):
    _set(monkeypatch, {k: v for k, v in COMPLETE_ENV.items() if k != "DATABASE_URL"})

    with pytest.raises(MissingConfigurationError) as excinfo:
        load_settings(env_file=None)

    assert "secret" not in str(excinfo.value)
    assert "devkey" not in str(excinfo.value)


def test_secrets_manager_supplies_what_the_environment_lacks(monkeypatch):
    _set(monkeypatch, {"ORCHESTRATOR_SECRET_ARN": "arn:aws:secretsmanager:...:salon/orchestrator"})
    calls = []

    def loader(secret_arn, region):
        calls.append((secret_arn, region))
        return dict(COMPLETE_ENV)

    settings = load_settings(env_file=None, secrets_loader=loader)

    assert calls == [("arn:aws:secretsmanager:...:salon/orchestrator", "ca-central-1")]
    assert settings.livekit_api_key == "devkey"


def test_the_environment_wins_over_secrets_manager(monkeypatch):
    """A local override stays possible, and mirrors how the API resolves its own secret."""
    _set(monkeypatch, COMPLETE_ENV | {"ORCHESTRATOR_SECRET_ARN": "arn:whatever"})

    settings = load_settings(
        env_file=None,
        secrets_loader=lambda arn, region: {"LIVEKIT_API_KEY": "from-aws"},
    )

    assert settings.livekit_api_key == "devkey"


def test_blank_secrets_manager_entries_are_ignored(monkeypatch):
    """An empty string in the secret is an unset key, not a valid credential."""
    _set(monkeypatch, {"ORCHESTRATOR_SECRET_ARN": "arn:whatever"})

    with pytest.raises(MissingConfigurationError) as excinfo:
        load_settings(
            env_file=None,
            secrets_loader=lambda arn, region: COMPLETE_ENV | {"LIVEKIT_API_SECRET": ""},
        )

    assert excinfo.value.missing == ["LIVEKIT_API_SECRET"]


def test_no_secret_arn_means_no_call_to_aws(monkeypatch):
    """A developer on their own machine starts without any AWS dependency."""
    _set(monkeypatch, COMPLETE_ENV)

    def explode(secret_arn, region):  # pragma: no cover - must never run
        raise AssertionError("AWS was contacted during a local start")

    assert load_settings(env_file=None, secrets_loader=explode).environment == "local"


def test_fetch_secret_reads_the_json_string_out_of_the_aws_response(monkeypatch):
    """The one path that only ever runs in AWS. A wrong key here fails on a deploy and
    nowhere else, so boto3 is stubbed rather than left untested."""
    boto3 = types.ModuleType("boto3")
    seen = {}

    class FakeClient:
        def get_secret_value(self, SecretId):  # noqa: N803 — boto3's own parameter name
            seen["secret_id"] = SecretId
            return {"SecretString": json.dumps({"LIVEKIT_API_KEY": "from-aws"})}

    def client(service, region_name):
        seen["service"] = service
        seen["region"] = region_name
        return FakeClient()

    boto3.client = client
    monkeypatch.setitem(sys.modules, "boto3", boto3)

    payload = fetch_secret("arn:aws:secretsmanager:...:salon/orchestrator", "ca-central-1")

    assert payload == {"LIVEKIT_API_KEY": "from-aws"}
    assert seen["service"] == "secretsmanager"
    assert seen["region"] == "ca-central-1"
    assert seen["secret_id"] == "arn:aws:secretsmanager:...:salon/orchestrator"


def test_a_malformed_value_is_not_disguised_as_a_missing_one(monkeypatch):
    """PORT=nonsense is a different mistake from PORT unset, and must read as one."""
    _set(monkeypatch, COMPLETE_ENV | {"PORT": "not-a-number"})

    with pytest.raises(ValidationError):
        load_settings(env_file=None)


def test_a_secrets_manager_failure_is_reported_as_a_startup_failure(monkeypatch):
    _set(monkeypatch, {"ORCHESTRATOR_SECRET_ARN": "arn:broken"})

    def explode(secret_arn, region):
        raise RuntimeError("AccessDeniedException")

    with pytest.raises(MissingConfigurationError) as excinfo:
        load_settings(env_file=None, secrets_loader=explode)

    assert "arn:broken" in str(excinfo.value)
