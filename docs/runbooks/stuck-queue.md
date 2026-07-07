# Runbook: Stuck Celery Queue

**Symptom:** documents stay in `processing`/`ready`; Sentry warning
"Celery queue depth over ..." from `monitor_queue_depths`; or the
`queue_depth_check` log line shows a growing number.

## Diagnose

1. Depths: `docker compose -f infra/docker-compose.yml exec redis redis-cli llen ocr`
   (repeat for `embed`, `ai`, `default`, `dlq`).
2. Worker alive? `docker compose -f infra/docker-compose.yml logs worker --tail 50`
3. Worker responsive? `docker compose -f infra/docker-compose.yml exec worker uv run celery -A app.workers.celery_app inspect ping`

## Fix

- Worker crashed → `docker compose -f infra/docker-compose.yml restart worker`,
  then watch depth drain.
- Tasks failing repeatedly → read the traceback in worker logs. Provider
  outage → see [ocr-provider-outage.md](ocr-provider-outage.md). Code bug →
  hotfix; tasks retry with exponential backoff automatically
  (`task_acks_late=True` means no loss).
- Stuck documents that missed their embed chain are re-dispatched
  automatically every 2 min by `heal_stuck_documents` — give it one cycle
  before intervening manually.

## Verify

Queue depths near 0; a fresh test upload reaches `indexed` status.
