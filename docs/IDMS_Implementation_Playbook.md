# Intelligent Document Management System (IDMS)
## Implementation Playbook — Build-Ready Development Guide

**Version:** 1.0
**Date:** June 2026
**Derived from:** v1 System Design + v2 Best Practices / Bottlenecks / Gap Analysis
**Audience:** Engineering team starting development
**Scope:** Detailed, ordered, build-ready plan for Stage 1 (MVP → first paying pilots), with Stage 2–3 outlined

---

# How to Use This Document

This is the executable version of the two design documents. Each phase below has the same shape:

- **Goal** — what "done" achieves
- **Prerequisites** — what must exist first
- **Backlog** — concrete tasks as checkable stories
- **Implementation notes** — the patterns that are easy to get wrong (cross-referenced to v2 bottlenecks)
- **Testing** — what proves it works
- **Definition of Done (DoD)** — the gate to the next phase

References like *(B4.2)* point to the bottleneck of that number in the v2 document; *(BP3.x)* points to a best practice. Do not start a phase until the previous phase's DoD is met.

**Total Stage-1 timeline:** ~8 weeks for 1–2 full-stack engineers. Phases are mostly sequential; the Chrome extension (Phase 5) can run in parallel from Phase 3 onward.

---

# 0. Project Conventions (Read First)

## 0.1 Repository Structure (Monorepo)

```
idms/
├── api/                      # FastAPI backend
│   ├── app/
│   │   ├── core/             # config, security, db, logging, telemetry
│   │   ├── models/           # SQLAlchemy models
│   │   ├── schemas/          # Pydantic request/response
│   │   ├── api/v1/           # routers (auth, documents, search, chat, admin)
│   │   ├── services/         # business logic (ocr, embed, search, rag, billing)
│   │   ├── workers/          # Celery tasks + queues
│   │   ├── repositories/     # DB access (org-context enforced)
│   │   └── main.py
│   ├── migrations/           # Alembic
│   ├── tests/
│   │   ├── unit/
│   │   ├── integration/
│   │   └── security/         # tenant-isolation suite (blocking in CI)
│   └── pyproject.toml
├── web/                      # Next.js app (App Router)
│   ├── app/
│   ├── components/
│   ├── lib/                  # api client, auth, sse
│   └── package.json
├── extension/                # Chrome MV3
│   ├── src/
│   └── manifest.json
├── infra/
│   ├── docker-compose.yml    # local dev
│   ├── docker-compose.prod.yml
│   └── scripts/              # backup, restore, seed
├── .github/workflows/        # CI
├── docs/                     # ADRs, runbooks, this playbook
└── Makefile
```

## 0.2 Branching & Workflow
- `main` is always deployable. Feature branches → PR → CI must pass → review → squash-merge.
- **CI is blocking** for: lint, type-check, unit + integration tests, and the **security/tenant-isolation suite** *(BP3.3)*.
- Conventional commits; tag releases (`v0.1.0`).

## 0.3 Environments
| Env | Purpose | Data |
|---|---|---|
| local | dev via docker-compose | seed/fake |
| staging | mirrors prod, pre-release testing | anonymized |
| production | live | real (encrypted, backed up) |

## 0.4 Accounts & Keys to Provision Before Phase 0
- Domain + Cloudflare account (DNS, WAF, TLS).
- Cloudflare **R2** bucket + API token.
- **Mistral** API key (OCR).
- **Google AI / Gemini** API key.
- VPS or managed host (Hetzner/DigitalOcean) — start with one 4 GB node + managed Postgres if budget allows.
- Sentry account (free tier).
- GitHub repo + Actions enabled.

Store all secrets in the CI secret store and a `.env` excluded from git. Separate keys for dev/staging/prod *(BP3.5)*.

---

# Phase 0 — Foundation (Week 1)

**Goal:** A new developer clones the repo, runs one command, and has the full stack running locally with HTTPS-ready config and green CI.

## Prerequisites
Accounts from §0.4 provisioned.

