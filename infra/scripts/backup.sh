#!/usr/bin/env bash
# Nightly encrypted Postgres backup -> R2.
# Required env: BACKUP_PASSPHRASE, BACKUP_BUCKET, R2_ENDPOINT,
#               AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY
set -euo pipefail

: "${BACKUP_PASSPHRASE:?set BACKUP_PASSPHRASE}"
: "${BACKUP_BUCKET:?set BACKUP_BUCKET}"
: "${R2_ENDPOINT:?set R2_ENDPOINT}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="${COMPOSE_FILE:-$SCRIPT_DIR/../docker-compose.yml}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="idms-backup-${STAMP}.sql.gz.enc"

RAW="$(mktemp)"
trap 'rm -f "$RAW" "$OUT"' EXIT

docker compose -f "$COMPOSE_FILE" exec -T postgres \
  pg_dump -U idms_app -d idms --no-owner > "$RAW"

# Refuse to upload an implausibly small dump (the schema alone is
# well over 8 KB uncompressed; smaller means pg_dump silently failed).
RAW_SIZE=$(wc -c < "$RAW")
if [ "$RAW_SIZE" -lt 8192 ]; then
  echo "ERROR: raw dump only ${RAW_SIZE} bytes — refusing to upload" >&2
  exit 1
fi

gzip -c "$RAW" \
  | openssl enc -aes-256-cbc -pbkdf2 -salt \
      -pass env:BACKUP_PASSPHRASE -out "$OUT"
SIZE=$(wc -c < "$OUT")

aws s3 cp "$OUT" "s3://${BACKUP_BUCKET}/postgres/${OUT}" \
  --endpoint-url "$R2_ENDPOINT"
echo "OK: uploaded postgres/${OUT} (${SIZE} bytes encrypted, ${RAW_SIZE} raw)"
