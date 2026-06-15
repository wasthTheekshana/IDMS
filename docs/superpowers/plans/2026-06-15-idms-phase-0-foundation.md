# IDMS Phase 0: Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One-command local startup (`make up`), `/healthz` and `/readyz` endpoints live, CI pipeline green and blocking — the foundation every subsequent phase builds on.

**Architecture:** Monorepo (`api/`, `web/`, `extension/`, `infra/`, `docs/`). FastAPI + Celery share one Docker image; `uv` manages Python deps with a lockfile. PostgreSQL 16 + pgvector from day one; Redis as Celery broker/backend. Next.js 14 App Router for the frontend. GitHub Actions CI is blocking on all test stages.

**Tech Stack:** Python 3.12 · uv · FastAPI 0.115 · SQLAlchemy 2.x async · Alembic · Celery 5 · structlog · Sentry SDK · Redis 7 · pgvector/pgvector:pg16; Next.js 14 · TypeScript; Docker Compose; GitHub Actions.

---

> **Scope:** Phase 0 only. Phases 1–6 each have a separate plan. Do **not** start Phase 1 until this plan's Definition of Done is met.
>
> **Definition of Done:**
> - `make up` starts all 4 containers (postgres, redis, api, worker) cleanly
> - `curl localhost:8000/healthz` → `{"status":"ok"}`
> - `curl localhost:8000/readyz` → `{"status":"ready","db":"ok","redis":"ok"}`
> - `make test` green (unit + integration + security suites)
> - `make lint` green (ruff, mypy, eslint)
> - CI pipeline passes on a clean PR
> - No secrets committed to git

---

## File Map

### api/
| File | Responsibility |
|------|---------------|
| `api/pyproject.toml` | uv project, all Python deps, ruff/mypy/pytest/bandit config |
| `api/Dockerfile` | Shared image for `api` and `worker` services |
| `api/app/main.py` | FastAPI app factory + lifespan hook |
| `api/app/core/config.py` | `Settings` class (pydantic-settings), reads from `.env` |
| `api/app/core/db.py` | Async SQLAlchemy engine, `SessionLocal`, `Base` |
| `api/app/core/logging.py` | structlog JSON configuration |
| `api/app/core/telemetry.py` | Sentry SDK init |
| `api/app/api/v1/health.py` | `/healthz` (liveness) + `/readyz` (readiness) |
| `api/app/workers/celery_app.py` | Celery instance + 4 named queues |
| `api/app/workers/tasks.py` | Placeholder `health_check` task |
| `api/alembic.ini` | Alembic config (url set programmatically in env.py) |
| `api/migrations/env.py` | Async Alembic migration runner |
| `api/migrations/script.py.mako` | Migration template |
| `api/tests/conftest.py` | pytest async client fixture |
| `api/tests/unit/test_config.py` | Settings load validation |
| `api/tests/integration/test_health.py` | Health endpoint integration tests |
| `api/tests/security/__init__.py` | Empty — populated in Phase 1 |

### web/
| File | Responsibility |
|------|---------------|
| `web/package.json` | Next.js 14, React 18, TypeScript |
| `web/next.config.ts` | Next.js config |
| `web/tsconfig.json` | TypeScript strict config |
| `web/app/layout.tsx` | Root layout |
| `web/app/page.tsx` | Home page (links to API docs) |
| `web/lib/api.ts` | Typed fetch wrapper + health API calls |

### infra/
| File | Responsibility |
|------|---------------|
| `infra/docker-compose.yml` | postgres (pgvector), redis, api, worker |
| `infra/scripts/seed.py` | Placeholder seed script |

### Root
| File | Responsibility |
|------|---------------|
| `.env.example` | All required env vars, no real secrets |
| `.gitignore` | Python, Node, .env exclusions |
| `.pre-commit-config.yaml` | ruff, bandit, prettier, secret detection |
| `Makefile` | `up`, `down`, `test`, `migrate`, `seed`, `lint` targets |
| `.github/workflows/ci.yml` | Lint → type-check → unit → integration → security (all blocking) |

---

### Task 1: Monorepo skeleton + .gitignore + .env.example

