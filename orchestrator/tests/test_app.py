"""The service starts, says so in the log, and answers about its own health.

Two health endpoints rather than one, because ECS asks two different questions. Liveness
answers "is this process wedged, should it be killed"; readiness answers "may this instance
be given work". A draining instance is perfectly alive and must not be killed — it is
finishing the Salons it holds — but it must stop being given new ones.
"""
import logging
import signal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.config import Settings
from src.lifecycle import SalonRegistry
from src.settings import InMemorySettingsStore
from src.main import (
    COMPONENT,
    HEALTH_PATH,
    READINESS_PATH,
    VERSION,
    _install_shutdown_handlers,
    app,
    create_app,
    handle_shutdown_signal,
)

# Explicit settings rather than whatever the developer's shell holds: what the health
# endpoint answers should not depend on the machine the suite runs on. The credentials are
# obviously fake and no test in this file opens a socket.
SETTINGS = Settings(
    livekit_url="ws://localhost:7880",
    livekit_api_key="devkey",
    livekit_api_secret="a-secret-nobody-should-see",
    database_url="postgresql://salon:hunter2@aurora:5432/salon",
    environment="test",
)


@pytest.fixture
def client():
    """Entering the client runs the lifespan, which builds a fresh registry — so a drain
    started by one test is not still in force in the next.

    Leaving it runs the drain, which waits for whatever is still hosted. A test that
    accepted a Salon and did not release it would sit there for the full drain timeout,
    so the teardown lets go of everything first.
    """
    with TestClient(app) as client:
        yield client
        registry = app.state.registry
        for salon_id in registry.hosted:
            registry.release(salon_id)


def test_liveness_reports_the_process_is_alive(client):
    response = client.get(HEALTH_PATH)

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "component": COMPONENT, "version": VERSION}


def test_readiness_reports_ready_and_what_is_hosted(client):
    response = client.get(READINESS_PATH)

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "draining": False, "hostedSalons": 0}


def test_readiness_counts_the_salons_this_instance_hosts(client):
    app.state.registry.accept("salon-1")

    assert client.get(READINESS_PATH).json()["hostedSalons"] == 1


def test_readiness_turns_away_a_draining_instance(client):
    app.state.registry.begin_drain()

    response = client.get(READINESS_PATH)

    assert response.status_code == 503
    assert response.json()["status"] == "draining"


def test_liveness_stays_ok_while_draining(client):
    """Draining must not read as "wedged" — ECS would kill the task mid-Salon."""
    app.state.registry.begin_drain()

    assert client.get(HEALTH_PATH).status_code == 200


def test_a_termination_signal_starts_the_drain(client):
    handle_shutdown_signal(app)

    assert app.state.registry.draining is True
    assert client.get(READINESS_PATH).status_code == 503


def test_a_second_termination_signal_changes_nothing(client):
    """ECS may send SIGTERM more than once; the drain has one beginning."""
    app.state.registry.accept("salon-1")
    handle_shutdown_signal(app)
    handle_shutdown_signal(app)

    assert app.state.registry.draining is True
    assert app.state.registry.hosted_count == 1


def test_a_termination_signal_before_startup_is_survivable():
    """Between process start and the lifespan there is no registry yet, and a signal
    arriving in that window must not take the process down with an AttributeError."""
    handle_shutdown_signal(create_app(settings=SETTINGS, settings_store=InMemorySettingsStore()))


def test_the_signal_handler_chains_onto_the_one_it_found(monkeypatch):
    """Uvicorn installs its own SIGTERM handler to close the server. Ours must run before
    it and then call it — a handler that swallowed the signal would leave a task that never
    stops, and ECS would SIGKILL it, which is the opposite of draining."""
    fresh = create_app(settings=SETTINGS, settings_store=InMemorySettingsStore())
    fresh.state.registry = SalonRegistry()
    called = []

    # Both signals are restored, SIGINT included: leaving our handler installed would have
    # every later Ctrl-C in this process run against a torn-down application.
    originals = {number: signal.getsignal(number) for number in (signal.SIGTERM, signal.SIGINT)}
    signal.signal(signal.SIGTERM, lambda signum, frame: called.append(signum))
    try:
        _install_shutdown_handlers(fresh)
        signal.getsignal(signal.SIGTERM)(signal.SIGTERM, None)
    finally:
        for number, handler in originals.items():
            signal.signal(number, handler)

    assert fresh.state.registry.draining is True
    assert called == [signal.SIGTERM]


def test_startup_is_logged_with_the_configuration_it_read(caplog):
    with caplog.at_level(logging.INFO, logger=COMPONENT):
        with TestClient(create_app(settings=SETTINGS, settings_store=InMemorySettingsStore())):
            pass

    startup = [r for r in caplog.records if r.getMessage().startswith("orchestrator starting")]
    assert startup, (
        "startup must leave a trace — an instance that starts silently "
        "cannot be told from one that did not"
    )
    logged = startup[0].getMessage()
    assert f"version={VERSION}" in logged
    assert "environment=test" in logged
    assert "port=8080" in logged


def test_startup_log_never_carries_a_secret(caplog):
    with caplog.at_level(logging.DEBUG):
        with TestClient(create_app(settings=SETTINGS, settings_store=InMemorySettingsStore())):
            pass

    logged = "\n".join(record.getMessage() for record in caplog.records)
    assert "hunter2" not in logged
    assert "a-secret-nobody-should-see" not in logged


def test_shutdown_drains_before_the_process_goes_away(caplog):
    fresh = create_app(settings=SETTINGS, settings_store=InMemorySettingsStore())

    with caplog.at_level(logging.INFO, logger=COMPONENT):
        with TestClient(fresh):
            fresh.state.registry.accept("salon-1")
            fresh.state.registry.release("salon-1")

    assert fresh.state.registry.draining is True
    assert any("drained cleanly" in record.getMessage() for record in caplog.records)


def test_shutdown_says_so_when_a_salon_outlives_the_drain(caplog):
    """The wait is bounded. What is left over is resumed elsewhere, and the log says so."""
    fresh = create_app(
        settings=SETTINGS.model_copy(update={"drain_timeout_seconds": 0}),
        settings_store=InMemorySettingsStore(),
    )

    with caplog.at_level(logging.INFO, logger=COMPONENT):
        with TestClient(fresh):
            fresh.state.registry.accept("salon-1")

    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert any("still hosted" in message for message in warnings)


def test_the_service_shell_carries_no_business_logic():
    """Story 6.1 ships a place to live, not a tenant.

    Scoped to the modules that story delivered, and it stays scoped to them as the epic
    fills in: Story 6.2 puts the Interpreter port in `src/interprete/`, 6.3 will put the
    journal and the reading positions beside it. What must not happen is any of that
    leaking into the four files whose entire job is to start a process and keep it
    healthy — the day `main.py` knows what a turn of speech is, the health endpoint has
    become something that can break for a reason nobody expected.
    """
    source = Path(__file__).resolve().parents[1] / "src"
    shell = ("main.py", "config.py", "lifecycle.py", "logging_config.py")
    forbidden = ("utterance", "curseur", "cursor", "stripe", "billing", "traduction", "translate")

    offenders = [
        (name, word)
        for name in shell
        for word in forbidden
        if word in (source / name).read_text(encoding="utf-8").lower()
    ]

    assert offenders == []
