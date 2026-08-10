"""The orchestrator service: starts, configures itself, reports its health, drains.

Nothing more, on purpose. The journal and the interpreter positions arrive in Story 6.3,
the rooms in 6.4, the ledger in Epic 8. What this story delivers is the place they will
live in — a deployable that exists so the ones after it have somewhere to go.

Two health endpoints rather than one, because ECS asks two different questions:

- `/health` — liveness. Is this process wedged and worth killing? A draining instance is
  not: it is finishing what it holds, and killing it is precisely what the drain avoids.
- `/health/ready` — readiness. May this instance be given new Salons? A draining one may
  not, and says so with 503 while staying perfectly alive.
"""
from __future__ import annotations

import logging
import signal
from contextlib import asynccontextmanager
from types import FrameType
from typing import Callable

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from sqlalchemy.ext.asyncio import create_async_engine

from src.config import DEFAULT_DRAIN_TIMEOUT_SECONDS, Settings, load_settings
from src.journal.sql_store import async_url
from src.salon import Salon
from src.serving import build_router
from src.settings import LiveSettings, SettingsStore, SqlSettingsStore
from src.lifecycle import SalonRegistry
from src.logging_config import configure_logging

COMPONENT = "orchestrator"
VERSION = "0.1.0"

HEALTH_PATH = "/health"
READINESS_PATH = "/health/ready"

logger = logging.getLogger("orchestrator")

__all__ = [
    "COMPONENT",
    "DEFAULT_DRAIN_TIMEOUT_SECONDS",
    "HEALTH_PATH",
    "READINESS_PATH",
    "VERSION",
    "app",
    "create_app",
    "handle_shutdown_signal",
]


def handle_shutdown_signal(target: FastAPI) -> None:
    """Begin draining. Called on SIGTERM, which is how ECS asks a task to stop.

    Flipping the flag on the signal rather than waiting for the server to close matters by
    a few seconds: in between, an instance that kept answering "ready" would be handed a
    Salon it is about to abandon.
    """
    registry: SalonRegistry | None = getattr(target.state, "registry", None)
    if registry is None or registry.draining:
        return

    logger.info("orchestrator draining: hosted=%d reason=signal", registry.hosted_count)
    registry.begin_drain()


def _install_shutdown_handlers(target: FastAPI) -> None:
    """Chain a drain onto the existing SIGTERM/SIGINT handlers.

    Chaining rather than replacing: uvicorn installs its own handlers to close the server
    gracefully, and a handler of ours that swallowed the signal would leave a task that
    never stops — ECS would SIGKILL it, which is the opposite of draining.

    Handlers can only be installed from the main thread. Under TestClient the application
    runs in a worker thread, so the ValueError is expected there and ignored.
    """
    for signal_number in (signal.SIGTERM, signal.SIGINT):
        previous = signal.getsignal(signal_number)

        def chained(
            signum: int,
            frame: FrameType | None,
            previous=previous,  # bound now: the loop rebinds `previous` on its next turn
        ) -> None:
            handle_shutdown_signal(target)
            if callable(previous):
                previous(signum, frame)

        try:
            signal.signal(signal_number, chained)
        except ValueError:
            logger.debug("not on the main thread: no handler installed for %s", signal_number)


async def _drain(target: FastAPI) -> None:
    """Stop taking Salons and wait out the ones this instance holds."""
    registry: SalonRegistry = target.state.registry
    timeout = target.state.settings.drain_timeout_seconds

    if not registry.draining:
        logger.info("orchestrator draining: hosted=%d reason=shutdown", registry.hosted_count)
        registry.begin_drain()

    drained = await registry.wait_until_empty(timeout=timeout)

    if drained:
        logger.info("orchestrator stopped: drained cleanly")
    else:
        # Not a failure. Whatever is still hosted is persisted, and another instance picks
        # it up by re-reading storage — that is the whole point of affinity being a
        # preference rather than a condition of survival.
        logger.warning(
            "orchestrator stopped: %d salon(s) still hosted after %ds, they resume elsewhere",
            registry.hosted_count,
            timeout,
        )


async def _no_factory(salon_id: str) -> Salon:
    """What an application built without a factory does when asked to host a Salon.

    Raising rather than returning something empty. An application that accepted a Salon and
    then had nowhere to put what was said would answer every request cheerfully and lose the
    conversation, which is the failure that takes longest to notice.
    """
    raise RuntimeError(
        f"cannot host salon {salon_id}: this application was built with no salon factory. "
        "The composition root in app.py supplies the real one."
    )