**Files:**
- Create: all directories per §0.1 of playbook
- Create: `.gitignore`
- Create: `.env.example`

- [ ] **Step 1: Create all directories**

Run from the project root (`d:\Project\Intelligent Document Management System\`):

```bash
mkdir -p api/app/core api/app/api/v1 api/app/workers \
         api/app/models api/app/schemas api/app/services \
         api/app/repositories api/migrations/versions \
         api/tests/unit api/tests/integration api/tests/security \
         web/app web/components web/lib \
         extension/src infra/scripts docs \
         .github/workflows
```

- [ ] **Step 2: Create empty `__init__.py` files**

```bash
touch api/app/__init__.py api/app/core/__init__.py \
      api/app/api/__init__.py api/app/api/v1/__init__.py \
      api/app/workers/__init__.py api/app/models/__init__.py \
      api/app/schemas/__init__.py api/app/services/__init__.py \
      api/app/repositories/__init__.py \
      api/migrations/__init__.py \
      api/tests/__init__.py api/tests/unit/__init__.py \
      api/tests/integration/__init__.py api/tests/security/__init__.py
```

- [ ] **Step 3: Create `.gitignore`**

```gitignore
# Python
__pycache__/
*.py[cod]
.venv/
dist/
*.egg-info/
.mypy_cache/
.ruff_cache/
.pytest_cache/
.coverage

# uv
# uv.lock IS committed — it pins exact versions for reproducible builds

# Env — NEVER commit real secrets
.env
.env.local
.env.*.local

# Node
node_modules/
.next/
out/

# IDE
.vscode/
.idea/

# OS
.DS_Store
Thumbs.db
```

- [ ] **Step 4: Create `.env.example`**

```bash
# ============================================================
# .env.example — Copy to .env and fill in real values.
# This file is committed to git. .env is NOT.
# ============================================================

# --- App ---
SECRET_KEY=changeme-must-be-at-least-32-random-chars
DEBUG=false

# --- Database (use postgresql+asyncpg:// for async SQLAlchemy) ---
DATABASE_URL=postgresql+asyncpg://idms_app:devpassword@postgres:5432/idms

# --- Redis ---
REDIS_URL=redis://redis:6379/0

# --- Sentry (leave empty to disable) ---
SENTRY_DSN=

# --- Cloudflare R2 ---
R2_ACCOUNT_ID=
R2_ACCESS_KEY_ID=
R2_SECRET_ACCESS_KEY=
R2_BUCKET=idms-documents
R2_ENDPOINT=https://<ACCOUNT_ID>.r2.cloudflarestorage.com

# --- Mistral (OCR) ---
MISTRAL_API_KEY=

# --- Google AI (Gemini) ---
GOOGLE_AI_API_KEY=
GEMINI_MODEL=gemini-1.5-pro
```

- [ ] **Step 5: Commit**

```bash
git init   # if not already a git repo
git add .gitignore .env.example
git commit -m "chore: monorepo skeleton, .gitignore, .env.example"
```

Verify `.env` is NOT tracked: `git status` should not show `.env`.

---

### Task 2: docker-compose.yml

**Files:**
- Create: `infra/docker-compose.yml`

- [ ] **Step 1: Create `infra/docker-compose.yml`**

```yaml
# infra/docker-compose.yml
services:
  postgres:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_DB: idms
      POSTGRES_USER: idms_app
      POSTGRES_PASSWORD: devpassword
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U idms_app -d idms"]
      interval: 5s
      timeout: 5s
      retries: 10

  redis:
    image: redis:7-alpine
    command: ["redis-server", "--appendonly", "yes"]
    ports:
      - "6379:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 5s
      retries: 10

  api:
    build:
      context: ../api
      dockerfile: Dockerfile
    env_file: ../.env
    ports:
      - "8000:8000"
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy

  worker:
    build:
      context: ../api
      dockerfile: Dockerfile
    command: >
      uv run celery -A app.workers.celery_app worker
      -Q ocr,embed,ai,default -c 4 --loglevel=info
    env_file: ../.env
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy

volumes:
  pgdata: {}
```

- [ ] **Step 2: Copy `.env.example` → `.env` for local dev**

```bash
cp .env.example .env
# Edit .env: set SECRET_KEY to any 32+ char string (dev only, never commit)
```

- [ ] **Step 3: Commit**

```bash
git add infra/docker-compose.yml
git commit -m "chore: docker-compose with pgvector postgres, redis, api, worker"
```

---

### Task 3: FastAPI project setup — pyproject.toml + Dockerfile

**Files:**
- Create: `api/pyproject.toml`
- Create: `api/Dockerfile`

- [ ] **Step 1: Create `api/pyproject.toml`**

```toml
[project]
name = "idms-api"
version = "0.1.0"
description = "Intelligent Document Management System API"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.30.0",
    "sqlalchemy[asyncio]>=2.0.0",
    "asyncpg>=0.29.0",
    "alembic>=1.13.0",
    "pydantic-settings>=2.6.0",
    "celery[redis]>=5.4.0",
    "redis>=5.0.0",
    "structlog>=24.4.0",
    "sentry-sdk[fastapi]>=2.14.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.3.0",
    "pytest-asyncio>=0.24.0",
    "pytest-cov>=5.0.0",
    "httpx>=0.27.0",
    "ruff>=0.6.0",
    "mypy>=1.11.0",
    "bandit[toml]>=1.7.9",
    "types-redis>=4.6.0",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.ruff]