## Backlog
- [ ] Initialize monorepo with the structure in §0.1.
- [ ] `infra/docker-compose.yml` with services: `postgres` (pgvector image), `redis`, `api`, `worker`.
- [ ] `.env.example` documenting every variable (no real secrets).
- [ ] Alembic initialized; empty baseline migration runs.
- [ ] FastAPI app with `/healthz` (liveness) and `/readyz` (checks DB + Redis) *(BP3.5)*.
- [ ] Celery app wired to Redis with **four queues**: `ocr`, `embed`, `ai`, `default` *(B4.4, BP3.2)*.
- [ ] Structured JSON logging + Sentry SDK initialized in API and worker.
- [ ] Next.js app scaffold with health page and API client lib.
- [ ] `Makefile`: `make up`, `make down`, `make test`, `make migrate`, `make seed`, `make lint`.
- [ ] GitHub Actions: lint → type-check → unit tests → integration tests (with a real Postgres service) → security tests. All blocking.
- [ ] Pre-commit hooks: ruff/black (Python), eslint/prettier (web), `bandit`, `npm audit`.

## Implementation notes

**docker-compose.yml (local) — shape:**
```yaml
services:
  postgres:
    image: pgvector/pgvector:pg16
    environment: { POSTGRES_DB: idms, POSTGRES_PASSWORD: dev }
    ports: ["5432:5432"]
    volumes: ["pgdata:/var/lib/postgresql/data"]
  redis:
    image: redis:7-alpine
    command: ["redis-server", "--appendonly", "yes"]
  api:
    build: ../api
    env_file: ../.env
    depends_on: [postgres, redis]
    ports: ["8000:8000"]
  worker:
    build: ../api
    command: celery -A app.workers.celery_app worker -Q ocr,embed,ai,default -c 4
    env_file: ../.env
    depends_on: [postgres, redis]
volumes: { pgdata: {} }
```

**CI Postgres must be the pgvector image** — RLS and vector features cannot be tested against SQLite *(B4.1, BP3.3)*.

## Testing
- `make up` brings the stack up; `/healthz` and `/readyz` return 200.
- CI green on an empty PR.

## Definition of Done
One-command local startup works; CI pipeline green and blocking; secrets never in git; both `/healthz` and `/readyz` live.

---

# Phase 1 — Auth & Multi-Tenancy (Week 2)

**Goal:** Secure login with organizations, roles, and **database-enforced tenant isolation** proven by an automated CI test. This is the highest-risk foundation in the whole product.

## Prerequisites
Phase 0 DoD met.

## Backlog
- [ ] Models + migrations: `organizations`, `users`, `audit_logs` (from v1 schema).
- [ ] Dedicated DB roles: `idms_app` (not table owner) and `idms_migrator` (owner, migrations only) *(BP3.3)*.
- [ ] Enable `ROW LEVEL SECURITY` + `FORCE ROW LEVEL SECURITY` + `org_isolation` policy on every tenant table.
- [ ] Argon2id password hashing; password policy (min 10 chars, zxcvbn breach check).
- [ ] JWT access tokens (15 min, RS256) + opaque refresh tokens (7 day, hashed in Redis, **rotated on use**, revocable).
- [ ] `get_db` dependency that sets `SET LOCAL app.current_org_id` from the verified JWT per transaction *(B4.7, BP3.3)*.
- [ ] Repository layer: all tenant queries go through it; raw cross-org queries forbidden by review rule.
- [ ] Endpoints: register (creates org + owner), login, refresh, logout, MFA setup (TOTP, optional).
- [ ] Account lockout (5 fails → 15 min) + audit logging of auth events.
- [ ] Rate limiting (slowapi + Redis): per-IP and per-user.
- [ ] Roles: owner / admin / member / viewer with dependency-based authorization.
- [ ] Next.js: register, login, dashboard shell; tokens in HttpOnly Secure SameSite=Strict cookies *(never localStorage)*.

## Implementation notes

**The org-context dependency (the single most important pattern):**
```python
async def get_db(user=Depends(get_current_user)):
    async with SessionLocal() as session:
        await session.execute(
            text("SET LOCAL app.current_org_id = :oid"),
            {"oid": str(user.org_id)},
        )
        yield session
```
`SET LOCAL` (transaction-scoped) is mandatory — a plain `SET` leaks org context across pooled connections to the next tenant's request *(B4.7)*.

**RLS policy (per tenant table):**
```sql
ALTER TABLE documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE documents FORCE ROW LEVEL SECURITY;
CREATE POLICY org_isolation ON documents FOR ALL
  USING (org_id = current_setting('app.current_org_id', true)::uuid)
  WITH CHECK (org_id = current_setting('app.current_org_id', true)::uuid);
```

