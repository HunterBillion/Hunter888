#!/bin/sh
set -e

# Run DB migrations before starting the app (Docker deployment)
cd /app
echo "Running Alembic migrations..."
python -m alembic upgrade head || {
    echo "Migration failed (DB may not be ready). Retrying in 5s..."
    sleep 5
    python -m alembic upgrade head
}

echo "Starting API..."
exec "$@"
