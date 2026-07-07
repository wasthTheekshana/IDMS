# Runbook: OCR Provider (Mistral) Outage

**Symptom:** `run_ocr` tasks failing with 5xx/timeout from Mistral;
documents accumulating in `processing`; ocr queue depth rising.

## Diagnose

1. Worker logs: `docker compose -f infra/docker-compose.yml logs worker --tail 100 | grep -i ocr`
2. Check https://status.mistral.ai for a declared incident.
3. Rule out our side: is `MISTRAL_API_KEY` valid (401 vs 5xx)? Did we
   hit a rate/spend limit (429)?

## Fix

- **Transient blip:** nothing to do — tasks retry with exponential
  backoff (30s \* 2^n) and `heal_stuck_documents` re-dispatches strays.
- **Extended outage:** pause intake if needed (announce in status
  channel). Queued OCR tasks are durable in Redis; they will drain when
  the provider recovers. Do NOT purge the ocr queue.
- **Key/billing problem:** rotate per
  [secret-rotation.md](secret-rotation.md), then restart worker.

## Verify

Upload a one-page test PDF; confirm it reaches `indexed`. Queue depth
drains. Note incident duration + affected document count.
