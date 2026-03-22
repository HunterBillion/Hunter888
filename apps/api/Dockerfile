# Development stage
FROM python:3.12-slim AS development

WORKDIR /app

RUN pip install uv

COPY pyproject.toml .
RUN uv pip install --system -e ".[dev]"

COPY . .

CMD ["uvicorn", "app.main:app", "--reload", "--host", "0.0.0.0", "--port", "8000"]

# Production stage
FROM python:3.12-slim AS production

WORKDIR /app

RUN pip install uv

COPY pyproject.toml .
RUN uv pip install --system .

COPY . .

# Run migrations on startup, then start gunicorn
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh
ENTRYPOINT ["/docker-entrypoint.sh"]

EXPOSE 8000

# FIX: Use gunicorn with uvicorn workers for proper process management in production.
# gunicorn handles worker lifecycle (restart on OOM, graceful shutdown) unlike bare uvicorn.
# --timeout 120: allow long WebSocket training sessions
# --graceful-timeout 30: wait 30s for WS connections to close on deploy
CMD ["gunicorn", "app.main:app", "-w", "4", "-k", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:8000", "--timeout", "120", "--graceful-timeout", "30", "--access-logfile", "-"]