target-version = "py312"
line-length = 88

[tool.ruff.lint]
select = ["E", "F", "I", "N", "W", "UP", "S"]
ignore = ["S101"]  # assert OK in tests

[tool.mypy]
python_version = "3.12"
strict = true
plugins = ["pydantic.mypy"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.bandit]
skips = ["B101"]  # assert statements OK
```

- [ ] **Step 2: Initialize uv and generate lockfile**

```bash
cd api
uv sync --all-extras
```

Expected: Creates `api/.venv/` and `api/uv.lock` (~30s first run).

- [ ] **Step 3: Create `api/Dockerfile`**

```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY . .

CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 4: Commit**

```bash
git add api/pyproject.toml api/uv.lock api/Dockerfile
git commit -m "chore: FastAPI project setup with uv lockfile, Dockerfile"
```

---

### Task 4: Core modules — config, db, logging, telemetry

**Files:**
- Create: `api/app/core/config.py`
- Create: `api/app/core/db.py`
- Create: `api/app/core/logging.py`
- Create: `api/app/core/telemetry.py`

- [ ] **Step 1: Create `api/app/core/config.py`**

```python
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )

    # App
    APP_NAME: str = "IDMS API"
    DEBUG: bool = False
    SECRET_KEY: str

    # Database
    DATABASE_URL: str

    # Redis
    REDIS_URL: str = "redis://redis:6379/0"

    # Sentry (empty = disabled)
    SENTRY_DSN: str = ""

    # Cloudflare R2
    R2_ACCOUNT_ID: str = ""
    R2_ACCESS_KEY_ID: str = ""
    R2_SECRET_ACCESS_KEY: str = ""
    R2_BUCKET: str = ""
    R2_ENDPOINT: str = ""

    # Mistral (OCR)
    MISTRAL_API_KEY: str = ""

    # Google AI (Gemini)
    GOOGLE_AI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-1.5-pro"


settings = Settings()
```

- [ ] **Step 2: Create `api/app/core/db.py`**

```python
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    pool_pre_ping=True,
)

SessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass
```

- [ ] **Step 3: Create `api/app/core/logging.py`**

```python
import logging

import structlog


def configure_logging(debug: bool = False) -> None:
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(level=level)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
```

- [ ] **Step 4: Create `api/app/core/telemetry.py`**

```python
import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration

from app.core.config import settings


def configure_sentry() -> None:
    if not settings.SENTRY_DSN:
        return
    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        integrations=[FastApiIntegration()],
        traces_sample_rate=0.1,
        environment="development" if settings.DEBUG else "production",
    )
```

- [ ] **Step 5: Commit**

```bash
git add api/app/core/
git commit -m "feat: core config (pydantic-settings), async db engine, structlog, Sentry"
```

