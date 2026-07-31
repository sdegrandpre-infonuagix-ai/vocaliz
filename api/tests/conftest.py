"""Shared test infrastructure — single in-memory SQLite engine for all API tests."""
import os

# Set required env vars before src.config is imported (no defaults in production).
os.environ.setdefault("JWT_SECRET", "test-only-secret-do-not-use-in-production")
os.environ.setdefault("LIVEKIT_API_SECRET", "test-only-livekit-secret")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, StaticPool
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
    """Stop agent dispatch and room notifications from reaching LiveKit in tests.

    Both swallow their own exceptions, so without this every session-creating test
    would silently attempt a real connection to the configured LiveKit URL — slow and
    dependent on the network.

    Tests that exercise those functions themselves opt out with
    @pytest.mark.real_livekit_service, otherwise they would assert against this mock.
    """
    from unittest.mock import AsyncMock, patch

    if request.node.get_closest_marker("real_livekit_service"):
        yield
        return

    with (
        patch("src.services.livekit_service.dispatch_agent", new_callable=AsyncMock),
        patch("src.services.livekit_service.notify_room", new_callable=AsyncMock),
    ):
        yield


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def db():
    session = TestingSession()
    yield session
    session.close()
