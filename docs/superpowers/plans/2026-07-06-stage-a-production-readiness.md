# Stage A — Production Readiness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the IDMS deployable to real customers: security headers, locked CORS, rate limiting, encrypted backups with a rehearsed restore, daily AI-cost reporting with spend alerts, queue-depth monitoring, a load-test harness, and operational runbooks.

**Architecture:** All API hardening lands as FastAPI middleware/config in `api/app/core` and `api/app/main.py`. Monitoring logic lives in a new `app/services/monitoring.py` service (pure functions, unit-testable) wired into Celery beat tasks in `app/workers/tasks.py`. Backups are shell scripts under `infra/scripts/` that run against the docker-compose Postgres and push encrypted dumps to R2. Load tests are a Locust file under `infra/load/`. Runbooks are markdown in `docs/runbooks/`.

**Tech Stack:** FastAPI + Starlette middleware, slowapi (already a dependency), SQLAlchemy async, Celery beat + Redis, structlog, sentry-sdk, `pg_dump` + `openssl` + `aws` CLI (S3-compatible R2), Locust, bandit + pip-audit in GitHub Actions.

## Global Constraints

- Python 3.12, mypy `strict = true` — every new function fully annotated.
- Ruff rules `E,F,I,N,W,UP,S`, line length 88 — run `uv run ruff check .` before each commit.
- All API tests run against the real Postgres/Redis from `infra/docker-compose.yml` (`make up` first). Test commands run from the `api/` directory with `uv run pytest`.
- Tenant-isolation suite (`tests/security/`) must stay green after every task.
- No secrets in code or committed files — secrets come from `.env` / CI secret store.
- Conventional commit messages (`feat:`, `fix:`, `docs:`, `chore:`, `test:`), matching existing history.
- New settings go in `api/app/core/config.py` `Settings` class with safe defaults so existing `.env` files keep working.

---

### Task 1: Security headers middleware

**Files:**

- Create: `api/app/core/middleware.py`
- Modify: `api/app/main.py` (register middleware in `create_app`)
- Test: `api/tests/security/test_headers.py`

**Interfaces:**

- Consumes: nothing new.
- Produces: `SecurityHeadersMiddleware` (Starlette `BaseHTTPMiddleware` subclass) imported by `app.main`.

- [ ] **Step 1: Write the failing test**

Create `api/tests/security/test_headers.py`:

```python
from httpx import AsyncClient


async def test_security_headers_on_api_response(client: AsyncClient) -> None:
    resp = await client.get("/healthz")
    assert resp.status_code == 200
    assert (
        resp.headers["Strict-Transport-Security"]
        == "max-age=63072000; includeSubDomains; preload"
    )
    assert resp.headers["X-Frame-Options"] == "DENY"
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.headers["Referrer-Policy"] == "no-referrer"
    assert (
        resp.headers["Content-Security-Policy"]
        == "default-src 'none'; frame-ancestors 'none'"
    )


async def test_docs_page_exempt_from_strict_csp(client: AsyncClient) -> None:
    """Swagger UI loads CDN assets; a default-src 'none' CSP would break it."""
    resp = await client.get("/api/docs")
    assert resp.status_code == 200
    assert "Content-Security-Policy" not in resp.headers
    # Non-CSP headers still apply everywhere.
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
```

- [ ] **Step 2: Run test to verify it fails**

Run (from `api/`): `uv run pytest tests/security/test_headers.py -v`
Expected: FAIL with `KeyError: 'strict-transport-security'`

- [ ] **Step 3: Write the middleware**

Create `api/app/core/middleware.py`:

```python
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

# Swagger/ReDoc load scripts and styles from a CDN; a strict CSP breaks them.
_CSP_EXEMPT_PREFIXES = ("/api/docs", "/api/redoc", "/openapi.json")


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        response = await call_next(request)
        response.headers["Strict-Transport-Security"] = (
            "max-age=63072000; includeSubDomains; preload"
        )
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        if not request.url.path.startswith(_CSP_EXEMPT_PREFIXES):
            response.headers["Content-Security-Policy"] = (
                "default-src 'none'; frame-ancestors 'none'"
            )
        return response
```

In `api/app/main.py`, add the import and register the middleware inside `create_app()` immediately after the `FastAPI(...)` construction (before the CORS middleware registration):

```python
from app.core.middleware import SecurityHeadersMiddleware
```

```python
    app.add_middleware(SecurityHeadersMiddleware)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/security/test_headers.py -v`
Expected: 2 PASSED

- [ ] **Step 5: Run lint, type-check, and the full security suite**

Run: `uv run ruff check . && uv run mypy app/ && uv run pytest tests/security/ -v`
Expected: no lint/type errors; all security tests PASS

- [ ] **Step 6: Commit**

```bash
git add api/app/core/middleware.py api/app/main.py api/tests/security/test_headers.py
git commit -m "feat(api): security headers middleware (HSTS, CSP, X-Frame-Options, nosniff)"
```

---

### Task 2: Config-driven CORS lockdown

**Files:**