## Testing — the gate that protects the business
- **Tenant-isolation suite** (`tests/security/`): create two orgs, each with a document; assert User B gets **404 (not 403)** on every read/write/delete of User A's resources, and that B's list/search never contain A's data. This test is **blocking in CI from now on** *(BP3.3)*.
- Auth tests: lockout, refresh rotation, expired/invalid tokens, role enforcement.

## Definition of Done
Login works; cross-tenant isolation test green; account lockout, refresh rotation, and audit logging verified; RLS active with `FORCE` on all tenant tables.

---

# Phase 2 — Upload & OCR Pipeline (Weeks 3–4)

**Goal:** A user uploads any supported document and reliably gets clean extracted text, with idempotent processing, quota enforcement, and real-time progress.

## Prerequisites
Phase 1 DoD met.

## Backlog
- [ ] Models + migrations: `documents`, `api_usage`; add quota fields to `organizations`.
- [ ] **Presigned R2 upload** flow: client requests URL → uploads direct to R2 → confirms → API verifies object, computes SHA-256, checks quota *(BP3.1)*.
- [ ] File validation: MIME allowlist by **magic bytes** (not extension), max 50 MB / 1,000 pages.
- [ ] **ClamAV** scan in the worker before OCR.
- [ ] Idempotency: tasks keyed on `document_id + stage`; check "already done" before paid work *(BP3.2)*.
- [ ] OCR service behind an interface (`OcrProvider`) with a **Mistral** implementation + a **PaddleOCR fallback** stub *(B4.3)*.
- [ ] **Batch API** path for multi-document/bulk uploads (half price, async) *(B4.3)*.
- [ ] **Layout-aware chunking** of Mistral markdown output (split on headings/tables/paragraphs; ~500 tokens, 50 overlap; keep page numbers) *(BP3.4)*.
- [ ] Status machine: `uploaded → processing → ocr_done → indexed → ready → failed`; `error_message` on failure.
- [ ] Retries with exponential backoff + jitter → **dead-letter queue** + alert *(BP3.2)*.
- [ ] **Per-tenant quota meter** enforced before each paid call; record pages + cost in `api_usage` *(B4.3)*.
- [ ] **Large-file handling**: process by page-range/segment, checkpoint progress, cap concurrent large jobs *(B4.5)*.
- [ ] **SSE** endpoint for live status; UI upload screen with progress *(B4.8)*.
- [ ] Separate worker pools so OCR doesn't block interactive jobs *(B4.4)*.

## Implementation notes

**OCR provider interface (enables fallback + future swap):**
```python
class OcrProvider(Protocol):
    async def extract(self, file_key: str, pages: range | None = None) -> OcrResult: ...

# MistralOcr(OcrProvider) — primary
# PaddleOcr(OcrProvider) — fallback / no-third-party tier
```
A **circuit breaker** wraps the primary: after N consecutive failures, fail fast and either fall back or DLQ for later replay *(B4.3)*.

**Idempotency guard inside the task:**
```python
@celery.task(queue="ocr", bind=True, max_retries=5)
def run_ocr(self, document_id):
    doc = get_document(document_id)
    if doc.status in ("ocr_done", "indexed", "ready"):
        return  # already processed — no double charge
    ...
```

**Quota check happens before the API call**, atomically (row lock or conditional update) to avoid concurrent uploads overrunning the limit *(B4.3)*.

## Testing
- Integration: upload PDF + scanned image + DOCX → text extracted and chunked with page numbers (Mistral mocked).
- Idempotency: re-running a task does not re-charge or duplicate chunks.
- Failure: a forced OCR failure lands in the DLQ with an alert, status `failed`, clear error.
- Quota: upload beyond quota is rejected cleanly with an upgrade message.
- Malware: EICAR test file is rejected by ClamAV.
- **OCR golden set**: 20–30 representative documents (incl. Sinhala/Tamil if in scope) compared to ground truth; target ≥95% on printed text *(addresses v2 §5.2 gap)*.

## Definition of Done
Any supported file uploads → extracted, chunked text visible in UI; idempotent + quota-enforced + DLQ-protected; SSE progress works; OCR accuracy meets target on the golden set.

---

# Phase 3 — Search & Summaries (Week 5)

**Goal:** Fast, high-quality hybrid search with reranking, plus an auto-generated cached summary per document.

## Prerequisites
Phase 2 DoD met (chunks exist).