---

### Task 5: Health endpoints + FastAPI app factory

**Files:**
- Create: `api/app/api/v1/health.py`
- Create: `api/app/main.py`

- [ ] **Step 1: Write the failing test first**

Create `api/tests/integration/test_health.py` (tests come before implementation):

```python
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_liveness(client: AsyncClient) -> None:
    response = await client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_readiness_shape(client: AsyncClient) -> None:
    response = await client.get("/readyz")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ready"
    assert data["db"] == "ok"
    assert data["redis"] == "ok"
```

- [ ] **Step 2: Run to confirm it fails (ImportError expected)**

```bash
cd api
DATABASE_URL=postgresql+asyncpg://idms_app:devpassword@localhost:5432/idms \
REDIS_URL=redis://localhost:6379/0 \
SECRET_KEY=dev-secret-key-at-least-32-chars \
uv run pytest tests/integration/test_health.py -v
```

Expected: `ERROR` — `ModuleNotFoundError` or `ImportError` because `app.main` doesn't exist yet.

- [ ] **Step 3: Create `api/app/api/v1/health.py`**

```python
from fastapi import APIRouter
from sqlalchemy import text

import redis.asyncio as aioredis

from app.core.config import settings
from app.core.db import SessionLocal

router = APIRouter(tags=["health"])


@router.get("/healthz", summary="Liveness probe")
async def liveness() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz", summary="Readiness probe")
async def readiness() -> dict[str, str]:
    async with SessionLocal() as session:
        await session.execute(text("SELECT 1"))

    client = aioredis.from_url(settings.REDIS_URL, socket_connect_timeout=2)
    await client.ping()
    await client.aclose()

    return {"status": "ready", "db": "ok", "redis": "ok"}
```

- [ ] **Step 4: Create `api/app/main.py`**

```python
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.v1.health import router as health_router
from app.core.config import settings
from app.core.logging import configure_logging
from app.core.telemetry import configure_sentry


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    configure_logging(debug=settings.DEBUG)
    configure_sentry()
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        lifespan=lifespan,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
    )
    app.include_router(health_router)
    return app


app = create_app()
```

- [ ] **Step 5: Create `api/tests/conftest.py`**

```python
import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac
```

Add the missing import at the top:
```python
from collections.abc import AsyncGenerator
```

Full `api/tests/conftest.py`:
```python
from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac
```

- [ ] **Step 6: Run integration tests (requires postgres + redis running)**

```bash
cd api
DATABASE_URL=postgresql+asyncpg://idms_app:devpassword@localhost:5432/idms \
REDIS_URL=redis://localhost:6379/0 \
SECRET_KEY=dev-secret-key-at-least-32-chars \
uv run pytest tests/integration/test_health.py -v
```

Expected:
```
PASSED tests/integration/test_health.py::test_liveness
PASSED tests/integration/test_health.py::test_readiness_shape
```

- [ ] **Step 7: Commit**

```bash
git add api/app/api/ api/app/main.py api/tests/conftest.py api/tests/integration/test_health.py
git commit -m "feat: /healthz (liveness) and /readyz (readiness) endpoints with tests"
```

---

### Task 6: Unit tests for config

**Files:**
- Create: `api/tests/unit/test_config.py`

- [ ] **Step 1: Write unit tests**

```python
# api/tests/unit/test_config.py


def test_settings_app_name() -> None:
    from app.core.config import settings

    assert settings.APP_NAME == "IDMS API"


def test_settings_database_url_is_async() -> None:
    from app.core.config import settings

    assert settings.DATABASE_URL.startswith("postgresql+asyncpg://")


def test_settings_redis_url() -> None:
    from app.core.config import settings

    assert settings.REDIS_URL.startswith("redis://")


def test_settings_secret_key_present() -> None:
    from app.core.config import settings

    assert len(settings.SECRET_KEY) >= 8
```

- [ ] **Step 2: Run unit tests**

```bash
cd api
DATABASE_URL=postgresql+asyncpg://idms_app:devpassword@localhost:5432/idms \
REDIS_URL=redis://localhost:6379/0 \
SECRET_KEY=dev-secret-key-at-least-32-chars \
uv run pytest tests/unit/ -v
```

