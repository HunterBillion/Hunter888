#!/bin/sh
set -e

# ── Hunter888 API Entrypoint ─────────────────────────────────────────
# Runs DB migrations (with retry + rollback safety), then starts gunicorn.
# Used by Docker production builds.

cd /app

log() {
    echo "[$(date -Iseconds)] $*"
}

# ── Security pre-flight (2026-04-18, FIND-002) ───────────────────────
# Refuse to start with default or placeholder secrets in production.
# Local dev (APP_ENV != production) may keep placeholders for convenience.
if [ "${APP_ENV:-development}" = "production" ]; then
    _DEFAULT_JWT="4ec3d26de8b0623fe427d7d28c684d57d0dfad80acaab0785d5bfca839878ca2"
    if [ "${JWT_SECRET:-}" = "${_DEFAULT_JWT}" ] || [ -z "${JWT_SECRET:-}" ]; then
        log "FATAL: JWT_SECRET is empty or set to default value. Generate a new one: openssl rand -hex 32"
        exit 1
    fi
    if [ "${#JWT_SECRET}" -lt 32 ]; then
        log "FATAL: JWT_SECRET must be at least 32 characters in production"
        exit 1
    fi
    case "${POSTGRES_PASSWORD:-}" in
        ""|"trainer_pass"|"postgres"|"password"|"123456")
            log "FATAL: POSTGRES_PASSWORD is empty or using a known weak/default value"
            exit 1
            ;;
    esac
    case "${REDIS_PASSWORD:-}" in
        ""|"redis_secret_pass"|"redis"|"password"|"123456")
            log "FATAL: REDIS_PASSWORD is empty or using a known weak/default value"
            exit 1
            ;;
    esac
    if [ "${APP_DEBUG:-false}" = "true" ]; then
        log "FATAL: APP_DEBUG=true in production — Swagger UI and debug traces would be exposed"
        exit 1
    fi
    log "Security pre-flight: OK (strong secrets, debug off)"
fi

# ── Graceful shutdown ──────────────────────────────────────────────────
# Forward SIGTERM to child process (gunicorn) for clean shutdown
cleanup() {
    log "Received shutdown signal. Forwarding to PID $CHILD_PID..."
    kill -TERM "$CHILD_PID" 2>/dev/null
    wait "$CHILD_PID"
    exit $?
}
trap cleanup TERM INT

# ── Pre-flight checks ────────────────────────────────────────────────
log "Checking database connectivity..."
MAX_RETRIES=10
RETRY=0
while ! python -c "
import asyncio, asyncpg, os
async def check():
    url = os.environ.get('DATABASE_URL', '').replace('+asyncpg', '')
    if not url: url = 'postgresql://trainer:trainer_pass@postgres:5432/trainer_db'
    conn = await asyncpg.connect(url)
    await conn.close()
asyncio.run(check())
" 2>/dev/null; do
    RETRY=$((RETRY + 1))
    if [ "$RETRY" -ge "$MAX_RETRIES" ]; then
        log "ERROR: Database not reachable after $MAX_RETRIES attempts"
        exit 1
    fi
    log "Waiting for database... (attempt $RETRY/$MAX_RETRIES)"
    sleep 3
done

log "Database is ready."

# ── DB schema setup ───────────────────────────────────────────────────
# On a fresh DB: bypass the broken alembic chain (several migrations
# reference tables/columns from commits that were dropped from history).
# Use SQLAlchemy Base.metadata.create_all() to reflect current intended
# schema, then stamp alembic to head for future migrations.
# On existing DB: run normal alembic upgrade.

IS_FRESH=$(python -c "
import asyncio, asyncpg, os
async def check():
    url = os.environ.get('DATABASE_URL', '').replace('+asyncpg', '')
    if not url: url = 'postgresql://trainer:trainer_pass@postgres:5432/trainer_db'
    conn = await asyncpg.connect(url)
    try:
        r = await conn.fetchval(\"SELECT to_regclass('public.alembic_version')\")
        print('yes' if r is None else 'no')
    finally:
        await conn.close()
asyncio.run(check())
" 2>/dev/null)

if [ "$IS_FRESH" = "yes" ]; then
    log "Fresh DB — creating schema via SQLAlchemy (bypass broken migration chain)..."
    if ! python -c "
import asyncio
from sqlalchemy import text, Enum as SAEnum
from app.database import engine, Base
import app.models  # noqa: F401 — register all models on Base

async def setup():
    async with engine.begin() as conn:
        # pgvector extension (needed for Vector(768) columns in rag/wiki/legal)
        await conn.execute(text('CREATE EXTENSION IF NOT EXISTS vector'))

        # Create all ENUM types up-front. Some models declare them with
        # create_type=False (assuming alembic would create them), some
        # duplicate-declare across columns. We walk metadata, collect every
        # unique enum name, and create each idempotently.
        seen = set()
        for tbl in Base.metadata.tables.values():
            for col in tbl.columns:
                t = col.type
                if isinstance(t, SAEnum) and t.name and t.name not in seen:
                    seen.add(t.name)
                    values = ', '.join(\"'\" + v.replace(\"'\", \"''\") + \"'\" for v in t.enums)
                    await conn.execute(text(
                        f\"DO \$\$ BEGIN CREATE TYPE {t.name} AS ENUM ({values}); \"
                        f\"EXCEPTION WHEN duplicate_object THEN NULL; END \$\$;\"
                    ))
        print(f'[schema-init] Ensured {len(seen)} enum types')

        # Now create all tables
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()

asyncio.run(setup())
"; then
        log "ERROR: Schema creation failed."
        exit 1
    fi
    log "Schema created. Stamping alembic to head..."
    if ! python -m alembic stamp heads; then
        log "ERROR: alembic stamp heads failed."
        exit 1
    fi
    log "DB ready (schema from models, alembic stamped at head)."
else
    CURRENT_REV=$(python -m alembic current 2>/dev/null | grep -oE '[a-f0-9]{12}' | head -1 || echo "")
    log "Running Alembic migrations (current: ${CURRENT_REV:-none})..."
    if ! python -m alembic upgrade head; then
        log "ERROR: Migration failed!"
        if [ -n "$CURRENT_REV" ]; then
            log "Rolling back to previous revision: $CURRENT_REV"
            python -m alembic downgrade "$CURRENT_REV" || {
                log "CRITICAL: Rollback also failed. Manual intervention required."
                exit 1
            }
            log "Rollback complete. Starting with previous schema version."
        else
            log "No previous revision to rollback to. Exiting."
            exit 1
        fi
    fi
    log "Migrations complete."
fi

# ── Seed database ─────────────────────────────────────────────────────
# Idempotent: seed_db.py checks if data exists before inserting.
log "Running database seed (idempotent)..."
if python -m scripts.seed_db; then
    log "Seed complete."
else
    log "WARNING: Seed script failed (non-critical, continuing startup)."
fi

log "Starting API..."

# Start the application in background and track PID for graceful shutdown
"$@" &
CHILD_PID=$!
wait "$CHILD_PID"
