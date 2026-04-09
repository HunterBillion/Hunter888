# ── Development stage ─────────────────────────────────────────────────
FROM python:3.12-slim AS development

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml .
RUN uv pip install --system -e ".[dev]"

COPY . .

CMD ["uvicorn", "app.main:app", "--reload", "--host", "0.0.0.0", "--port", "8000"]

# ── Production stage ─────────────────────────────────────────────────
FROM python:3.12-slim AS production

# Security: install deps as root, then drop privileges
WORKDIR /app

RUN pip install --no-cache-dir uv \
    && groupadd -r appuser && useradd -r -g appuser -d /app -s /sbin/nologin appuser \
    && mkdir -p /app/uploads && chown -R appuser:appuser /app

COPY pyproject.toml .
RUN uv pip install --system .

COPY --chown=appuser:appuser . .

# Run migrations on startup, then start gunicorn
COPY --chown=appuser:appuser docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

# Drop to non-root user
USER appuser

EXPOSE 8000

ENTRYPOINT ["/docker-entrypoint.sh"]

# Worker count: configurable via WEB_CONCURRENCY env var
# Pilot: 2 workers (pool 50+20=70 × 2 = 140 < 200 max_connections)
# Production: 4 workers (needs PgBouncer for >50 concurrent users)
# --timeout 120: allow long WebSocket training sessions
# --graceful-timeout 30: wait 30s for WS connections to close on deploy
ENV WEB_CONCURRENCY=2
ENV PYTHONPATH=/app

CMD ["gunicorn", "app.main:app", "-k", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:8000", "--timeout", "120", "--graceful-timeout", "30", "--access-logfile", "-"]