Expected:
```
PASSED tests/unit/test_config.py::test_settings_app_name
PASSED tests/unit/test_config.py::test_settings_database_url_is_async
PASSED tests/unit/test_config.py::test_settings_redis_url
PASSED tests/unit/test_config.py::test_settings_secret_key_present
```

- [ ] **Step 3: Commit**

```bash
git add api/tests/unit/test_config.py
git commit -m "test: unit tests for Settings config"
```

---

### Task 7: Celery workers bootstrap

**Files:**
- Create: `api/app/workers/celery_app.py`
- Create: `api/app/workers/tasks.py`

- [ ] **Step 1: Create `api/app/workers/celery_app.py`**

```python
from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "idms",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.workers.tasks"],
)

celery_app.conf.update(
    task_default_queue="default",
    task_queues={
        "ocr": {},
        "embed": {},
        "ai": {},
        "default": {},
    },
    task_routes={
        "app.workers.tasks.ocr_*": {"queue": "ocr"},
        "app.workers.tasks.embed_*": {"queue": "embed"},
        "app.workers.tasks.ai_*": {"queue": "ai"},
    },
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
)
```

- [ ] **Step 2: Create `api/app/workers/tasks.py`**

```python
from app.workers.celery_app import celery_app


@celery_app.task(queue="default", name="app.workers.tasks.health_check")
def health_check() -> dict[str, str]:
    """Smoke-test task — verifies the worker is alive and processing."""
    return {"status": "ok"}
```

- [ ] **Step 3: Commit**

```bash
git add api/app/workers/
git commit -m "feat: Celery app with ocr/embed/ai/default queues + health_check task"
```

---

### Task 8: Alembic initialization + baseline migration

**Files:**
- Modify: `api/alembic.ini` (generated then patched)
- Modify: `api/migrations/env.py` (replace with async runner)
- `api/migrations/versions/<hash>_baseline.py` (generated)

- [ ] **Step 1: Initialize Alembic**

```bash
cd api
uv run alembic init migrations
```

Expected: Creates `alembic.ini` and populates `migrations/env.py`, `migrations/script.py.mako`. These will be overwritten next.

- [ ] **Step 2: Patch `api/alembic.ini` — clear the hardcoded url**

Find the line `sqlalchemy.url = driver://user:pass@localhost/dbname` and replace with:
```ini
sqlalchemy.url =
```

The url is set programmatically in `env.py` so alembic.ini never contains credentials.

- [ ] **Step 3: Replace `api/migrations/env.py` with async runner**

```python
import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import settings
from app.core.db import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def do_run_migrations(connection):  # type: ignore[no-untyped-def]
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    engine = create_async_engine(settings.DATABASE_URL)
    async with engine.begin() as conn:
        await conn.run_sync(do_run_migrations)
    await engine.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


run_migrations_online()
```

- [ ] **Step 4: Generate baseline migration**

```bash
cd api
DATABASE_URL=postgresql+asyncpg://idms_app:devpassword@localhost:5432/idms \
SECRET_KEY=dev \
uv run alembic revision --autogenerate -m "baseline"
```

Expected: Creates `migrations/versions/<hash>_baseline.py`. Since no models exist yet, `upgrade()` and `downgrade()` will be empty — that is correct.

- [ ] **Step 5: Run migration against local DB**

```bash
cd api
DATABASE_URL=postgresql+asyncpg://idms_app:devpassword@localhost:5432/idms \
SECRET_KEY=dev \
uv run alembic upgrade head
```

Expected: `INFO [alembic.runtime.migration] Running upgrade -> <hash>, baseline`

- [ ] **Step 6: Commit**

```bash
git add api/alembic.ini api/migrations/
git commit -m "chore: Alembic async setup + empty baseline migration"
```

---

### Task 9: Next.js scaffold

**Files:**
- Create: `web/package.json`
- Create: `web/next.config.ts`
- Create: `web/tsconfig.json`
- Create: `web/app/layout.tsx`
- Create: `web/app/page.tsx`
- Create: `web/lib/api.ts`

