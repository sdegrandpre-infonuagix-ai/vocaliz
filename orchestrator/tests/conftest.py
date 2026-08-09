"""Shared test setup.

The credentials have no defaults in `Settings` — that is the point of the module — so the
tests that start an application supply them here, before `src.main` is imported. The
values are obviously fake and never reach a network: no test in this suite opens a socket
to LiveKit, to Aurora or to AWS.
"""
import os

os.environ.setdefault("LIVEKIT_URL", "ws://localhost:7880")
os.environ.setdefault("LIVEKIT_API_KEY", "devkey")
os.environ.setdefault("LIVEKIT_API_SECRET", "test-only-livekit-secret")
os.environ.setdefault("DATABASE_URL", "postgresql://salon:password@localhost:5432/salon")
# Belt and braces: an ARN left in a developer's shell would send the whole suite to AWS.
os.environ.pop("ORCHESTRATOR_SECRET_ARN", None)