- Modify: `api/app/core/config.py` (add `CORS_ORIGINS`)
- Modify: `api/app/main.py:42-53` (use setting; restrict methods/headers)
- Test: `api/tests/security/test_cors.py`

**Interfaces:**

- Consumes: nothing new.
- Produces: `settings.CORS_ORIGINS: list[str]` — production deploys override it via the `CORS_ORIGINS` env var (JSON list, e.g. `["https://app.example.com"]`).

- [ ] **Step 1: Write the failing test**

Create `api/tests/security/test_cors.py`:

```python
from httpx import AsyncClient


async def test_preflight_allows_configured_origin(client: AsyncClient) -> None:
    resp = await client.options(
        "/api/v1/auth/login",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert resp.status_code == 200
    assert (
        resp.headers["access-control-allow-origin"] == "http://localhost:3000"
    )


async def test_preflight_rejects_unknown_origin(client: AsyncClient) -> None:
    resp = await client.options(
        "/api/v1/auth/login",
        headers={
            "Origin": "https://evil.example.com",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert "access-control-allow-origin" not in resp.headers


async def test_preflight_rejects_disallowed_method(client: AsyncClient) -> None:
    resp = await client.options(
        "/api/v1/auth/login",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "TRACE",
        },
    )
    assert resp.status_code == 400
```

- [ ] **Step 2: Run test to verify current gaps**

Run: `uv run pytest tests/security/test_cors.py -v`
Expected: `test_preflight_rejects_disallowed_method` FAILS (current config uses `allow_methods=["*"]`, so TRACE preflight returns 200). The other two may already pass — that is fine; keep them as regression tests.

- [ ] **Step 3: Add the setting and lock down main.py**

In `api/app/core/config.py`, add below the `SENTRY_DSN` field:

```python
    # CORS — override in production with the deployed web origin(s)
    CORS_ORIGINS: list[str] = [
        "http://localhost:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3001",
    ]
```

In `api/app/main.py`, replace the existing `app.add_middleware(CORSMiddleware, ...)` block with:

```python
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/security/test_cors.py -v`
Expected: 3 PASSED

- [ ] **Step 5: Run full test suite to catch regressions**

Run: `uv run pytest tests/ -v --tb=short`
Expected: all PASS (uploads use POST + Authorization/Content-Type, so nothing should break; if an integration test fails on a missing header, add that header to `allow_headers` rather than reverting to `*`)

- [ ] **Step 6: Commit**

```bash
git add api/app/core/config.py api/app/main.py api/tests/security/test_cors.py
git commit -m "feat(api): config-driven CORS with locked methods and headers"
```

---

### Task 3: Rate limiting on auth endpoints

**Files:**

- Modify: `api/app/core/config.py` (add `RATE_LIMIT_ENABLED`)
- Modify: `api/app/main.py` (honor the flag)
- Modify: `api/app/api/v1/auth.py` (apply limits to register/login/refresh)
- Modify: `api/tests/conftest.py` (disable limiter by default in tests)
- Test: `api/tests/security/test_rate_limit.py`

**Interfaces:**

- Consumes: `limiter` from `app.main` (module-level slowapi `Limiter`, already exists at `api/app/main.py:24`).
- Produces: `settings.RATE_LIMIT_ENABLED: bool` (default `True`); decorated auth endpoints returning HTTP 429 with slowapi's default JSON body when exceeded.

**Why the enable flag:** the limiter keys on client IP; every test request comes from the same test IP, so a 5/minute login limit would break the whole suite. Tests disable the limiter globally and re-enable it only inside the rate-limit test.

- [ ] **Step 1: Write the failing test**

Create `api/tests/security/test_rate_limit.py`:

```python
from collections.abc import Generator

import pytest
from httpx import AsyncClient

from app.main import limiter


@pytest.fixture
def rate_limits_on() -> Generator[None, None, None]:
    limiter.reset()
    limiter.enabled = True
    yield
    limiter.enabled = False
    limiter.reset()


async def test_login_returns_429_after_10_attempts(
    client: AsyncClient, rate_limits_on: None
) -> None:
    payload = {"email": "nobody@example.com", "password": "wrongpassword"}
    for _ in range(10):
        resp = await client.post("/api/v1/auth/login", json=payload)
        assert resp.status_code != 429
    resp = await client.post("/api/v1/auth/login", json=payload)
    assert resp.status_code == 429


async def test_register_returns_429_after_5_attempts(
    client: AsyncClient, rate_limits_on: None
) -> None:
    for i in range(5):
        resp = await client.post(
            "/api/v1/auth/register",
            json={
                "org_name": f"RL Org {i}",
                "email": f"rl-{i}@example.com",
                "password": "password1234",
            },
        )
        assert resp.status_code != 429
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "org_name": "RL Org 5",
            "email": "rl-5@example.com",
            "password": "password1234",
        },
    )
    assert resp.status_code == 429
```

Add this autouse fixture to `api/tests/conftest.py` (after the existing `clean_db` fixture):

```python
@pytest.fixture(autouse=True)
def _disable_rate_limits() -> Generator[None, None, None]:
    """Rate limits key on client IP; all test traffic shares one IP."""
    from app.main import limiter

    limiter.enabled = False
    yield
    limiter.enabled = False
```

