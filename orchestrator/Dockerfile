# syntax=docker/dockerfile:1
FROM python:3.12-slim

WORKDIR /app

# uv for dependency resolution, as in agent/Dockerfile — one toolchain across the Python
# components rather than pip here and uv there.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Dependencies first, so a source change does not reinstall them.
COPY pyproject.toml uv.lock ./
RUN uv export --frozen --no-dev --no-emit-project -o requirements.txt \
    && uv pip install --system -r requirements.txt \
    && rm requirements.txt

COPY src/ src/

# Unbuffered, or a crash loses the last lines — which are the ones that say why.
ENV PYTHONUNBUFFERED=1
ENV PORT=8080

EXPOSE 8080

# Nothing to gain from more than one worker: the state of a hosted Salon lives in the
# process, and a second worker would be a second, unrelated instance sharing a port.
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8080"]