def create_app(
    settings: Settings | None = None,
    settings_store: SettingsStore | None = None,
    salon_factory: Callable[..., Callable[[str], Salon]] | None = None,
) -> FastAPI:
    """Build the application.

    `settings` is normally left out, and then the configuration — credentials included —
    is resolved in the lifespan below. Passing one is for tests, which have no business
    reading a developer's environment to decide what the health endpoint answers.

    `settings_store` is the same arrangement for Story 7.1's parameters: left out, the
    instance opens the database named in the configuration, which is what production does
    and what makes an unreachable database a startup failure rather than a surprise later.

    `salon_factory` is what turns an identifier into a running conversation, and it is a
    parameter rather than an import because the real one names LiveKit. The composition root
    in `app.py` — outside `src/`, where a vendor may be named — supplies it. Left out, this
    application serves health and readiness and refuses to host anything, which is what the
    tests of the lifecycle itself want and all they want.
    """

    @asynccontextmanager
    async def lifespan(target: FastAPI):
        """Configure, announce, serve, drain.

        Configuration is resolved here rather than at import time so that a missing
        credential stops the process at startup, with the port never opened and the
        failure in the deployment's own log — not on somebody's first Salon.
        """
        resolved = settings if settings is not None else load_settings()
        configure_logging(resolved.log_level)

        target.state.settings = resolved
        target.state.registry = SalonRegistry()

        # Story 7.1. The operational parameters come from a table rather than the
        # environment, and are read here so a combination that could never work stops the
        # instance at startup rather than a week later. `LiveSettings` re-reads on an
        # interval, which is what lets a change reach a running fleet without a deploy.
        store = settings_store
        engine = None
        if store is None:
            engine = create_async_engine(async_url(resolved.database_url))
            store = SqlSettingsStore(engine)
            await store.create_all()
        target.state.salon_settings = LiveSettings(store=store)
        salon_settings = await target.state.salon_settings.get()

        # Nothing here names an adapter, and nothing here may: the domain does not know what
        # implements it. `salon_factory` arrives from the composition root in `app.py`,
        # which sits outside `src/` precisely so this file can stay ignorant of LiveKit.
        if salon_factory is None:
            target.state.build_salon = _no_factory
        else:
            # Configuration in, a callable out. The factory opens whatever it needs and
            # creates whatever tables it owns — this file does not know that it needs any,
            # which is the point of it arriving from outside `src/`.
            target.state.build_salon = await salon_factory(
                database_url=resolved.database_url,
                livekit_url=resolved.livekit_url,
                livekit_api_key=resolved.livekit_api_key,
                livekit_api_secret=resolved.livekit_api_secret,
                settings=salon_settings,
                api_base_url=resolved.api_base_url,
                orchestrator_callback_secret=resolved.orchestrator_callback_secret,
            )

        _install_shutdown_handlers(target)

        # Identifiers and numbers only — never a credential, never conversation content.
        logger.info(
            "orchestrator starting: version=%s environment=%s region=%s host=%s port=%d "
            "drain_timeout=%ds",
            VERSION,
            resolved.environment,
            resolved.aws_region,
            resolved.host,
            resolved.port,
            resolved.drain_timeout_seconds,
        )

        try:
            yield
        finally:
            await _drain(target)

    application = FastAPI(title="Salon Orchestrator", version=VERSION, lifespan=lifespan)

    @application.get(HEALTH_PATH)
    def health() -> dict[str, str]:
        """Liveness. Answers as long as the event loop turns — draining included."""
        return {"status": "ok", "component": COMPONENT, "version": VERSION}

    @application.get(READINESS_PATH)
    def readiness() -> JSONResponse:
        """Readiness. 503 while draining, so no new Salon reaches an instance on its way
        out."""
        registry: SalonRegistry = application.state.registry
        draining = registry.draining

        return JSONResponse(
            status_code=503 if draining else 200,
            content={
                "status": "draining" if draining else "ready",
                "draining": draining,
                "hostedSalons": registry.hosted_count,
            },
        )

    application.include_router(build_router())

    return application


# The domain application: health, readiness, and routes that refuse to host anything,
# because nothing here knows what a real journal or a real room is. `app.py` at the root is
# what wires those in, and what the container runs.
app = create_app()


if __name__ == "__main__":  # pragma: no cover - in the container uvicorn is the entry point
    import uvicorn

    # Read once, here, only to know where to bind. The application resolves its own
    # configuration again in the lifespan, which is where a missing credential must stop
    # the process.
    bootstrap = load_settings()
    uvicorn.run(
        "src.main:app",
        host=bootstrap.host,
        port=bootstrap.port,
        log_level=bootstrap.log_level.lower(),
    )