(Also add `from collections.abc import Generator` to the conftest imports — it currently imports only `AsyncGenerator`.)

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/security/test_rate_limit.py -v`
Expected: FAIL — final request returns 401/201 instead of 429 (no limits applied yet)

- [ ] **Step 3: Apply limits to the auth endpoints**

Replace `api/app/api/v1/auth.py` with:

```python
from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_public_db
from app.schemas.auth import (
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
)
from app.services import auth as auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(
    request: Request,
    body: RegisterRequest,
    session: AsyncSession = Depends(get_public_db),
) -> TokenResponse:
    return await auth_service.register(body, session)


@router.post("/login", response_model=TokenResponse)
async def login(
    request: Request,
    body: LoginRequest,
    session: AsyncSession = Depends(get_public_db),
) -> TokenResponse:
    return await auth_service.login(body, session)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(request: Request, body: RefreshRequest) -> TokenResponse:
    return await auth_service.refresh_tokens(body.refresh_token)


@router.post("/logout", status_code=204)
async def logout(body: LogoutRequest) -> None:
    await auth_service.logout(body.refresh_token)
```

slowapi decorators need the `limiter` instance, which lives in `app.main` — importing it in `auth.py` would create a circular import (`main` imports `auth_router`). Move the limiter to its own module instead. Create the limiter in `api/app/core/ratelimit.py`:

```python
from slowapi import Limiter  # type: ignore[import-untyped]
from slowapi.util import get_remote_address  # type: ignore[import-untyped]

limiter = Limiter(key_func=get_remote_address)
```

Then in `api/app/main.py`: delete the `limiter = Limiter(key_func=get_remote_address)` line and its `Limiter` / `get_remote_address` imports, and instead import it:

```python
from app.core.ratelimit import limiter
```

Keep `app.state.limiter = limiter` and the `RateLimitExceeded` handler as they are. Add the flag inside `create_app()` right before `app.state.limiter = limiter`:

```python
    limiter.enabled = settings.RATE_LIMIT_ENABLED
```

In `api/app/core/config.py`, add below the CORS block:

```python
    # Rate limiting
    RATE_LIMIT_ENABLED: bool = True
