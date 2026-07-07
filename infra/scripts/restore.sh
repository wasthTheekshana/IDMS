#!/usr/bin/env bash
# Restore an encrypted backup into a target database.
# Usage: restore.sh <backup-file.sql.gz.enc> [target_db]
# Required env: BACKUP_PASSPHRASE. Downloads from R2 if the file
# is not local: set BACKUP_BUCKET + R2_ENDPOINT + AWS creds.
set -euo pipefail

: "${BACKUP_PASSPHRASE:?set BACKUP_PASSPHRASE}"
FILE="${1:?usage: restore.sh <backup-file> [target_db]}"
TARGET_DB="${2:-idms_restore_drill}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="${COMPOSE_FILE:-$SCRIPT_DIR/../docker-compose.yml}"

if [ ! -f "$FILE" ]; then
  aws s3 cp "s3://${BACKUP_BUCKET}/postgres/${FILE}" "$FILE" \
    --endpoint-url "$R2_ENDPOINT"
fi

docker compose -f "$COMPOSE_FILE" exec -T postgres \
  psql -U idms_app -d postgres \
  -c "DROP DATABASE IF EXISTS ${TARGET_DB};" \
  -c "CREATE DATABASE ${TARGET_DB};"

openssl enc -d -aes-256-cbc -pbkdf2 \
    -pass env:BACKUP_PASSPHRASE -in "$FILE" \
  | gunzip \
  | docker compose -f "$COMPOSE_FILE" exec -T postgres \
      psql -U idms_app -d "$TARGET_DB" --quiet

COUNT=$(docker compose -f "$COMPOSE_FILE" exec -T postgres \
  psql -U idms_app -d "$TARGET_DB" -tAc \
  "SELECT count(*) FROM information_schema.tables WHERE table_schema='public';")
echo "OK: restored into ${TARGET_DB} — ${COUNT} tables"