- [ ] **Step 1: Create `web/package.json`**

```json
{
  "name": "idms-web",
  "version": "0.1.0",
  "private": true,
  "scripts": {
    "dev": "next dev",
    "build": "next build",
    "start": "next start",
    "lint": "next lint",
    "type-check": "tsc --noEmit"
  },
  "dependencies": {
    "next": "14.2.5",
    "react": "^18.3.0",
    "react-dom": "^18.3.0"
  },
  "devDependencies": {
    "@types/node": "^20",
    "@types/react": "^18",
    "@types/react-dom": "^18",
    "eslint": "^8",
    "eslint-config-next": "14.2.5",
    "typescript": "^5"
  }
}
```

- [ ] **Step 2: Create `web/tsconfig.json`**

```json
{
  "compilerOptions": {
    "lib": ["dom", "dom.iterable", "esnext"],
    "allowJs": true,
    "skipLibCheck": true,
    "strict": true,
    "noEmit": true,
    "esModuleInterop": true,
    "module": "esnext",
    "moduleResolution": "bundler",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "jsx": "preserve",
    "incremental": true,
    "plugins": [{ "name": "next" }],
    "paths": { "@/*": ["./*"] }
  },
  "include": ["next-env.d.ts", "**/*.ts", "**/*.tsx", ".next/types/**/*.ts"],
  "exclude": ["node_modules"]
}
```

- [ ] **Step 3: Create `web/next.config.ts`**

```typescript
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
};

export default nextConfig;
```

- [ ] **Step 4: Create `web/app/layout.tsx`**

```tsx
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "IDMS",
  description: "Intelligent Document Management System",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
```

- [ ] **Step 5: Create `web/app/page.tsx`**

```tsx
export default function Home() {
  return (
    <main style={{ fontFamily: "system-ui", padding: "2rem", maxWidth: "800px" }}>
      <h1>IDMS</h1>
      <p>Intelligent Document Management System</p>
      <ul>
        <li>
          <a href="http://localhost:8000/api/docs">API Docs (Swagger)</a>
        </li>
        <li>
          <a href="http://localhost:8000/healthz">API Liveness</a>
        </li>
        <li>
          <a href="http://localhost:8000/readyz">API Readiness</a>
        </li>
      </ul>
    </main>
  );
}
```

- [ ] **Step 6: Create `web/lib/api.ts`**

```typescript
const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...init?.headers,
    },
  });
  if (!res.ok) {
    throw new Error(`API ${res.status}: ${await res.text()}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  health: {
    liveness: () => apiFetch<{ status: string }>("/healthz"),
    readiness: () =>
      apiFetch<{ status: string; db: string; redis: string }>("/readyz"),
  },
};
```

- [ ] **Step 7: Install deps and verify type-check passes**

```bash
cd web
npm install
npm run type-check
```

Expected: `tsc` exits 0, no type errors.

- [ ] **Step 8: Commit**

```bash
git add web/
git commit -m "feat: Next.js 14 scaffold — layout, home page, typed API client"
```

---

### Task 10: Makefile + seed stub

**Files:**
- Create: `Makefile`
- Create: `infra/scripts/seed.py`

- [ ] **Step 1: Create `Makefile`**

```makefile
.PHONY: up down test test-unit test-integration test-security \
        migrate migrate-down seed lint format logs shell-api

up:
	docker compose -f infra/docker-compose.yml up -d --build

down:
	docker compose -f infra/docker-compose.yml down

test:
	cd api && uv run pytest tests/ -v --tb=short

test-unit:
	cd api && uv run pytest tests/unit/ -v

test-integration:
	cd api && uv run pytest tests/integration/ -v

test-security:
	cd api && uv run pytest tests/security/ -v

migrate:
	cd api && uv run alembic upgrade head

migrate-down:
	cd api && uv run alembic downgrade -1

seed:
	cd api && uv run python infra/scripts/seed.py

lint:
	cd api && uv run ruff check . && uv run ruff format --check . && uv run mypy app/
	cd web && npm run lint && npm run type-check

