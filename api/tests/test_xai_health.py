"""Is xAI answering? Probed every minute, because the failure is invisible from inside Vocaliz.

A spent balance, a revoked key and a suspended team all produce the same symptom: the agent
joins a Salon, the room looks normal, and nobody is ever answered. Nothing errors, so nothing
tells anybody — which is how three keys came to be rotated in one afternoon over a problem that
turned out to be a credit limit on a card.

xAI publishes no balance endpoint. /v1/billing, /v1/credits and /v1/usage all answer 404, and
/v1/api-key returns the key's metadata and nothing about money. A threshold was the obvious
design and it is unavailable, so this detects the condition instead of predicting it.

The tests that matter most here are the ones about *not* sending: a probe every minute that
emailed on every failure would send more than fourteen hundred messages during one bad night.
"""
from unittest.mock import MagicMock, patch

import pytest

from src.models.service_health import ServiceHealth
from src.services import xai_health


@pytest.fixture
def sent():
    """Every alert this test sent, without touching SES."""
    with patch("src.services.xai_health.boto3") as boto:
        client = MagicMock()
        boto.client.return_value = client
        yield client.send_email


def _probing(healthy: bool, detail: str = "HTTP 402: insufficient credits"):
    return patch.object(
        xai_health, "probe", return_value=(healthy, "" if healthy else detail)
    )


# ─── The first probe ─────────────────────────────────────────────────────────

def test_a_healthy_first_probe_says_nothing(db, sent):
    """An email announcing that monitoring has started is noise on the day it is deployed."""
    with _probing(True):
        result = xai_health.check(db)
    assert result["alerted"] is False
    sent.assert_not_called()


def test_a_failing_first_probe_alerts_immediately(db, sent):
    """Deployed into an outage is exactly when somebody needs telling."""
    with _probing(False):
        result = xai_health.check(db)
    assert result["alerted"] is True
    sent.assert_called_once()


# ─── Not sending fourteen hundred emails ─────────────────────────────────────

def test_a_second_failure_is_silent(db, sent):
    """The whole reason the state is remembered. An inbox with a thousand identical alerts is
    an inbox where the next real one is missed."""
    with _probing(False):
        xai_health.check(db)
        sent.reset_mock()
        for _ in range(5):
            assert xai_health.check(db)["alerted"] is False
    sent.assert_not_called()


def test_a_continuing_success_is_silent(db, sent):
    with _probing(True):
        for _ in range(5):
            assert xai_health.check(db)["alerted"] is False
    sent.assert_not_called()


def test_an_unchanged_state_does_not_touch_the_row(db, sent):
    """changed_at means "when this last became true", not "when we last looked". Rewriting it
    on every probe would destroy the only fact the column carries."""
    with _probing(False):
        xai_health.check(db)
        first = db.get(ServiceHealth, xai_health.SERVICE).changed_at
        xai_health.check(db)
    assert db.get(ServiceHealth, xai_health.SERVICE).changed_at == first


# ─── Both transitions ────────────────────────────────────────────────────────

def test_recovery_is_announced(db, sent):
    """Being told something broke and never told it was fixed leaves somebody checking by
    hand, which is the work this was meant to remove."""
    with _probing(False):
        xai_health.check(db)
    sent.reset_mock()
    with _probing(True):
        assert xai_health.check(db)["alerted"] is True
    sent.assert_called_once()


def test_the_outage_email_says_what_the_symptom_looks_like(db, sent):
    """"xAI returned 402" means nothing to somebody at an awkward hour. That agents will be
    silent, and that nothing else will show an error, is the actionable part."""
    with _probing(False):
        xai_health.check(db)
    body = sent.call_args.kwargs["Message"]["Body"]["Text"]["Data"]
    assert "will not speak" in body
    assert "insufficient credits" in body, "the reason xAI gave has to be quoted"
    assert "console.x.ai" in body


def test_the_alert_goes_to_the_configured_administrator(db, sent):
    from src.config import settings

    with _probing(False):
        xai_health.check(db)
    assert sent.call_args.kwargs["Destination"]["ToAddresses"] == [settings.front_desk_email]


# ─── The probe itself ────────────────────────────────────────────────────────

def test_the_probe_asks_for_a_completion_not_the_key():
    """/v1/api-key answers 200 with a spent balance — it validates the key and knows nothing
    about credit — so probing it would report health right through the outage.

    The assertion reads the code and not the docstring, which explains at length that
    /v1/api-key is the wrong endpoint. Fifth time today a test has caught itself quoting its
    own reasoning as evidence."""
    import inspect

    source = inspect.getsource(xai_health.probe)
    assert "chat/completions" in source
    body = source.split('"""')[-1]
    assert "api-key" not in body.replace("xai_api_key", "")


def test_the_probe_asks_for_one_token(db):
    """Fourteen hundred probes a day is only affordable because each one is a single token."""
    import inspect

    assert '"max_tokens": 1' in inspect.getsource(xai_health.probe)


