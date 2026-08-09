"""The composition root: where the domain meets the things that implement it.

Three lines, and they are the reason `src/` can be read without knowing that LiveKit exists.
The guard in `test_interprete_port.py` fails the build on `import adapters` anywhere under
`src/`, so the wiring cannot live there — it has to be done by whoever starts the process,
which is this file.

The container runs `app:app`. Anything importing `src.main:app` gets an application that
serves health and readiness and refuses to host a Salon, which is correct: an application
with no factory has nowhere to put what is said, and saying so at the first request is
better than accepting one and losing the conversation.
"""
from __future__ import annotations

from adapters.salon_factory import build_salon_factory
from src.main import create_app

app = create_app(salon_factory=build_salon_factory)


if __name__ == "__main__":  # pragma: no cover — in the container uvicorn is the entry point
    import uvicorn

    from src.config import load_settings

    # Read once, only to know where to bind. The application resolves its own configuration
    # again in the lifespan, which is where a missing credential must stop the process.
    bootstrap = load_settings()
    uvicorn.run(
        "app:app",
        host=bootstrap.host,
        port=bootstrap.port,
        log_level=bootstrap.log_level.lower(),
    )
