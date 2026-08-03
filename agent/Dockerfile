FROM python:3.12-slim

WORKDIR /app

# Install uv for fast dependency resolution
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Copy dependency files first for layer caching
COPY pyproject.toml .

# Install dependencies (no virtual env needed inside container)
#
# No turn-detector extra: end-of-turn detection moved to livekit.agents.inference, which
# runs on LiveKit's service and needs nothing installed here. The extra pulled in
# transformers and wanted PyTorch — hundreds of megabytes for a model that is no longer
# loaded.
RUN uv pip install --system "livekit-agents[xai,silero]>=1.5.0" python-dotenv

# Silero VAD is still very much in use (see vad= in agent.py) and is a local model, so it
# is fetched at build time rather than on every cold start. Deliberately not removed
# alongside the turn detector: the two are different models with different fates.
RUN python -c "from livekit.plugins import silero; silero.VAD.load()" || true

# Copy source
COPY agent.py .
COPY src/ src/

ENV PYTHONUNBUFFERED=1

CMD ["python", "agent.py", "start"]
