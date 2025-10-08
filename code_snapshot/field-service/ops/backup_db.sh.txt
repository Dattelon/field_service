#!/usr/bin/env bash
set -euo pipefail

: "${DATABASE_URL:?DATABASE_URL is not set}"

TS=$(date -u +"%Y%m%d_%H%M%SZ")
BACKUP_DIR=${BACKUP_DIR:-backups}
mkdir -p "$BACKUP_DIR"
pg_dump -Fc -d "$DATABASE_URL" > "${BACKUP_DIR}/pg_${TS}.dump"
find "$BACKUP_DIR" -type f -name 'pg_*.dump' -mtime +7 -delete
