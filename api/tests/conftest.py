"""Shared test infrastructure — single in-memory SQLite engine for all API tests."""
import os

# Set required env vars before src.config is imported (no defaults in production).
os.environ.setdefault("JWT_SECRET", "test-only-secret-do-not-use-in-production")
os.environ.setdefault("LIVEKIT_API_SECRET", "test-only-livekit-secret")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, StaticPool
from sqlalchemy.orm import sessionmaker

from src.database import Base, get_db
from src.main import app
from src.rate_limit import limiter

SQLALCHEMY_TEST_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_TEST_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# SQLite ignores foreign keys unless asked, per connection. Without this, every ON DELETE
# RESTRICT and ON DELETE SET NULL in the schema is inert in tests: they are declared, Postgres
# enforces them, and nothing here ever checks. That is the worst place for a gap — the
# constraints protecting billing evidence would be verified only in production.
@event.listens_for(engine, "connect")
def _enforce_foreign_keys(dbapi_connection, _record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def _override_get_db():
    db = TestingSession()
    try:
        yield db
    finally:
        db.close()


# Install override once at collection time; all tests share this engine
app.dependency_overrides[get_db] = _override_get_db


@pytest.fixture(autouse=True)
def _fresh_db():
    """Create all tables before each test, drop them after, and reset rate limits."""
    Base.metadata.create_all(bind=engine)
    try:
        limiter._storage.reset()
    except Exception:
        pass
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(autouse=True)
def _no_livekit_side_calls(request):
    """Stop room provisioning, agent dispatch and room notifications from reaching LiveKit.

    Dispatch, notification and deletion swallow their own exceptions, so without this every
    salon-creating test would silently attempt a real connection to the configured LiveKit
    URL — slow and dependent on the network. `create_room` does not swallow its own failure
    (it raises a 503 for the caller to answer with), so leaving it real here would fail these
    tests outright rather than slowly: every guest-join test provisions the guest's own room
    now, on top of the host's own tests that already patched this locally.

    Tests that exercise those functions themselves opt out with
    @pytest.mark.real_livekit_service, otherwise they would assert against this mock.

    `dispatch_agent` is autospecced rather than a bare AsyncMock: it gained three required
    keyword-only arguments for the per-participant topology, one call site was never updated
    to pass them, and a bare mock accepts any call — so every test through this fixture kept
    passing while the real endpoint 500'd. Only caught live. Autospeccing turns a missing or
    misnamed argument back into the TypeError it always should have been.
    """
    from unittest.mock import AsyncMock, patch

    if request.node.get_closest_marker("real_livekit_service"):
        yield
        return

    with (
        patch("src.services.livekit_service.create_room", new_callable=AsyncMock),
        patch("src.services.livekit_service.dispatch_agent", autospec=True),
        patch("src.services.livekit_service.notify_room", new_callable=AsyncMock),
        patch("src.services.livekit_service.delete_room", new_callable=AsyncMock),
    ):
        yield


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def db():
    salon = TestingSession()
    yield salon
    salon.close()


@pytest.fixture(autouse=True)
def _no_email_or_sms_side_calls():
    """Stop every code path that mails or texts through AWS from making a real, billed call.

    Discovered by way of `salon_closure_report`: ending a salon now mails a closure report
    on every path that reaches `finalize_salon`, and that function is exercised by tests
    that have nothing to do with email and no reason to know it happens — unlike
    `test_auth.py`'s OTP tests, which patch `otp._send_email` themselves because sending is
    exactly what they are testing. A test in the second category stays untouched: it patches
    a function above this point, and that patch wins for its duration regardless of what
    this fixture does to the client underneath it.
    boto3.client is patched rather than each call site (`participant_report`,
    `salon_closure_report`, `invitation_service`, `otp`, `xai_health`, `sms_service`) so a
    future one is covered without anyone having to remember to add another patch here.
    Limited to the three services that actually send something to somebody — `translate`
    has its own fixture below, and anything else (`secretsmanager`, at import time) is left
    alone.
    """
    from unittest.mock import MagicMock, patch

    import boto3 as _boto3

    real_client = _boto3.client

    def _fake_client(service_name, *args, **kwargs):
        if service_name in ("ses", "sesv2", "sns"):
            return MagicMock()
        return real_client(service_name, *args, **kwargs)

    with patch("boto3.client", side_effect=_fake_client):
        yield


@pytest.fixture(autouse=True)
def _no_translate_side_calls():
    """Stop the corpus search from reaching Amazon Translate in tests.

    Every question is translated into English before it is matched, because the topics are
    English. translate() swallows its own errors and returns None, so without this each
    search test would make a real, billed, network-dependent call and pass anyway — the
    worst combination: slow, costing money, and invisible.

    Returning None is what a translator outage looks like, and the search is written to fall
    back to the untranslated words.

    No opt-out marker, unlike the LiveKit guard above: a test that wants to control what the
    translator returns simply patches it again inside itself, and the inner patch wins for
    its duration. A marker was written here first and removed once it turned out to unlock
    nothing — one whose name promised real calls that no test ever made.
    """
    from unittest.mock import patch

    with patch("src.services.translation_service.translate", return_value=None):
        yield
