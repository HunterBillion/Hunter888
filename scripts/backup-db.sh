#!/bin/sh
# Hunter888 — PostgreSQL backup script
# Runs daily via cron in the backup container (docker-compose.prod.yml)
# Retention: configurable via BACKUP_RETENTION_DAYS env var (default: 30)
#
# Manual run:
#   docker compose -f docker-compose.yml -f docker-compose.prod.yml \
#     run --rm backup /backup-db.sh

set -e

BACKUP_DIR="/backups"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-30}"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
FILENAME="hunter888_${TIMESTAMP}.sql.gz"

echo "[$(date -Iseconds)] Starting backup: ${FILENAME}"

# Create backup directory if needed
mkdir -p "${BACKUP_DIR}"

# Dump + compress (using env vars from docker-compose)
pg_dump \
  --host="${PGHOST}" \
  --username="${PGUSER}" \
  --dbname="${PGDATABASE}" \
  --format=custom \
  --compress=6 \
  --no-owner \
  --no-privileges \
  --verbose \
  > "${BACKUP_DIR}/${FILENAME}" 2>/dev/null

# Verify backup is not empty
FILESIZE=$(stat -c%s "${BACKUP_DIR}/${FILENAME}" 2>/dev/null || stat -f%z "${BACKUP_DIR}/${FILENAME}" 2>/dev/null)
if [ "${FILESIZE}" -lt 1024 ]; then
  echo "[$(date -Iseconds)] ERROR: Backup file too small (${FILESIZE} bytes), possible failure"
  rm -f "${BACKUP_DIR}/${FILENAME}"
  exit 1
fi

echo "[$(date -Iseconds)] Backup complete: ${FILENAME} ($(echo "${FILESIZE}" | awk '{printf "%.1f MB", $1/1048576}'))"

# Cleanup old backups
DELETED=$(find "${BACKUP_DIR}" -name "hunter888_*.sql.gz" -mtime "+${RETENTION_DAYS}" -print -delete | wc -l)
if [ "${DELETED}" -gt 0 ]; then
  echo "[$(date -Iseconds)] Cleaned up ${DELETED} backups older than ${RETENTION_DAYS} days"
fi

echo "[$(date -Iseconds)] Backup rotation complete. Active backups:"
ls -lh "${BACKUP_DIR}"/hunter888_*.sql.gz 2>/dev/null | tail -5