format:
	cd api && uv run ruff format . && uv run ruff check --fix .

logs:
	docker compose -f infra/docker-compose.yml logs -f

shell-api:
	docker compose -f infra/docker-compose.yml exec api bash
```

- [ ] **Step 2: Create `infra/scripts/seed.py`**

```python
"""Dev seed script — verifies DB connectivity and seeds minimal dev data."""
import asyncio

from sqlalchemy import text

from app.core.db import SessionLocal


async def seed() -> None:
    async with SessionLocal() as session:
        result = await session.execute(text("SELECT current_database()"))
        db_name = result.scalar_one()
        print(f"Connected to database: {db_name}")
        print("Phase 0: no seed data needed yet.")


if __name__ == "__main__":
    asyncio.run(seed())
```

- [ ] **Step 3: Verify `make lint` passes**

```bash
make lint
```

Expected: All checks exit 0.

- [ ] **Step 4: Commit**

```bash
git add Makefile infra/scripts/seed.py
git commit -m "chore: Makefile targets (up/down/test/migrate/seed/lint) + seed stub"
```

---

### Task 11: GitHub Actions CI pipeline

**Files:**
- Create: `.github/workflows/ci.yml`

- [ ] **Step 1: Create `.github/workflows/ci.yml`**

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  api:
    name: "API — lint · type-check · tests"
    runs-on: ubuntu-latest

    services:
      postgres:
        image: pgvector/pgvector:pg16
        env:
          POSTGRES_DB: idms_test
          POSTGRES_USER: idms_app
          POSTGRES_PASSWORD: testpassword
        ports: ["5432:5432"]
        options: >-
          --health-cmd "pg_isready -U idms_app -d idms_test"
          --health-interval 10s
          --health-timeout 5s
          --health-retries 10

      redis:
        image: redis:7-alpine
        ports: ["6379:6379"]
        options: >-
          --health-cmd "redis-cli ping"
          --health-interval 5s
          --health-timeout 5s
          --health-retries 10

    env:
      DATABASE_URL: postgresql+asyncpg://idms_app:testpassword@localhost:5432/idms_test
      REDIS_URL: redis://localhost:6379/0
      SECRET_KEY: ci-test-secret-key-minimum-32-chars-here

    defaults:
      run:
        working-directory: api

    steps:
      - uses: actions/checkout@v4

      - uses: astral-sh/setup-uv@v3
        with:
          version: "latest"
          enable-cache: true
          cache-dependency-glob: "api/uv.lock"

      - name: Install dependencies
        run: uv sync --all-extras

      - name: Lint (ruff)
        run: uv run ruff check .

      - name: Format check (ruff)
        run: uv run ruff format --check .

      - name: Type check (mypy)
        run: uv run mypy app/

      - name: Security scan (bandit)
        run: uv run bandit -r app/ -c pyproject.toml

      - name: Run migrations
        run: uv run alembic upgrade head

      - name: Unit tests
        run: uv run pytest tests/unit/ -v --tb=short

      - name: Integration tests
        run: uv run pytest tests/integration/ -v --tb=short

      - name: Security / tenant-isolation tests  # Blocking from Phase 1 onward
        run: uv run pytest tests/security/ -v --tb=short

  web:
    name: "Web — lint · type-check"
    runs-on: ubuntu-latest

    defaults:
      run:
        working-directory: web

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: "20"
          cache: "npm"
          cache-dependency-path: web/package-lock.json

      - name: Install dependencies
        run: npm ci

      - name: Lint
        run: npm run lint

      - name: Type check
        run: npm run type-check
```

- [ ] **Step 2: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: GitHub Actions — lint, type-check, unit/integration/security tests (all blocking)"
```

---

### Task 12: Pre-commit hooks

**Files:**
- Create: `.pre-commit-config.yaml`

- [ ] **Step 1: Create `.pre-commit-config.yaml`**

```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.6.0
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format

  - repo: https://github.com/PyCQA/bandit
    rev: 1.7.9
    hooks:
      - id: bandit
        args: ["-c", "api/pyproject.toml", "-r", "api/app/"]

  - repo: https://github.com/pre-commit/mirrors-prettier
    rev: v4.0.0-alpha.8
    hooks:
      - id: prettier
        files: \.(ts|tsx|js|jsx|json|css|md)$
        exclude: ^web/\.next/

  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.6.0
    hooks:
      - id: check-added-large-files
        args: [--maxkb=500]
      - id: detect-private-key
      - id: check-merge-conflict
      - id: end-of-file-fixer
