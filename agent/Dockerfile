FROM python:3.12-slim

WORKDIR /app

# Install uv for fast dependency resolution
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Copy dependency files first for layer caching
COPY pyproject.toml .

# Install dependencies (no virtual env needed inside container)
RUN uv pip install --system "livekit-agents[xai,silero,turn-detector]>=1.5.0" python-dotenv

# Download model files at build time to avoid cold-start latency
RUN python -c "from livekit.plugins import silero; silero.VAD.load()" || true

# Copy source
COPY agent.py .
COPY src/ src/

ENV PYTHONUNBUFFERED=1

CMD ["python", "agent.py", "start"]