## Backlog
- [ ] Models + migrations: `document_chunks` with `embedding VECTOR(1024)` + `content_tsv` (generated) + HNSW and GIN indexes.
- [ ] **Embedding service behind an interface** (`Embedder`): batched BGE-M3 (encode 32–64 chunks/call), ONNX/quantized build *(B4.2)*.
- [ ] **pgvector iterative index scans enabled** so RLS post-filtering doesn't collapse recall *(B4.1)*.
- [ ] Hybrid search: vector top-K + full-text top-K → **Reciprocal Rank Fusion** → **cross-encoder reranker** (bge-reranker-v2 or Cohere) on top ~30 *(BP3.4)*.
- [ ] Low-confidence handling: if top rerank score < threshold, return "no strong match" *(v2 §5.1 gap)*.
- [ ] Gemini summary on document completion, **cached** in `documents.summary` (never regenerate) *(BP3.4)*.
- [ ] Search UI: query box, filters (date, tags, type), highlighted snippets, relevance order.

## Implementation notes

**Embedder interface (so CPU→GPU→API is a config swap, not a rewrite):**
```python
class Embedder(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]: ...
# Bge M3 CPU (batched, ONNX) now → GPU/managed endpoint when the embed queue backs up (B4.2)
```

**Vector recall safeguard:** confirm `SET hnsw.iterative_scan = relaxed_order` (pgvector 0.8+) or partition vectors by `org_id`; verify recall on a small tenant against a brute-force baseline *(B4.1)*.

## Testing
- Search quality: a 50-query set with expected documents; measure recall@10 before vs after reranking (reranking should clearly improve it).
- Recall-under-isolation: a small tenant's search returns the correct docs (guards against the pgvector+RLS trap).
- Summary caching: a document is summarized once; re-fetch hits cache.

## Definition of Done
Semantic + keyword search returns correct, reranked results across tenants with verified recall; summaries generated once and cached; search UI usable with filters.

---

# Phase 4 — Q&A Chat (RAG) (Week 6)

**Goal:** A user asks natural-language questions and gets grounded, cited answers, streamed live, hardened against prompt injection.

## Prerequisites
Phase 3 DoD met (retrieval + reranking work).

## Backlog
- [ ] Models + migrations: `chat_sessions`, `chat_messages` (with `cited_chunks`).
- [ ] RAG pipeline: embed question → hybrid retrieve → rerank → build context (org-filtered) → Gemini with grounding prompt → answer + citations.
- [ ] Modes: "Ask this document" and "Ask all my documents".
- [ ] **Streaming responses via SSE** *(B4.8)*.
- [ ] Prompt-injection defense: document text delimited and labeled as data; output sanitized (no raw HTML render) *(BP3.4)*.
- [ ] Grounding guarantee: answer only from context; cite chunk IDs; "not found" when absent.
- [ ] **Evaluation harness**: 50 Q&A pairs run in CI measuring answer correctness + citation accuracy *(BP3.4)*.
- [ ] Graceful degradation: if the LLM provider is down, search/view still work; Q&A shows a clear message *(BP3.1)*.

## Implementation notes
- Retrieval context is **always filtered by org_id before** it reaches the model — the model can never see another tenant's chunks *(B4.1, security)*.
- Cost guard: per-org AI-question quota enforced before the call *(B4.3)*.

## Testing
- RAG eval set passes thresholds for correctness and citation accuracy.
- Injection test: a document containing "ignore previous instructions…" does not alter behavior.
- Cross-tenant: questions never surface another org's content (extends the isolation suite).

## Definition of Done
Cited, grounded answers stream correctly in both modes; eval thresholds met; injection and cross-tenant tests green; graceful degradation verified.

---

# Phase 5 — Chrome Extension (Week 7, parallelizable from Phase 3)

**Goal:** A Manifest V3 extension for quick upload and search using the same API and auth.

## Prerequisites
Auth (Phase 1) and upload (Phase 2) endpoints stable.

## Backlog
- [ ] MV3 manifest, minimal permissions (`activeTab`, `storage` — no broad host permissions) *(security)*.
- [ ] Login via the same token flow; tokens in `chrome.storage.session` (cleared on browser close).
- [ ] Quick upload: file, screenshot, or current page as PDF.
- [ ] Quick search popup hitting the search API.
- [ ] CSP in manifest; no `eval`; all logic bundled (no remote code).
- [ ] Chrome Web Store listing assets + privacy policy; publish **unlisted** first for testing.

