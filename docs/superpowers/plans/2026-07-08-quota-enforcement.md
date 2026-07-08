# Quota Enforcement Implementation Plan (Stage B — Task 1)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the page-quota system: reject uploads when quota is exhausted, true-up usage to actual OCR page counts, reset usage monthly, and expose usage to the dashboard.

**Architecture:** Builds on the existing `OrgRepository.check_and_increment_quota` (atomic UPDATE guard, called in `run_ocr`). Adds: a pre-flight check in the upload service (HTTP 402), an `adjust_usage` true-up after OCR, a `reset_monthly_usage` beat task (1st of month), and `GET /api/v1/users/me/usage`. Web dashboard gets a small usage indicator.

**Tech Stack:** FastAPI, SQLAlchemy async, Celery beat crontab, Next.js dashboard.

## Global Constraints

- Same as Stage A plan: Python 3.12, mypy strict for new code, ruff `E,F,I,N,W,UP,S` @ 88 cols, conventional commits.
- Tests run via `TESTING=true DATABASE_URL=...idms_test... uv run --extra dev pytest` (never against `idms` — conftest guard enforces).
- Quota semantics: `pages_used_this_month + estimate <= monthly_page_quota` allows; uploads blocked only when `pages_used_this_month >= monthly_page_quota` (a partially-full quota still accepts uploads; OCR-time check remains the hard gate).

---

### Task 1: Reject uploads when quota exhausted (HTTP 402)

**Files:**

- Modify: `api/app/services/upload.py` (quota pre-flight in `init_upload`)
- Test: `api/tests/integration/test_quota.py`

**Interfaces:**

- Consumes: `OrgRepository.get_by_id`, org columns `pages_used_this_month`, `monthly_page_quota`.
- Produces: `init_upload` raises `HTTPException(402, "Monthly page quota exhausted ...")` when used >= quota.

- [ ] Step 1: failing test — register org, `UPDATE organizations SET pages_used_this_month = monthly_page_quota`, POST `/api/v1/documents/upload-url` → expect 402.
- [ ] Step 2: run test, expect FAIL (currently 201).
- [ ] Step 3: in `init_upload`, load org; if `org.pages_used_this_month >= org.monthly_page_quota` raise 402 with message "Monthly page quota exhausted. Quota resets on the 1st; contact support to upgrade."
- [ ] Step 4: test passes; full suite green.
- [ ] Step 5: commit `feat(api): reject uploads with 402 when monthly page quota exhausted`.

### Task 2: True-up usage to actual OCR page count

**Files:**

- Modify: `api/app/repositories/organization.py` (add `adjust_usage`)
- Modify: `api/app/workers/tasks.py` (`_run_ocr_async`: after OCR success, adjust by `result.page_count - estimated_pages`)
- Test: `api/tests/integration/test_quota.py`

**Interfaces:**

- Produces: `async def adjust_usage(self, org_id: uuid.UUID, delta_pages: int) -> None` — `pages_used_this_month = GREATEST(0, pages_used_this_month + delta)`; no quota guard (records reality even if over).

- [ ] Step 1: failing tests — repo-level: org with used=10, `adjust_usage(-3)` → 7; `adjust_usage(-100)` → clamps to 0.
- [ ] Step 2: run, expect AttributeError.
- [ ] Step 3: implement with `func.greatest(0, Organization.pages_used_this_month + delta_pages)`; wire into `_run_ocr_async` right after `set_status(... READY ...)` with `delta = result.page_count - estimated_pages`, skip if 0.
- [ ] Step 4: tests pass; full suite green.
- [ ] Step 5: commit `feat(api): true-up org page usage to actual OCR page count`.

### Task 3: Monthly usage reset beat task

**Files:**

- Modify: `api/app/repositories/organization.py` (add `reset_all_usage`)
- Modify: `api/app/workers/tasks.py` (task `reset_monthly_usage`)
- Modify: `api/app/workers/celery_app.py` (beat entry, crontab 1st 00:05 UTC)
- Test: `api/tests/integration/test_quota.py`

**Interfaces:**

- Produces: `async def reset_all_usage(self) -> int` (rows updated); Celery task `app.workers.tasks.reset_monthly_usage` returning `{"orgs_reset": n}`.

- [ ] Step 1: failing test — two orgs with usage 5/9, run `reset_monthly_usage` via `asyncio.to_thread(task.run)`, both back to 0, result reports count.
- [ ] Step 2: run, expect ImportError.
- [ ] Step 3: implement repo method (`UPDATE organizations SET pages_used_this_month = 0 WHERE pages_used_this_month > 0`), task following `report_api_costs` pattern (asyncio.run + logger), beat entry `crontab(day_of_month=1, hour=0, minute=5)`.
- [ ] Step 4: tests pass; verify `celery_app.conf.beat_schedule` loads.
- [ ] Step 5: commit `feat(api): monthly page-quota reset beat task (1st 00:05 UTC)`.

### Task 4: Usage endpoint for the dashboard

**Files:**

- Modify: `api/app/schemas/user.py` (add `UsageResponse`)
- Modify: `api/app/api/v1/users.py` (GET `/users/me/usage`)
- Test: `api/tests/integration/test_quota.py`

**Interfaces:**

- Produces: `GET /api/v1/users/me/usage` → `{"plan": "free", "monthly_page_quota": 500, "pages_used_this_month": 0, "remaining_pages": 500}` (auth required; org-scoped).

- [ ] Step 1: failing test — register → GET → 200 with plan "free", quota 500, used 0, remaining 500; unauthenticated → 401.
- [ ] Step 2: run, expect 404.
- [ ] Step 3: implement schema + endpoint (load org via `CurrentUserDep.org_id`, `remaining = max(0, quota - used)`).
- [ ] Step 4: tests pass; full suite green.
- [ ] Step 5: commit `feat(api): usage endpoint — plan, quota, pages used/remaining`.

### Task 5: Dashboard usage indicator (web)

**Files:**

- Create: `web/components/UsageIndicator.tsx`
- Modify: dashboard page/header to render it.

**Interfaces:**

- Consumes: `GET /api/v1/users/me/usage` with bearer token (same fetch pattern as existing dashboard components).

- [ ] Step 1: component fetches usage on mount; renders "N / M pages used"; turns amber ≥80%, red at 100% with "quota exhausted" note; hidden while loading/on error.
- [ ] Step 2: `npm run lint && npm run type-check` green.
- [ ] Step 3: commit `feat(web): dashboard usage indicator with quota warning states`.

## Definition of Done

- Full api suite green against idms_test; lint clean.
- Upload at exhausted quota → 402 with actionable message; OCR gate still enforced.
- Usage self-corrects to actual pages; resets monthly; visible in dashboard.
