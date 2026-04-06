#!/bin/sh
set -e

# ── Hunter888 API Entrypoint ─────────────────────────────────────────
# Runs DB migrations (with retry + rollback safety), then starts gunicorn.
# Used by Docker production builds.

cd /app

log() {
    echo "[$(date -Iseconds)] $*"
}

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

# ── Alembic migrations ───────────────────────────────────────────────
# Record current revision so we can rollback on failure
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
