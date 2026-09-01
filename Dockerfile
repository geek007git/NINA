# syntax=docker/dockerfile:1

# Build a slim runtime image for a LiveKit agent worker.
# Dependencies are installed in their own layer so that editing source code does
# not invalidate the (slow) dependency install.

FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    NINA_LOG_FORMAT=json \
    NINA_MEMORY_PATH=/app/.nina/memory.json

WORKDIR /app

# Run as a non-root user. Created before the copies so ownership is set once.
RUN useradd --create-home --uid 10001 nina

# Dependency layer.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Application layer.
COPY pyproject.toml README.md LICENSE agent.py ./
COPY src ./src
RUN pip install --no-cache-dir --no-deps -e . \
    && mkdir -p /app/.nina \
    && chown -R nina:nina /app

USER nina

# Pre-download model weights (turn detector, VAD) at build time rather than on
# the first call, which would otherwise show up as cold-start latency.
RUN nina download-files || echo "download-files unavailable for this configuration; skipping"

# Fails the build/deploy early if the image cannot even parse its own config.
HEALTHCHECK --interval=60s --timeout=10s --start-period=10s --retries=3 \
    CMD nina prompt > /dev/null || exit 1

ENTRYPOINT ["nina"]
CMD ["start"]