```

Now decorate the endpoints in `api/app/api/v1/auth.py` — add the import and decorators:

```python
from app.core.ratelimit import limiter
```

```python
@router.post("/register", response_model=TokenResponse, status_code=201)
@limiter.limit("5/minute")
async def register(
```

```python
@router.post("/login", response_model=TokenResponse)
@limiter.limit("10/minute")
async def login(
```

```python
@router.post("/refresh", response_model=TokenResponse)
@limiter.limit("30/minute")
async def refresh(request: Request, body: RefreshRequest) -> TokenResponse:
```

Finally, update the import in `api/tests/security/test_rate_limit.py` and the conftest fixture from `from app.main import limiter` to `from app.core.ratelimit import limiter`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/security/test_rate_limit.py -v`
Expected: 2 PASSED

- [ ] **Step 5: Run the full suite (limiter must not leak into other tests)**

Run: `uv run pytest tests/ -v --tb=short`
Expected: all PASS. If any auth-heavy test hits 429, the autouse `_disable_rate_limits` fixture is not being applied — check it was added to `tests/conftest.py`, not a subdirectory conftest.

- [ ] **Step 6: Lint, type-check, commit**

Run: `uv run ruff check . && uv run mypy app/`

```bash
git add api/app/core/ratelimit.py api/app/core/config.py api/app/main.py api/app/api/v1/auth.py api/tests/conftest.py api/tests/security/test_rate_limit.py
git commit -m "feat(api): rate limits on auth endpoints (5-30/min) with test-mode flag"
```

---

### Task 4: Monitoring service — API cost summary and queue depths

**Files:**

- Create: `api/app/services/monitoring.py`
- Modify: `api/app/core/config.py` (add alert thresholds)
- Test: `api/tests/integration/test_monitoring.py`

**Interfaces:**

- Consumes: `ApiUsage` model (`api/app/models/api_usage.py` — columns `org_id`, `service`, `pages_used`, `tokens_used`, `cost_usd`, `created_at`), `Organization` model (`api/app/models/organization.py`), `SessionLocal` from `app.core.db`, `settings.REDIS_URL`.
- Produces:
  - `CostSummary` dataclass: `service: str`, `total_cost_usd: float`, `total_tokens: int`, `total_pages: int`
  - `async def summarize_api_costs(session: AsyncSession, since_hours: int = 24) -> list[CostSummary]`
  - `def check_queue_depths(queues: Sequence[str] | None = None) -> dict[str, int]` (opens its own Redis connection from `settings.REDIS_URL`)
  - Task 5 wires both into Celery beat.

- [ ] **Step 1: Write the failing tests**

Create `api/tests/integration/test_monitoring.py`:

```python
import uuid
from datetime import UTC, datetime, timedelta

from app.core.db import SessionLocal
from app.models.api_usage import ApiUsage
from app.models.organization import Organization
from app.services.monitoring import check_queue_depths, summarize_api_costs


async def _seed_usage() -> None:
    async with SessionLocal.begin() as session:
        org = Organization(name="Cost Org", slug=f"cost-{uuid.uuid4().hex[:8]}")
        session.add(org)
        await session.flush()
        session.add_all(
            [
                ApiUsage(
                    org_id=org.id, service="ocr", pages_used=10, cost_usd=0.10
                ),
                ApiUsage(
                    org_id=org.id, service="ocr", pages_used=5, cost_usd=0.05
                ),
                ApiUsage(
                    org_id=org.id,
                    service="gemini",
                    tokens_used=2000,
                    cost_usd=0.02,
                ),
                # Older than the 24h window — must be excluded.
                ApiUsage(
                    org_id=org.id,
                    service="ocr",
                    pages_used=999,
                    cost_usd=9.99,
                    created_at=datetime.now(UTC) - timedelta(hours=48),
                ),
            ]
        )


async def test_summarize_api_costs_groups_by_service_within_window() -> None:
    await _seed_usage()
    async with SessionLocal() as session:
        rows = await summarize_api_costs(session, since_hours=24)
    by_service = {r.service: r for r in rows}
    assert by_service["ocr"].total_cost_usd == 0.15
    assert by_service["ocr"].total_pages == 15  # 48h-old row excluded
    assert by_service["gemini"].total_tokens == 2000


def test_check_queue_depths_returns_all_default_queues() -> None:
    depths = check_queue_depths()
    assert set(depths) == {"ocr", "embed", "ai", "default", "dlq"}
    assert all(isinstance(v, int) and v >= 0 for v in depths.values())
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/integration/test_monitoring.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.monitoring'`

- [ ] **Step 3: Implement the monitoring service**

Create `api/app/services/monitoring.py`:

```python
"""Aggregation helpers for operational monitoring (cost reports, queue depth)."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import redis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.api_usage import ApiUsage

CELERY_QUEUES: tuple[str, ...] = ("ocr", "embed", "ai", "default", "dlq")


@dataclass(frozen=True)
class CostSummary:
    service: str
    total_cost_usd: float
    total_tokens: int
    total_pages: int


async def summarize_api_costs(
    session: AsyncSession, since_hours: int = 24
) -> list[CostSummary]:
    cutoff = datetime.now(UTC) - timedelta(hours=since_hours)
    stmt = (
        select(
            ApiUsage.service,
            func.coalesce(func.sum(ApiUsage.cost_usd), 0.0),
            func.coalesce(func.sum(ApiUsage.tokens_used), 0),
            func.coalesce(func.sum(ApiUsage.pages_used), 0),
        )
        .where(ApiUsage.created_at >= cutoff)
        .group_by(ApiUsage.service)
    )
    result = await session.execute(stmt)
    return [
        CostSummary(
            service=row[0],
            total_cost_usd=round(float(row[1]), 6),
            total_tokens=int(row[2]),
            total_pages=int(row[3]),
        )
        for row in result.all()
    ]


def check_queue_depths(
    queues: Sequence[str] | None = None,
) -> dict[str, int]:
    """Celery queues are Redis lists named after the queue."""
    client = redis.Redis.from_url(settings.REDIS_URL)
    try:
        return {q: int(client.llen(q)) for q in queues or CELERY_QUEUES}
    finally:
        client.close()
```

In `api/app/core/config.py`, add below the `RATE_LIMIT_ENABLED` field:

```python
    # Monitoring / alerting thresholds
    DAILY_COST_ALERT_USD: float = 5.0
    QUEUE_ALERT_DEPTH: int = 500
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/integration/test_monitoring.py -v`
Expected: 2 PASSED (requires `make up` stack: Postgres + Redis running)

- [ ] **Step 5: Lint, type-check, commit**

Run: `uv run ruff check . && uv run mypy app/`

```bash
git add api/app/services/monitoring.py api/app/core/config.py api/tests/integration/test_monitoring.py
git commit -m "feat(api): monitoring service — 24h cost summary and Celery queue depths"
```

---

### Task 5: Beat tasks — daily cost report and queue-depth alerts

**Files:**

- Modify: `api/app/workers/tasks.py` (two new tasks at the end of the file)
- Modify: `api/app/workers/celery_app.py:34-39` (extend `beat_schedule`)
- Test: `api/tests/integration/test_monitoring_tasks.py`

**Interfaces:**

- Consumes: `summarize_api_costs`, `check_queue_depths`, `CostSummary` from Task 4; `settings.DAILY_COST_ALERT_USD`, `settings.QUEUE_ALERT_DEPTH`; existing pattern `celery_app.task` + `asyncio.run(...)` (see `heal_stuck_documents` at `api/app/workers/tasks.py:72-78`).
- Produces: Celery tasks `app.workers.tasks.report_api_costs` (daily 01:00 UTC) and `app.workers.tasks.monitor_queue_depths` (every 5 min). Both return dicts so results are inspectable; alerts go to structlog + `sentry_sdk.capture_message`.

- [ ] **Step 1: Write the failing test**

Create `api/tests/integration/test_monitoring_tasks.py`:

```python
import uuid

from app.core.db import SessionLocal
from app.models.api_usage import ApiUsage
from app.models.organization import Organization
from app.workers.tasks import monitor_queue_depths, report_api_costs


async def test_report_api_costs_flags_overspend() -> None:
    async with SessionLocal.begin() as session:
        org = Organization(name="Spend Org", slug=f"spend-{uuid.uuid4().hex[:8]}")
        session.add(org)
        await session.flush()
        # 9.99 USD in the last 24h — above the 5.00 default threshold.
        session.add(ApiUsage(org_id=org.id, service="gemini", cost_usd=9.99))

    result = report_api_costs.run()
    assert result["total_cost_usd"] >= 9.99
    assert result["alert"] is True
    assert any(s["service"] == "gemini" for s in result["services"])


def test_monitor_queue_depths_reports_all_queues() -> None:
    result = monitor_queue_depths.run()
    assert set(result["depths"]) == {"ocr", "embed", "ai", "default", "dlq"}
    assert result["alert"] is False  # local queues are empty
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/integration/test_monitoring_tasks.py -v`
Expected: FAIL with `ImportError: cannot import name 'report_api_costs'`

- [ ] **Step 3: Implement the tasks**

Append to `api/app/workers/tasks.py` (reuse the file's existing `asyncio`, `structlog`/logger, and `celery_app` imports — check the top of the file and only add what is missing):

```python
# ---------------------------------------------------------------------------
# 5. Monitoring beat tasks — daily cost report + queue depth alerts
# ---------------------------------------------------------------------------


@celery_app.task(queue="default", name="app.workers.tasks.report_api_costs")  # type: ignore[untyped-decorator]
def report_api_costs() -> dict[str, object]:
    """Daily: aggregate last-24h third-party API spend; alert past threshold."""
    return asyncio.run(_report_api_costs_async())


async def _report_api_costs_async() -> dict[str, object]:
    import sentry_sdk

    from app.core.config import settings
    from app.core.db import SessionLocal
    from app.services.monitoring import summarize_api_costs

    async with SessionLocal() as session:
        summaries = await summarize_api_costs(session, since_hours=24)

    total = round(sum(s.total_cost_usd for s in summaries), 6)
    alert = total > settings.DAILY_COST_ALERT_USD
    services = [
        {
            "service": s.service,
            "cost_usd": s.total_cost_usd,
            "tokens": s.total_tokens,
            "pages": s.total_pages,
        }
        for s in summaries
    ]
    logger.info(
        "daily_api_cost_report",
        total_cost_usd=total,
        alert=alert,
        services=services,
    )
    if alert:
        sentry_sdk.capture_message(
            f"Daily API spend ${total:.2f} exceeded threshold "
            f"${settings.DAILY_COST_ALERT_USD:.2f}",
            level="warning",
        )
    return {"total_cost_usd": total, "alert": alert, "services": services}


@celery_app.task(queue="default", name="app.workers.tasks.monitor_queue_depths")  # type: ignore[untyped-decorator]
def monitor_queue_depths() -> dict[str, object]:
    """Every 5 min: alert if any Celery queue (incl. DLQ) grows past threshold."""
    import sentry_sdk

    from app.core.config import settings
    from app.services.monitoring import check_queue_depths

    depths = check_queue_depths()
    over = {q: n for q, n in depths.items() if n > settings.QUEUE_ALERT_DEPTH}
    alert = bool(over)
    logger.info("queue_depth_check", depths=depths, alert=alert)
    if alert:
        sentry_sdk.capture_message(
            f"Celery queue depth over {settings.QUEUE_ALERT_DEPTH}: {over}",
            level="warning",
        )
    return {"depths": depths, "alert": alert}
```

Note: if `tasks.py` has no module-level `logger`, add near the top:

```python
import structlog

logger = structlog.get_logger(__name__)
```

In `api/app/workers/celery_app.py`, add the import at the top:

```python
from celery.schedules import crontab  # type: ignore[import-untyped]
```

and extend `beat_schedule` to:

```python
    beat_schedule={
        "heal-stuck-documents": {
            "task": "app.workers.tasks.heal_stuck_documents",
            "schedule": 120.0,
        },
        "daily-cost-report": {
            "task": "app.workers.tasks.report_api_costs",
            "schedule": crontab(hour=1, minute=0),
        },
        "queue-depth-monitor": {
            "task": "app.workers.tasks.monitor_queue_depths",
            "schedule": 300.0,
        },
    },
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/integration/test_monitoring_tasks.py -v`
Expected: 2 PASSED

- [ ] **Step 5: Verify beat picks up the schedule**

Run: `docker compose -f ../infra/docker-compose.yml up -d --build beat worker && docker compose -f ../infra/docker-compose.yml logs beat --tail 20`
Expected: beat log lists `daily-cost-report` and `queue-depth-monitor` alongside `heal-stuck-documents`

- [ ] **Step 6: Lint, type-check, commit**

Run: `uv run ruff check . && uv run mypy app/`

```bash
git add api/app/workers/tasks.py api/app/workers/celery_app.py api/tests/integration/test_monitoring_tasks.py
git commit -m "feat(api): beat tasks for daily cost report and queue-depth alerts"
```

---

### Task 6: Encrypted nightly backups + rehearsed restore

**Files:**

- Create: `infra/scripts/backup.sh`
- Create: `infra/scripts/restore.sh`
- Create: `docs/runbooks/db-restore.md`
- Modify: `Makefile` (add `backup` and `restore-drill` targets)

**Interfaces:**

- Consumes: running compose stack (`infra/docker-compose.yml`), env vars `BACKUP_PASSPHRASE`, `BACKUP_BUCKET`, `R2_ENDPOINT`, plus AWS-style creds (`AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` set to the R2 key pair) for the `aws` CLI.
- Produces: `idms-backup-<UTC timestamp>.sql.gz.enc` objects under `postgres/` in the backup bucket; `restore.sh <file>` restores into a target database. Retention (30 days) is enforced by an R2 lifecycle rule, documented in the runbook — not by script.

**Prerequisites:** `aws` CLI and `openssl` available where the script runs (Git Bash on this Windows host has `openssl`; install AWS CLI v2 if missing). A **separate** R2 bucket for backups — never the document bucket.

- [ ] **Step 1: Write backup.sh**

Create `infra/scripts/backup.sh`:

```bash
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

docker compose -f "$COMPOSE_FILE" exec -T postgres \
    pg_dump -U idms_app -d idms --no-owner \
  | gzip \
  | openssl enc -aes-256-cbc -pbkdf2 -salt \
      -pass env:BACKUP_PASSPHRASE -out "$OUT"

# Refuse to upload an implausibly small dump (schema alone is > 4 KB).
SIZE=$(wc -c < "$OUT")
if [ "$SIZE" -lt 4096 ]; then
  echo "ERROR: backup only ${SIZE} bytes — refusing to upload" >&2
  exit 1
fi

aws s3 cp "$OUT" "s3://${BACKUP_BUCKET}/postgres/${OUT}" \
  --endpoint-url "$R2_ENDPOINT"
rm -f "$OUT"
echo "OK: uploaded postgres/${OUT} (${SIZE} bytes)"
```

- [ ] **Step 2: Write restore.sh**

Create `infra/scripts/restore.sh`:

```bash
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
```

- [ ] **Step 3: Add Makefile targets**

Add to `Makefile` (and add `backup restore-drill` to the `.PHONY` line):

```makefile
backup:
	bash infra/scripts/backup.sh

restore-drill:
	bash infra/scripts/restore.sh $(FILE) idms_restore_drill
```

- [ ] **Step 4: Execute the restore drill (this is the test)**

Run from repo root in Git Bash, with the compose stack up:

```bash
export BACKUP_PASSPHRASE="drill-passphrase-for-local-test"
export BACKUP_BUCKET="<your-backup-bucket>" R2_ENDPOINT="<your-r2-endpoint>"
export AWS_ACCESS_KEY_ID="<r2-key>" AWS_SECRET_ACCESS_KEY="<r2-secret>"
bash infra/scripts/backup.sh
# take the printed filename:
bash infra/scripts/restore.sh idms-backup-<stamp>.sql.gz.enc
```

Expected: `OK: uploaded ...` then `OK: restored into idms_restore_drill — N tables` where N ≥ 6 (organizations, users, documents, document_chunks, api_usage, audit_logs, alembic_version). If R2 credentials are not yet provisioned, verify locally by skipping the `aws s3 cp` upload (comment it out for the drill only) — but the task is not DONE until an upload to a real backup bucket has succeeded once.

Record the drill (date, backup file, table count, time taken) in `docs/runbooks/db-restore.md` — Step 5.

- [ ] **Step 5: Write the db-restore runbook**

Create `docs/runbooks/db-restore.md`:

```markdown
# Runbook: Database Restore

**When:** data corruption, bad migration, accidental deletion, or DR.

## Prerequisites

- `BACKUP_PASSPHRASE` from the secret store (NOT in the repo).
- R2 backup-bucket credentials (separate from app credentials).
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

## Retention

30-day retention is enforced by an R2 lifecycle rule on the backup
bucket (Cloudflare dashboard → R2 → bucket → Settings → Lifecycle).
Verify the rule exists when rotating buckets.

## Drill log

| Date                 | Backup file | Tables restored | Duration | Operator |
| -------------------- | ----------- | --------------- | -------- | -------- |
| (fill on each drill) |             |                 |          |          |
```

- [ ] **Step 6: Commit**

```bash
git add infra/scripts/backup.sh infra/scripts/restore.sh docs/runbooks/db-restore.md Makefile
git commit -m "feat(infra): encrypted nightly backup + restore scripts with drill runbook"
```

**Scheduling note (document, don't automate yet):** on the production host, schedule `backup.sh` nightly at 02:00 via cron (Linux) or Task Scheduler (Windows). Add this line to the runbook when the production host exists.

---

### Task 7: Locust load-test harness

**Files:**

- Create: `infra/load/locustfile.py`
- Modify: `api/pyproject.toml` (add `locust` to dev deps)
- Modify: `Makefile` (add `load-test` target)

**Interfaces:**

- Consumes: live API at `http://localhost:8000`; auth endpoints from Task 3 — **run with `RATE_LIMIT_ENABLED=false` in `.env.docker`** or every simulated user gets 429s from the shared IP.
- Produces: repeatable load scenario; pass criterion **API p95 < 300 ms** at 50 concurrent users for the read paths.

- [ ] **Step 1: Add locust dev dependency**

In `api/pyproject.toml` `[project.optional-dependencies] dev`, add:

```toml
    "locust>=2.29",
```

Run: `cd api && uv sync --extra dev`
Expected: locust installs without dependency conflicts

- [ ] **Step 2: Write the locustfile**

Create `infra/load/locustfile.py`:

```python
"""Load test: 50 users listing, searching, and asking questions.

Run (rate limiting must be disabled on the target API):
    cd api && uv run locust -f ../infra/load/locustfile.py \
        --host http://localhost:8000 -u 50 -r 5 --run-time 3m --headless

Pass criteria: p95 < 300 ms on list/search; failure rate < 1%.
"""

import uuid

from locust import HttpUser, between, task


class IdmsUser(HttpUser):
    wait_time = between(1, 3)

    def on_start(self) -> None:
        """Each simulated user registers its own org, then reuses the token."""
        suffix = uuid.uuid4().hex[:10]
        resp = self.client.post(
            "/api/v1/auth/register",
            json={
                "org_name": f"Load Org {suffix}",
                "email": f"load-{suffix}@example.com",
                "password": "loadtest-password-1234",
            },
        )
        resp.raise_for_status()
        token = resp.json()["access_token"]
        self.client.headers["Authorization"] = f"Bearer {token}"

    @task(5)
    def list_documents(self) -> None:
        self.client.get("/api/v1/documents", name="/documents [list]")

    @task(3)
    def search(self) -> None:
        self.client.get(
            "/api/v1/search",
            params={"q": "invoice payment terms"},
            name="/search",
        )

    @task(1)
    def health(self) -> None:
        self.client.get("/healthz", name="/healthz")
```

Before running, confirm the two GET paths against the actual routers (`api/app/api/v1/documents.py`, `api/app/api/v1/search.py`) — if the search route is e.g. `/api/v1/search/hybrid` or takes a different query param name, fix the locustfile to match, not the API.

- [ ] **Step 3: Add Makefile target**

Add to `Makefile` (and extend `.PHONY`):

```makefile
load-test:
	cd api && uv run locust -f ../infra/load/locustfile.py \
		--host http://localhost:8000 -u 50 -r 5 --run-time 3m --headless
```

- [ ] **Step 4: Run the load test (this is the test)**

Run: `make up` then set `RATE_LIMIT_ENABLED=false` in `.env.docker`, `docker compose -f infra/docker-compose.yml up -d api`, then `make load-test`
Expected: locust summary table shows 0 failed register calls, p95 for `/documents [list]` and `/search` under 300 ms, failure rate < 1%. Record the numbers in the commit message. If p95 exceeds 300 ms, file the finding (slowest endpoint + number) in `docs/runbooks/` notes — fixing performance is out of scope for this task, measuring it is the deliverable.

- [ ] **Step 5: Commit**

```bash
git add infra/load/locustfile.py api/pyproject.toml api/uv.lock Makefile
git commit -m "feat(infra): locust load-test harness — 50-user list/search scenario"
```

---

### Task 8: Runbooks + dependency scanning in CI

**Files:**

- Create: `docs/runbooks/stuck-queue.md`
- Create: `docs/runbooks/ocr-provider-outage.md`
- Create: `docs/runbooks/secret-rotation.md`
- Modify: `.github/workflows/ci.yml` (add a `security` job)

**Interfaces:**

- Consumes: bandit (already in dev deps), pip-audit (added here), monitoring tasks from Task 5 (runbooks reference their log lines).
- Produces: three operational runbooks; CI fails on high-severity findings in code (`bandit`) or dependencies (`pip-audit`).

- [ ] **Step 1: Write the stuck-queue runbook**

Create `docs/runbooks/stuck-queue.md`:

```markdown
# Runbook: Stuck Celery Queue

**Symptom:** documents stay in `processing`/`ready`; Sentry warning
"Celery queue depth over ..." from `monitor_queue_depths`; or the
`queue_depth_check` structlog line shows a growing number.

## Diagnose

1. Depths: `docker compose -f infra/docker-compose.yml exec redis redis-cli llen ocr`
   (repeat for `embed`, `ai`, `default`, `dlq`).
2. Worker alive? `docker compose -f infra/docker-compose.yml logs worker --tail 50`
3. Worker responsive? `docker compose -f infra/docker-compose.yml exec worker uv run celery -A app.workers.celery_app inspect ping`

## Fix

- Worker crashed → `docker compose -f infra/docker-compose.yml restart worker`,
  then watch depth drain.
- Tasks failing repeatedly → read the traceback in worker logs. Provider
  outage → see ocr-provider-outage.md. Code bug → hotfix; tasks retry with
  exponential backoff automatically (`task_acks_late=True` means no loss).
- Stuck documents that missed their embed chain are re-dispatched
  automatically every 2 min by `heal_stuck_documents` — give it one cycle
  before intervening manually.

## Verify

Queue depths near 0; a fresh test upload reaches `indexed` status.
```

- [ ] **Step 2: Write the OCR-outage runbook**

Create `docs/runbooks/ocr-provider-outage.md`:

```markdown
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
- **Key/billing problem:** rotate/refund per secret-rotation.md, then
  restart worker.

## Verify

Upload a one-page test PDF; confirm it reaches `indexed`. Queue depth
drains. Note incident duration + affected document count.
```

- [ ] **Step 3: Write the secret-rotation runbook**

Create `docs/runbooks/secret-rotation.md`:

```markdown
# Runbook: Secret Rotation

Rotate immediately if a secret may have leaked; otherwise quarterly.

## Inventory (all set via .env.docker / CI secrets — never in code)

| Secret                                  | Where issued                       | Consumers                  |
| --------------------------------------- | ---------------------------------- | -------------------------- |
| SECRET_KEY / JWT_SECRET_KEY             | generated (`openssl rand -hex 32`) | api                        |
| DATABASE_URL password                   | Postgres                           | api, worker, beat, migrate |
| R2_ACCESS_KEY_ID / R2_SECRET_ACCESS_KEY | Cloudflare dash                    | api, worker, backups       |
| MISTRAL_API_KEY                         | Mistral console                    | worker (OCR, embeddings)   |
| GOOGLE_AI_API_KEY                       | Google AI Studio                   | api/worker (Gemini)        |
| GROQ_API_KEY                            | Groq console                       | api                        |
| SENTRY_DSN                              | Sentry project settings            | api, worker                |
| BACKUP_PASSPHRASE                       | generated, stored in secret store  | backup/restore scripts     |

## Procedure

1. Issue the new credential at the provider (keep the old one active).
2. Update `.env.docker` on the host and the CI secret store.
3. Rolling restart: `docker compose -f infra/docker-compose.yml up -d api worker beat`
4. Smoke test the affected path (login for JWT, upload for R2/OCR,
   AI chat for Gemini/Groq).
5. Revoke the old credential at the provider.
6. **JWT_SECRET_KEY note:** rotation invalidates all sessions — users
   must log in again. Schedule off-peak and announce.
7. **BACKUP_PASSPHRASE note:** old backups stay encrypted with the old
   passphrase — archive the old passphrase in the secret store with a
   dated label; never delete it while backups encrypted with it exist.
```

- [ ] **Step 4: Add the CI security job**

In `.github/workflows/ci.yml`, add a job alongside the existing `api` job (same indentation level under `jobs:`):

```yaml
security:
  name: "Security — bandit · pip-audit"
  runs-on: ubuntu-latest
  defaults:
    run:
      working-directory: api
  steps:
    - uses: actions/checkout@v4

    - uses: astral-sh/setup-uv@v3
      with:
        enable-cache: true

    - name: Install deps
      run: uv sync --extra dev

    - name: Bandit (code security scan)
      run: uv run bandit -r app/ -ll

    - name: pip-audit (dependency CVEs)
      run: uv run --with pip-audit pip-audit --skip-editable
```

- [ ] **Step 5: Run the scanners locally to verify a clean pass**

Run (from `api/`): `uv run bandit -r app/ -ll && uv run --with pip-audit pip-audit --skip-editable`
Expected: bandit reports no medium/high issues; pip-audit reports no known CVEs. **If either flags findings, fix them as part of this task** (upgrade the pinned dep, or add a targeted `# nosec` with a justification comment for a confirmed false positive) — do not merge a red security job.

- [ ] **Step 6: Commit**

```bash
git add docs/runbooks/stuck-queue.md docs/runbooks/ocr-provider-outage.md docs/runbooks/secret-rotation.md .github/workflows/ci.yml
git commit -m "docs: operational runbooks; ci: bandit + pip-audit security job"
```

---

### Task 9: Housekeeping — ignore celerybeat artifacts

**Files:**

- Modify: `.gitignore`

- [ ] **Step 1: Add ignore rules and remove strays**

Append to `.gitignore`:

```
# Celery beat schedule files
celerybeat-schedule*
```

Then remove the untracked artifacts:

```bash
rm -f api/celerybeat-schedule api/celerybeat-schedule-shm api/celerybeat-schedule-wal
```

- [ ] **Step 2: Verify and commit**

Run: `git status --short`
Expected: no `celerybeat-schedule*` entries listed

```bash
git add .gitignore
git commit -m "chore: gitignore celery beat schedule artifacts"
```

---

## Definition of Done (Stage A)

- [ ] All security tests green: `make test-security`
- [ ] Full suite green: `make test`
- [ ] Restore drill executed and logged in `docs/runbooks/db-restore.md`
- [ ] One successful backup uploaded to the real R2 backup bucket
- [ ] Load test run recorded with p95 numbers
- [ ] CI green including the new `security` job
- [ ] `SENTRY_DSN` set in the production env so cost/queue alerts actually deliver