```

- [ ] **Step 2: Install pre-commit and hooks**

```bash
pip install pre-commit
pre-commit install
```

Expected: `pre-commit installed at .git/hooks/pre-commit`

- [ ] **Step 3: Run hooks against all files**

```bash
pre-commit run --all-files
```

Expected: All hooks pass. Ruff may auto-fix minor style issues — commit those fixes.

- [ ] **Step 4: Commit**

```bash
git add .pre-commit-config.yaml
git commit -m "chore: pre-commit hooks (ruff, bandit, prettier, secret detection)"
```

---

### Task 13: End-to-end verification — Definition of Done check

- [ ] **Step 1: Start the full stack**

```bash
make up
```

Wait ~30s for containers to become healthy, then:

```bash
docker compose -f infra/docker-compose.yml ps
```

Expected: All 4 services (`postgres`, `redis`, `api`, `worker`) show status `running` or `healthy`.

- [ ] **Step 2: Verify liveness**

```bash
curl -s http://localhost:8000/healthz | python -m json.tool
```

Expected:
```json
{"status": "ok"}
```

- [ ] **Step 3: Verify readiness**

```bash
curl -s http://localhost:8000/readyz | python -m json.tool
```

Expected:
```json
{"status": "ready", "db": "ok", "redis": "ok"}
```

- [ ] **Step 4: Verify API docs**

Open `http://localhost:8000/api/docs` — Swagger UI should show `/healthz` and `/readyz`.

- [ ] **Step 5: Run full test suite**

```bash
make test
```

Expected: All tests pass (6 passing: 4 unit + 2 integration + 0 security).

- [ ] **Step 6: Run linter**

```bash
make lint
```

Expected: All checks exit 0.

- [ ] **Step 7: Confirm no secrets in git**

```bash
git log --all --oneline
git grep "SECRET_KEY=\w" -- "*.env" 2>/dev/null && echo "LEAK DETECTED" || echo "No secrets in git"
```

Expected: `No secrets in git`. `.env` must not appear in `git log`.

- [ ] **Step 8: Tag Phase 0 complete**

```bash
git tag v0.0.1 -m "Phase 0: Foundation complete — one-command stack + green CI"
```

---

## Self-Review

**Spec coverage check against playbook Phase 0:**

| Playbook requirement | Covered in task |
|---|---|
| Monorepo structure (§0.1) | Task 1 |
| docker-compose: postgres (pgvector), redis, api, worker | Task 2 |
| `.env.example` documenting every variable | Task 1 |
| Alembic initialized; empty baseline migration | Task 8 |
| FastAPI `/healthz` (liveness) + `/readyz` (DB + Redis) | Task 5 |
| Celery with 4 queues: `ocr`, `embed`, `ai`, `default` | Task 7 |
| Structured JSON logging + Sentry SDK in API + worker | Task 4 |
| Next.js scaffold with health page + API client | Task 9 |
| Makefile: `up`, `down`, `test`, `migrate`, `seed`, `lint` | Task 10 |
| GitHub Actions: lint → type-check → unit → integration → security | Task 11 |
| Pre-commit: ruff/black (→ ruff), bandit, prettier | Task 12 |

All playbook Phase 0 requirements are covered. ✓

---

## Next Plan

After this plan's DoD is met, create:
`docs/superpowers/plans/2026-06-15-idms-phase-1-auth-multitenancy.md`

Phase 1 covers: JWT auth (RS256 access + opaque refresh), Argon2id passwords, PostgreSQL RLS with `FORCE ROW LEVEL SECURITY`, the `get_db` org-context dependency (`SET LOCAL app.current_org_id`), and the **tenant-isolation test suite** (blocking CI from that point forward).