## Testing
- Auth/refresh works inside the extension; tokens cleared on close.
- Upload + search round-trip from the extension.

## Definition of Done
Extension installs, authenticates, uploads, and searches against the live API; published unlisted.

---

# Phase 6 — Hardening & Commercial Launch (Week 8)

**Goal:** Production-ready: secure, observed, backed up, billable, with pilot clients onboarded.

## Prerequisites
Phases 1–4 DoD met (5 can trail).

## Backlog
- [ ] Security review: OWASP Top 10 checklist, dependency scan, OWASP ZAP baseline, basic pen test.
- [ ] Security headers (HSTS preload, CSP, X-Frame-Options DENY, X-Content-Type-Options); CORS locked to web domain + extension ID.
- [ ] Load test (Locust): 50 concurrent users + a 100-document bulk import; API p95 < 300 ms; queue drains within SLA *(B4.4, B4.5)*.
- [ ] Monitoring: Sentry, Uptime Kuma, **daily API-cost report**, alert on spend threshold and on DLQ growth *(B4.3)*.
- [ ] **Backups**: nightly encrypted `pg_dump` → separate R2 bucket, 30-day retention; **restore drill executed and documented** *(v2 §5.7)*.
- [ ] Runbooks: stuck queue, OCR provider outage (fallback/replay), DB restore, secret rotation.
- [ ] Billing: plans + quotas; manual invoicing acceptable for first pilots, Stripe/Paddle wired if time allows *(v2 §5.8)*.
- [ ] Privacy policy + ToS naming Mistral/Google as sub-processors; data export endpoint *(v2 §5.3)*.
- [ ] Go-live checklist (from v1 §9) fully checked.
- [ ] Onboard 2–3 pilot clients with white-glove setup.

## Definition of Done
Production launched with paying/pilot users; backups tested; monitoring + cost alerts live; security review passed; runbooks written.

---

# Stage 1 Sprint Plan (Summary)

| Sprint | Weeks | Phase(s) | Headline deliverable |
|---|---|---|---|
| 1 | 1 | Phase 0 | One-command stack + green CI |
| 2 | 2 | Phase 1 | Secure login + tenant isolation proven |
| 3 | 3–4 | Phase 2 | Upload → reliable OCR + text |
| 4 | 5 | Phase 3 | Hybrid search + reranking + summaries |
| 5 | 6 | Phase 4 | Cited, streamed Q&A |
| 6 | 7 | Phase 5 | Chrome extension (unlisted) |
| 7 | 8 | Phase 6 | Hardening + pilot launch |

Phase 5 can overlap Sprints 4–6 if a second engineer is available.

---

# Cross-Cutting Definition of Done (applies to every story)

A story is not done until: code reviewed; unit + integration tests written and green; **security/tenant-isolation suite still green**; no secrets in code; structured logs + traces emitted for new paths; relevant runbook/README updated; feature flag or graceful fallback where it touches a third-party API.

---

# Stage 2 & 3 (Forward Backlog — Build When Needed)

**Stage 2 (paying customers):** PgBouncer; API behind LB (≥2 replicas) + Postgres read replica; per-tenant fair queueing; circuit breakers + Batch OCR + PaddleOCR fallback in production; ONNX/GPU embeddings if the embed queue saturates *(B4.2)*; OpenTelemetry tracing; billing integration; folder/sharing permissions; bulk import + export; per-tenant cost dashboards; PII-redaction option.

**Stage 3 (enterprise/scale):** dedicated vector DB (Qdrant) if pgvector strains *(B4.1)*; org-partitioned storage; data-residency / self-hosted-LLM tier *(v2 §5.3)*; multi-region DR; tamper-evident (hash-chained) audit log; status page + SLA; advanced query understanding; autoscaling workers.

---

# First Week, Concretely

1. Provision the accounts in §0.4 and put keys in the CI secret store.
2. Build the monorepo skeleton (§0.1) and `docker-compose.yml`.
3. Get `make up` + `/healthz`/`/readyz` working and CI green (Phase 0 DoD).
4. Immediately start Phase 1 with the **`get_db` org-context pattern and the tenant-isolation test first** — write the failing security test before the feature, so isolation is proven by construction.

---

*End of playbook. Recommended companion artifacts to produce next: (a) the actual Phase 0 repo scaffold + docker-compose + CI files, and (b) ADRs for the OCR-fallback and vector-store decisions.*