def test_a_missing_key_is_unhealthy_rather_than_an_exception(db):
    from src.config import settings

    with patch.object(settings, "xai_api_key", ""):
        healthy, detail = xai_health.probe()
    assert healthy is False
    assert "key" in detail.lower()


def test_an_unreachable_xai_counts_as_unhealthy(db):
    """Unreachable is indistinguishable from refusing, from where the agent stands."""
    with patch("src.services.xai_health.httpx.post", side_effect=OSError("no route")):
        healthy, detail = xai_health.probe()
    assert healthy is False
    assert "could not be reached" in detail


def test_a_failing_alert_never_breaks_the_monitor(db):
    """A monitor that can crash is a monitor that stops monitoring — and it would fail
    silently, the same shape as the outage it watches for."""
    with patch("src.services.xai_health.boto3") as boto, _probing(False):
        boto.client.side_effect = RuntimeError("SES is down")
        assert xai_health.check(db)["healthy"] is False


# ─── Being able to see what the schedule does ─────────────────────────────────
#
# The sweep and this probe both run on a schedule, so the log is the only record — EventBridge
# discards return values. For hours it was no record at all: alembic's fileConfig disables every
# existing logger by default, which killed this module's logging for the whole life of a warm
# Lambda container. Both jobs ran every minute and said nothing, and the silence looked exactly
# like a schedule that was not firing.

def test_alembic_no_longer_silences_everything_else():
    """The cause. One keyword, and without it every migration blinds the container it ran in."""
    import pathlib

    env = pathlib.Path(__file__).resolve().parents[1] / "migrations" / "env.py"
    source = env.read_text(encoding="utf-8")
    assert "disable_existing_loggers=False" in source


def test_the_maintenance_function_reports_through_stdout():
    """Immune to whatever the logging module has been told. A silent failure in the thing that
    reports failures deserves a path nothing can reconfigure — and Lambda captures stdout
    regardless."""
    import inspect

    from src import migrate_handler

    assert "print(" in inspect.getsource(migrate_handler._report)


def test_every_scheduled_action_says_what_it_did():
    """A scheduled job whose outcome is invisible cannot be trusted, and cannot be debugged
    either: the return value goes to EventBridge, which throws it away."""
    import inspect

    from src import migrate_handler

    source = inspect.getsource(migrate_handler.handler)
    for action in ("check_xai", "sweep_sessions", "invoice_advertisers"):
        assert f'_report(f"{action}' in source, f"{action} runs silently"


# ─── Voice, reported rather than probed ───────────────────────────────────────
#
# xAI offers no cheap voice call: /v1/audio/speech answers 403 for this team, and a realtime
# session is too costly to open every minute purely to ask whether it can be opened. So the
# agent reports what it actually observed, which is better than a probe in the way that matters
# — a substitute can succeed while the genuine path fails, and this cannot, because it is the
# genuine path. What it gives up is warning: nothing is said until somebody calls.

def test_voice_and_text_are_tracked_separately(db, sent):
    """Two things fail independently. One row would let a healthy text API hide a broken voice
    one, which is the exact gap this was built to close."""
    with _probing(True):
        xai_health.check(db)
    xai_health.record(db, service=xai_health.VOICE_SERVICE, healthy=False, detail="handshake 400")

    assert db.get(ServiceHealth, xai_health.SERVICE).healthy is True
    assert db.get(ServiceHealth, xai_health.VOICE_SERVICE).healthy is False


def test_the_voice_alert_says_it_is_voice(db, sent):
    """"xAI is not answering" would send somebody to check their credit when the text API is
    fine and only the voice model is not."""
    xai_health.record(db, service=xai_health.VOICE_SERVICE, healthy=False, detail="handshake 400")
    subject = sent.call_args.kwargs["Message"]["Subject"]["Data"]
    assert "voice" in subject.lower()


def test_the_voice_alert_says_somebody_was_already_affected(db, sent):
    """This is not a warning about what might happen. An agent really tried to join a real
    Salon and could not speak, so a caller was already failed."""
    xai_health.record(db, service=xai_health.VOICE_SERVICE, healthy=False, detail="handshake 400")
    body = sent.call_args.kwargs["Message"]["Body"]["Text"]["Data"]
    assert "already affected" in body


def test_voice_alerts_once_like_everything_else(db, sent):
    """A busy evening opens many Salons. If every failed one emailed, the inbox would fill at
    the rate people were being let down."""
    xai_health.record(db, service=xai_health.VOICE_SERVICE, healthy=False, detail="a")
    sent.reset_mock()
    for _ in range(4):
        xai_health.record(db, service=xai_health.VOICE_SERVICE, healthy=False, detail="a")
    sent.assert_not_called()


def test_the_agent_reports_through_an_authenticated_endpoint(client, db):
    """Anonymous, this would let anybody declare the voice model broken and trigger an alert."""
    assert client.post("/sessions/whatever/voice-health", json={"ok": False}).status_code in (
        401,
        403,
    )
