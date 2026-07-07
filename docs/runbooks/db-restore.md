# Runbook: Database Restore

**When:** data corruption, bad migration, accidental deletion, or DR.

## Prerequisites

- `BACKUP_PASSPHRASE` from the secret store (NOT in the repo).
- R2 backup-bucket credentials (separate from app credentials).
- `aws` CLI v2 and `openssl` on the operator machine.
- Docker compose stack reachable.

## Steps

1. List available backups:
   `aws s3 ls s3://<backup-bucket>/postgres/ --endpoint-url <r2-endpoint>`
2. Restore into a scratch DB first — never straight over production:
   `bash infra/scripts/restore.sh <backup-file> idms_restore_check`
3. Sanity-check the scratch DB (row counts on organizations/documents,
   spot-check a recent document).
4. To promote: stop `api`, `worker`, `beat`; restore into `idms`
   (`bash infra/scripts/restore.sh <backup-file> idms`); run
   `make migrate`; restart services; run smoke test (login + list docs).
5. Announce completion; note data-loss window (time since backup).

## Scheduling

On the production host, schedule `infra/scripts/backup.sh` nightly at
02:00 via cron (Linux) or Task Scheduler (Windows), with the required
env vars sourced from the secret store.

## Retention

30-day retention is enforced by an R2 lifecycle rule on the backup
bucket (Cloudflare dashboard → R2 → bucket → Settings → Lifecycle).
Verify the rule exists when rotating buckets.

## Drill log

| Date       | Backup file                             | Tables restored | Duration | Operator               | Notes                                                                                                                                                |
| ---------- | --------------------------------------- | --------------- | -------- | ---------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- |
| 2026-07-07 | idms-backup-20260707T080305Z.sql.gz.enc | 9               | < 1 min  | Claude (Stage A build) | Local drill: dump → AES-256 encrypt → restore into `idms_restore_drill`. R2 upload leg pending: install AWS CLI + provision dedicated backup bucket. |
