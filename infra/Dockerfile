# =============================================================================
# BrokenLinkBrief — Production Dockerfile (multi-stage)
# =============================================================================
# Runtime requirements:
#   - Python 3.11+
#   - No C extensions (stdlib-based HTTP server)
#
# Environment variables (set at deploy time):
#   PORT                        — Bind port (default: 8000)
#   BROKENLINKBRIEF_SCAN_TOKEN  — Bearer token for API auth (if enabled)
#   BROKENLINKBRIEF_LOG_FILE    — Path to JSONL log file
# =============================================================================

# ─── Builder stage: install Python packages ───────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build

# Copy dependency files
COPY pyproject.toml README.md ./
COPY src ./src

# Install the package (pulls all [project] dependencies)
RUN pip install --no-cache-dir .


# ─── Runtime stage: slim image with only what's needed ────────────────────────
FROM python:3.11-slim

# Copy installed Python packages from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

WORKDIR /app

# Copy application code
COPY src ./src

# Non-root user
RUN useradd --create-home --shell /bin/bash app \
    && chown -R app:app /app
USER app

# Expose default port (overridden at deploy time via PORT env var)
EXPOSE 8000

# Run the stdlib HTTP server.
# Respect Railway's PORT env var; fall back to 8000 for local runs.
CMD ["sh", "-c", "python -m brokenlinkbrief.app"]
