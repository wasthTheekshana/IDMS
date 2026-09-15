# Platform Super Admin Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a platform-level super admin identity to IDMS that can see every organization's usage (users, documents, AI tokens/cost), toggle four AI capabilities per org, view a per-org document list (metadata only), and suspend/reactivate organizations.

**Architecture:** A fully separate `platform_admins` identity (not a role on the existing `users` table), authenticated through the existing `/api/v1/auth/login` endpoint but issuing a distinctly-typed JWT. All cross-org reads/writes go through a dedicated `idms_platform_admin` Postgres role with the `BYPASSRLS` attribute — the only connection in the system allowed to see rows across organizations — keeping the existing FORCE-RLS tenant isolation completely intact for every other code path.

**Tech Stack:** FastAPI, SQLAlchemy 2.0 async, Alembic, PostgreSQL 16 (BYPASSRLS role), Redis (admin refresh tokens under a separate key namespace), Next.js/React (new `/admin` route), no new dependencies.

**Spec:** `docs/superpowers/specs/2026-09-14-platform-super-admin-design.md`

## Global Constraints

- Every tenant table keeps `FORCE ROW LEVEL SECURITY` exactly as-is — this plan never weakens it. The only new bypass is the dedicated `idms_platform_admin` role.
- The `idms_platform_admin` Postgres role is cluster-wide (not per-database) — its creation in the migration MUST be idempotent (`IF NOT EXISTS`), because the same migration also runs against `idms_test` in the same Postgres cluster.
- Platform admin JWTs carry `"type": "access"` (unchanged, satisfies the existing `_get_token_payload` check) plus a new `"account_type": "platform_admin"` claim — never repurpose the existing `"type"` claim.
- AI toggle defaults: `ai_qa_enabled=true`, `ai_summarization_enabled=true`, `ai_search_answer_enabled=true`, `ai_extraction_enabled=false`.
- Platform admin document access is metadata-only — never expose `extracted_text` or a preview URL through `/platform-admin/*`.
- No new Python or npm dependencies — `argparse`/`getpass` (stdlib) for the bootstrap script, existing `passlib`/`jose` for auth.
- All new backend code follows existing patterns exactly: repository classes take `session` in `__init__`, services take `(session, ...)` positionally, routers use `AuthSession`/`CurrentUserDep`-style `Annotated` dependencies, `ValueError` in a service maps to 404 in its router (established in `templates.py`).
- Run `cd api && make test` (or the equivalent `TESTING=true DATABASE_URL=... uv run pytest tests/ -v`) after every backend task. Run `cd web && npm run build` after every frontend task (this project's `next build` also type-checks).

---

## Task 1: Migration — `platform_admins` table, organization columns, BYPASSRLS role

**Files:**

- Create: `api/migrations/versions/006_platform_admin.py`
- Modify: `api/app/core/config.py` (add `PLATFORM_ADMIN_DATABASE_URL`, `PLATFORM_ADMIN_DB_PASSWORD`)
- Modify: `api/.env`, `.env.docker`, `.env.example` (add the two new vars)
- Modify: `Makefile` (add `PLATFORM_ADMIN_DATABASE_URL` to `TEST_ENV`)

**Interfaces:**

- Produces: `settings.PLATFORM_ADMIN_DATABASE_URL: str`, `settings.PLATFORM_ADMIN_DB_PASSWORD: str` — consumed by Task 4 (`core/db.py`) and this migration itself.
- Produces (DB): table `platform_admins(id, email, password_hash, is_active, created_at, last_login_at)`; `organizations` gains `is_suspended`, `ai_qa_enabled`, `ai_summarization_enabled`, `ai_search_answer_enabled`, `ai_extraction_enabled` (all `NOT NULL` with the defaults listed in Global Constraints); Postgres role `idms_platform_admin` with `LOGIN BYPASSRLS`, granted `SELECT` on `organizations`/`users`/`documents`/`api_usage` and column-level `UPDATE` on the 5 new `organizations` columns.

- [ ] **Step 1: Add the two settings fields**

In `api/app/core/config.py`, add after the `Database` section (after `DATABASE_URL: str`):

```python
    # Platform admin — dedicated BYPASSRLS Postgres role for cross-org reads.
    # Defaults are syntactically valid but non-functional placeholders; every
    # real environment must override both in its .env file.
    PLATFORM_ADMIN_DATABASE_URL: str = (
        "postgresql+asyncpg://idms_platform_admin:changeme@localhost:5432/idms"
    )
    PLATFORM_ADMIN_DB_PASSWORD: str = "changeme-platform-admin-password"
```

- [ ] **Step 2: Add real values to the env files**

In `api/.env`, add after the `DATABASE_URL` line:

```
PLATFORM_ADMIN_DATABASE_URL=postgresql+asyncpg://idms_platform_admin:devplatformadmin123@localhost:5432/idms
PLATFORM_ADMIN_DB_PASSWORD=devplatformadmin123
```

In `.env.docker`, add after the `DATABASE_URL` line:

```
PLATFORM_ADMIN_DATABASE_URL=postgresql+asyncpg://idms_platform_admin:devplatformadmin123@postgres:5432/idms
PLATFORM_ADMIN_DB_PASSWORD=devplatformadmin123
```

In `.env.example`, add after the `DATABASE_URL` line:

```
PLATFORM_ADMIN_DATABASE_URL=postgresql+asyncpg://idms_platform_admin:changeme@postgres:5432/idms
PLATFORM_ADMIN_DB_PASSWORD=changeme
```

- [ ] **Step 3: Wire the test environment**

In `Makefile`, change:

```makefile
TEST_ENV = TESTING=true DATABASE_URL=postgresql+asyncpg://idms_app:devpassword@127.0.0.1:5432/idms_test
```

to:

```makefile
TEST_ENV = TESTING=true DATABASE_URL=postgresql+asyncpg://idms_app:devpassword@127.0.0.1:5432/idms_test PLATFORM_ADMIN_DATABASE_URL=postgresql+asyncpg://idms_platform_admin:devplatformadmin123@127.0.0.1:5432/idms_test
```

- [ ] **Step 4: Write the migration**

Create `api/migrations/versions/006_platform_admin.py`:

```python
"""Platform admin: platform_admins table, organization suspend/AI-toggle
columns, and the idms_platform_admin BYPASSRLS role for cross-org reads.

Revision ID: 006
Revises: 005
Create Date: 2026-09-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.core.config import settings

revision: str = "006"
down_revision: str | None = "005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "platform_admins",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean, server_default="true", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_platform_admins_email", "platform_admins", ["email"], unique=True
    )

    op.add_column(
        "organizations",
        sa.Column("is_suspended", sa.Boolean, server_default="false", nullable=False),
    )
    op.add_column(
        "organizations",
        sa.Column("ai_qa_enabled", sa.Boolean, server_default="true", nullable=False),
    )
    op.add_column(
        "organizations",
        sa.Column(
            "ai_summarization_enabled", sa.Boolean, server_default="true", nullable=False
        ),
    )
    op.add_column(
        "organizations",
        sa.Column(
            "ai_search_answer_enabled", sa.Boolean, server_default="true", nullable=False
        ),
    )
    op.add_column(
        "organizations",
        sa.Column(
            "ai_extraction_enabled", sa.Boolean, server_default="false", nullable=False
        ),
    )

    # ── Platform-admin DB role ──────────────────────────────────────────────
    # BYPASSRLS lets this role read/write across every org — it's the ONLY
    # role that can; every other connection is still subject to FORCE RLS.
    # Roles are cluster-wide (not per-database), so creation must be
    # idempotent — this same migration also runs against idms_test, which
    # shares the Postgres cluster/role namespace with the main idms database.
    #
    # The password is trusted server-side config (not user input), so
    # interpolating it into DDL here follows the same pattern already used
    # for org_id in core/deps.py's SET LOCAL statement.
    password = settings.PLATFORM_ADMIN_DB_PASSWORD
    assert "'" not in password, "PLATFORM_ADMIN_DB_PASSWORD must not contain '"
    op.execute(f"""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'idms_platform_admin') THEN
                CREATE ROLE idms_platform_admin WITH LOGIN PASSWORD '{password}' BYPASSRLS;
            END IF;
        END
        $$;
    """)
    op.execute("GRANT SELECT ON organizations TO idms_platform_admin")
    op.execute(
        "GRANT UPDATE (is_suspended, ai_qa_enabled, ai_summarization_enabled, "
        "ai_search_answer_enabled, ai_extraction_enabled) ON organizations "
        "TO idms_platform_admin"
    )
    op.execute("GRANT SELECT ON users TO idms_platform_admin")
    op.execute("GRANT SELECT ON documents TO idms_platform_admin")
    op.execute("GRANT SELECT ON api_usage TO idms_platform_admin")


def downgrade() -> None:
    # Deliberately does NOT drop the idms_platform_admin role or its grants —
    # it's a cluster-wide principal that idms_test's copy of this migration
    # also depends on; dropping it here could break the other database.
    # Removing it for real is a manual DBA step: DROP ROLE idms_platform_admin;
    op.drop_column("organizations", "ai_extraction_enabled")
    op.drop_column("organizations", "ai_search_answer_enabled")
    op.drop_column("organizations", "ai_summarization_enabled")
    op.drop_column("organizations", "ai_qa_enabled")
    op.drop_column("organizations", "is_suspended")
    op.drop_index("ix_platform_admins_email", table_name="platform_admins")
    op.drop_table("platform_admins")
```

- [ ] **Step 5: Run the migration against the dev database and verify**

```bash
cd api && uv run alembic upgrade head
```

Then verify the role and columns exist:

```bash
docker exec infra-postgres-1 psql -U idms_app -d idms -c "\du idms_platform_admin"
docker exec infra-postgres-1 psql -U idms_app -d idms -c "\d organizations"
docker exec infra-postgres-1 psql -U idms_app -d idms -c "\d platform_admins"
```

Expected: `idms_platform_admin` row shows `Bypass RLS` in its attributes; `organizations` lists the 5 new columns; `platform_admins` table exists.

- [ ] **Step 6: Provision the test database and verify idempotency**

```bash
make test-db
```

Expected: this re-runs `alembic upgrade head` against `idms_test` in the same cluster — it must succeed without a "role already exists" error, proving the `IF NOT EXISTS` guard works.

- [ ] **Step 7: Commit**

```bash
git add api/migrations/versions/006_platform_admin.py api/app/core/config.py api/.env .env.docker .env.example Makefile
git commit -m "feat(api): platform admin schema, BYPASSRLS role, and env wiring"
```

---

## Task 2: Models — `PlatformAdmin`, `Organization` new columns, test truncation

**Files:**

- Create: `api/app/models/platform_admin.py`
- Modify: `api/app/models/organization.py`
- Modify: `api/tests/conftest.py`
- Test: `api/tests/unit/test_platform_admin_model.py`

**Interfaces:**

- Consumes: table `platform_admins` and the 5 new `organizations` columns from Task 1.
- Produces: `PlatformAdmin` ORM class (`id`, `email`, `password_hash`, `is_active`, `created_at`, `last_login_at`); `Organization` gains attributes `is_suspended: bool`, `ai_qa_enabled: bool`, `ai_summarization_enabled: bool`, `ai_search_answer_enabled: bool`, `ai_extraction_enabled: bool` — consumed by every later task.

- [ ] **Step 1: Write the failing test**

Create `api/tests/unit/test_platform_admin_model.py`:

```python
import uuid

import pytest
from sqlalchemy import select

from app.core.db import SessionLocal
from app.core.security import hash_password
from app.models.platform_admin import PlatformAdmin


@pytest.mark.asyncio
async def test_platform_admin_round_trips_through_db() -> None:
    admin_id = uuid.uuid4()
    async with SessionLocal.begin() as session:
        session.add(
            PlatformAdmin(
                id=admin_id,
                email="round-trip@example.com",
                password_hash=hash_password("password1234"),
            )
        )

    async with SessionLocal() as session:
        result = await session.execute(
            select(PlatformAdmin).where(PlatformAdmin.id == admin_id)
        )
        admin = result.scalar_one()
        assert admin.email == "round-trip@example.com"
        assert admin.is_active is True
        assert admin.last_login_at is None


@pytest.mark.asyncio
async def test_organization_has_ai_toggle_defaults(auth_client: tuple) -> None:  # type: ignore[type-arg]
    from app.repositories.organization import OrgRepository

    client, tokens = auth_client
    me = await client.get("/api/v1/users/me")
    org_id = uuid.UUID(me.json()["org_id"])

    async with SessionLocal() as session:
        org = await OrgRepository(session).get_by_id(org_id)
        assert org is not None
        assert org.is_suspended is False
        assert org.ai_qa_enabled is True
        assert org.ai_summarization_enabled is True
        assert org.ai_search_answer_enabled is True
        assert org.ai_extraction_enabled is False
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd api && TESTING=true DATABASE_URL=postgresql+asyncpg://idms_app:devpassword@127.0.0.1:5432/idms_test uv run pytest tests/unit/test_platform_admin_model.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'app.models.platform_admin'`.

- [ ] **Step 3: Create the `PlatformAdmin` model**

Create `api/app/models/platform_admin.py`:

```python
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class PlatformAdmin(Base):
    """A platform-level admin account — separate from the org-scoped `users`
    table entirely. Not RLS-protected: holds no tenant data."""

    __tablename__ = "platform_admins"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(
        String(255), nullable=False, unique=True, index=True
    )
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, server_default="true")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
```

- [ ] **Step 4: Add the new columns to the `Organization` model**

In `api/app/models/organization.py`, add `Boolean` to the import and add the 5 fields after `pages_used_this_month`:

```python
from sqlalchemy import Boolean, DateTime, Integer, String, func
```

```python
    pages_used_this_month: Mapped[int] = mapped_column(Integer, server_default="0")
    is_suspended: Mapped[bool] = mapped_column(Boolean, server_default="false")
    ai_qa_enabled: Mapped[bool] = mapped_column(Boolean, server_default="true")
    ai_summarization_enabled: Mapped[bool] = mapped_column(
        Boolean, server_default="true"
    )
    ai_search_answer_enabled: Mapped[bool] = mapped_column(
        Boolean, server_default="true"
    )
    ai_extraction_enabled: Mapped[bool] = mapped_column(
        Boolean, server_default="false"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
```

- [ ] **Step 5: Add `platform_admins` to the test truncation list**

In `api/tests/conftest.py`, change the `_sql` in `clean_db`:

```python
    _sql = (
        "TRUNCATE TABLE document_chunks, api_usage, documents,"
        " audit_logs, users, organizations, platform_admins RESTART IDENTITY CASCADE"
    )
```

- [ ] **Step 6: Run test to verify it passes**

```bash
cd api && TESTING=true DATABASE_URL=postgresql+asyncpg://idms_app:devpassword@127.0.0.1:5432/idms_test uv run pytest tests/unit/test_platform_admin_model.py -v
```

Expected: PASS (2 tests).

- [ ] **Step 7: Run the full suite to confirm nothing else broke**

```bash
make test
```

Expected: all existing tests still PASS (the `clean_db` truncation change should be transparent to every other test).

- [ ] **Step 8: Commit**

```bash
git add api/app/models/platform_admin.py api/app/models/organization.py api/tests/conftest.py api/tests/unit/test_platform_admin_model.py
git commit -m "feat(api): PlatformAdmin model and organization AI-toggle/suspend columns"
```

---

## Task 3: Security helpers — platform admin token + admin refresh key

**Files:**

- Modify: `api/app/core/security.py`
- Test: `api/tests/unit/test_security_platform_admin.py`

**Interfaces:**

- Consumes: `settings.JWT_SECRET_KEY`, `settings.JWT_ALGORITHM`, `settings.ACCESS_TOKEN_EXPIRE_MINUTES` (existing).
- Produces: `create_platform_admin_token(admin_id: str) -> str`, `admin_refresh_token_redis_key(token_id: str) -> str` — consumed by Task 6 (`services/auth.py`).

- [ ] **Step 1: Write the failing test**

Create `api/tests/unit/test_security_platform_admin.py`:

```python
from app.core.security import (
    admin_refresh_token_redis_key,
    create_platform_admin_token,
    decode_access_token,
)


def test_create_platform_admin_token_carries_account_type() -> None:
    token = create_platform_admin_token("11111111-1111-1111-1111-111111111111")
    payload = decode_access_token(token)
    assert payload["sub"] == "11111111-1111-1111-1111-111111111111"
    assert payload["account_type"] == "platform_admin"
    assert payload["type"] == "access"
    assert "org_id" not in payload
    assert "role" not in payload


def test_admin_refresh_token_redis_key_is_namespaced_separately() -> None:
    key = admin_refresh_token_redis_key("abc-123")
    assert key == "admin_refresh:abc-123"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd api && TESTING=true DATABASE_URL=postgresql+asyncpg://idms_app:devpassword@127.0.0.1:5432/idms_test uv run pytest tests/unit/test_security_platform_admin.py -v
```

Expected: FAIL with `ImportError: cannot import name 'create_platform_admin_token'`.

- [ ] **Step 3: Implement**

In `api/app/core/security.py`, add after `create_access_token`:

```python
def create_platform_admin_token(admin_id: str) -> str:
    expire = datetime.now(UTC) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload: dict[str, Any] = {
        "sub": admin_id,
        "account_type": "platform_admin",
        "exp": expire,
        "type": "access",
    }
    return jwt.encode(
        payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM
    )  # type: ignore[no-any-return]
```

And after `refresh_token_redis_key`:

```python
def admin_refresh_token_redis_key(token_id: str) -> str:
    return f"admin_refresh:{token_id}"
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd api && TESTING=true DATABASE_URL=postgresql+asyncpg://idms_app:devpassword@127.0.0.1:5432/idms_test uv run pytest tests/unit/test_security_platform_admin.py -v
```

Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add api/app/core/security.py api/tests/unit/test_security_platform_admin.py
git commit -m "feat(api): platform admin token + namespaced refresh key"
```

---

## Task 4: DB session + FastAPI dependencies — admin bypass session, token-type guards, suspension check

**This is the security-critical task.** It wires the `idms_platform_admin` engine, adds the `get_current_platform_admin` dependency, and closes off two ways a platform-admin token could otherwise be misused against org-scoped endpoints (and vice versa) plus makes org suspension take effect immediately.

**Files:**

- Modify: `api/app/core/db.py`
- Modify: `api/app/core/deps.py`
- Test: `api/tests/security/test_platform_admin_isolation.py`

**Interfaces:**

- Consumes: `settings.PLATFORM_ADMIN_DATABASE_URL` (Task 1), `create_platform_admin_token` (Task 3).
- Produces: `AdminSessionLocal` (in `core/db.py`); `get_admin_db`, `AdminSession`, `CurrentPlatformAdmin`, `get_current_platform_admin`, `CurrentPlatformAdminDep` (in `core/deps.py`) — consumed by Task 8's router. Also modifies `get_db` and `get_current_user` to reject platform-admin tokens and to 403 on a suspended org.

- [ ] **Step 1: Write the failing tests**

Create `api/tests/security/test_platform_admin_isolation.py`:

```python
"""
BLOCKING CI GATE — platform admin isolation.

The idms_platform_admin BYPASSRLS session must see rows across every org
(that's its entire purpose); every normal org session must still never see
another org's rows even though both now exist in the same database. A
platform-admin token must not work against org-scoped endpoints, and an
org token must not work against platform-admin endpoints.
"""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.db import AdminSessionLocal
from app.core.security import hash_password
from app.models.organization import Organization
from app.models.platform_admin import PlatformAdmin


async def _create_platform_admin(email: str, password: str) -> None:
    from app.core.db import SessionLocal

    async with SessionLocal.begin() as session:
        session.add(
            PlatformAdmin(
                id=uuid.uuid4(), email=email, password_hash=hash_password(password)
            )
        )


@pytest.mark.asyncio
async def test_admin_session_sees_rows_across_multiple_orgs(
    auth_client: tuple[AsyncClient, dict],  # type: ignore[type-arg]
    second_auth_client: tuple[AsyncClient, dict],  # type: ignore[type-arg]
) -> None:
    """Proves the BYPASSRLS bypass actually works — the whole point of the role."""
    async with AdminSessionLocal() as session:
        result = await session.execute(select(Organization))
        orgs = result.scalars().all()
        assert len(orgs) >= 2, (
            "Admin session must see both orgs created by the fixtures — "
            "BYPASSRLS is not working"
        )


@pytest.mark.asyncio
async def test_normal_org_session_still_isolated(
    auth_client: tuple[AsyncClient, dict],  # type: ignore[type-arg]
    second_auth_client: tuple[AsyncClient, dict],  # type: ignore[type-arg]
) -> None:
    """Proves the bypass is contained to the admin role only."""
    client_a, _ = auth_client
    client_b, _ = second_auth_client

    orgs_a = await client_a.get("/api/v1/users/me")
    orgs_b = await client_b.get("/api/v1/users/me")
    assert orgs_a.json()["org_id"] != orgs_b.json()["org_id"]

    # Org A's own document listing must never contain anything from org B —
    # covered already by test_tenant_isolation.py; this test only re-confirms
    # the two fixtures produced genuinely different orgs for the test above.


@pytest.mark.asyncio
async def test_platform_admin_login_returns_admin_account_type(
    client: AsyncClient,
) -> None:
    await _create_platform_admin("admin@dok.example.com", "adminpassword123")

    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "admin@dok.example.com", "password": "adminpassword123"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["account_type"] == "platform_admin"


@pytest.mark.asyncio
async def test_platform_admin_token_rejected_by_org_endpoint(
    client: AsyncClient,
) -> None:
    await _create_platform_admin("admin2@dok.example.com", "adminpassword123")
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "admin2@dok.example.com", "password": "adminpassword123"},
    )
    admin_token = login.json()["access_token"]

    resp = await client.get(
        "/api/v1/users/me", headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_org_token_rejected_by_platform_admin_endpoint(
    auth_client: tuple[AsyncClient, dict],  # type: ignore[type-arg]
) -> None:
    client, _ = auth_client
    resp = await client.get("/api/v1/platform-admin/organizations")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_suspended_org_blocks_existing_token_immediately(
    auth_client: tuple[AsyncClient, dict],  # type: ignore[type-arg]
) -> None:
    """A token issued before suspension must stop working on its very next
    request — not just at next login."""
    client, _ = auth_client

    me = await client.get("/api/v1/users/me")
    assert me.status_code == 200
    org_id = me.json()["org_id"]

    async with AdminSessionLocal.begin() as session:
        result = await session.execute(
            select(Organization).where(Organization.id == uuid.UUID(org_id))
        )
        org = result.scalar_one()
        org.is_suspended = True

    resp = await client.get("/api/v1/users/me")
    assert resp.status_code == 403
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd api && TESTING=true DATABASE_URL=postgresql+asyncpg://idms_app:devpassword@127.0.0.1:5432/idms_test PLATFORM_ADMIN_DATABASE_URL=postgresql+asyncpg://idms_platform_admin:devplatformadmin123@127.0.0.1:5432/idms_test uv run pytest tests/security/test_platform_admin_isolation.py -v
```

Expected: FAIL — `ImportError: cannot import name 'AdminSessionLocal'`.

- [ ] **Step 3: Add the admin engine to `core/db.py`**

In `api/app/core/db.py`, after the existing `engine`/`SessionLocal` definitions and before `class Base`:

```python
admin_engine = create_async_engine(
    settings.PLATFORM_ADMIN_DATABASE_URL,
    echo=settings.DEBUG,
    pool_pre_ping=True,
    **_pool_kwargs,  # type: ignore[arg-type]
)

AdminSessionLocal = async_sessionmaker(
    admin_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)
```

- [ ] **Step 4: Add the platform-admin dependencies to `core/deps.py`**

In `api/app/core/deps.py`, add the import and the new pieces. First, update the import line:

```python
from app.core.db import AdminSessionLocal, SessionLocal
```

Add after `get_public_db`:

```python
async def get_admin_db() -> AsyncGenerator[AsyncSession, None]:
    """Cross-org session via the BYPASSRLS idms_platform_admin role.
    No SET LOCAL org context — the whole point is reading across every org.
    Only platform-admin routes may depend on this."""
    async with AdminSessionLocal.begin() as session:
        yield session


AdminSession = Annotated[AsyncSession, Depends(get_admin_db)]
```

Replace `get_db` with:

```python
async def get_db(payload: TokenPayload) -> AsyncGenerator[AsyncSession, None]:
    """Authenticated DB session. Sets org context via SET LOCAL so RLS activates."""
    if payload.get("account_type") == "platform_admin":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Platform admin tokens cannot access organization-scoped endpoints",
        )
    org_id = str(
        _uuid_module.UUID(payload["org_id"])
    )  # validated — safe to interpolate
    async with SessionLocal.begin() as session:
        # SET LOCAL does not support parameterized queries in PostgreSQL.
        # org_id is validated as a UUID above so interpolation is safe.
        await session.execute(text(f"SET LOCAL app.current_org_id = '{org_id}'"))
        suspended = await session.execute(
            text("SELECT is_suspended FROM organizations WHERE id = :oid"),
            {"oid": org_id},
        )
        if suspended.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This organization has been suspended. Contact support.",
            )
        yield session
```

Replace `get_current_user` with:

```python
async def get_current_user(payload: TokenPayload) -> CurrentUser:
    if payload.get("account_type") == "platform_admin":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Platform admin tokens cannot access organization-scoped endpoints",
        )
    return CurrentUser(
        user_id=payload["sub"],
        org_id=payload["org_id"],
        role=payload["role"],
    )
```

Add after `CurrentUserDep`:

```python
class CurrentPlatformAdmin:
    __slots__ = ("admin_id",)

    def __init__(self, admin_id: str) -> None:
        self.admin_id = uuid.UUID(admin_id)


async def get_current_platform_admin(payload: TokenPayload) -> CurrentPlatformAdmin:
    if payload.get("account_type") != "platform_admin":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not a platform admin token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return CurrentPlatformAdmin(admin_id=payload["sub"])


CurrentPlatformAdminDep = Annotated[
    CurrentPlatformAdmin, Depends(get_current_platform_admin)
]
```

- [ ] **Step 5: Run tests — expect the login-dependent ones still failing**

```bash
cd api && TESTING=true DATABASE_URL=postgresql+asyncpg://idms_app:devpassword@127.0.0.1:5432/idms_test PLATFORM_ADMIN_DATABASE_URL=postgresql+asyncpg://idms_platform_admin:devplatformadmin123@127.0.0.1:5432/idms_test uv run pytest tests/security/test_platform_admin_isolation.py -v
```

Expected: `test_admin_session_sees_rows_across_multiple_orgs`, `test_normal_org_session_still_isolated`, and `test_suspended_org_blocks_existing_token_immediately` PASS. `test_platform_admin_login_returns_admin_account_type`, `test_platform_admin_token_rejected_by_org_endpoint`, and `test_org_token_rejected_by_platform_admin_endpoint` still FAIL (login doesn't check `platform_admins` yet, and the `/platform-admin/organizations` route doesn't exist yet) — that's expected; they're finished by Tasks 6 and 8.

- [ ] **Step 6: Commit**

```bash
git add api/app/core/db.py api/app/core/deps.py api/tests/security/test_platform_admin_isolation.py
git commit -m "feat(api): admin BYPASSRLS session, token-type guards, immediate suspension check"
```

---

## Task 5: `PlatformAdminRepository`

**Files:**

- Create: `api/app/repositories/platform_admin.py`
- Test: `api/tests/unit/test_platform_admin_repository.py`

**Interfaces:**

- Consumes: `PlatformAdmin` model (Task 2).
- Produces: `PlatformAdminRepository(session)` with `get_by_email(email) -> PlatformAdmin | None`, `get_by_id(admin_id) -> PlatformAdmin | None`, `update_last_login(admin) -> None` — consumed by Task 6 (`services/auth.py`) and Task 8 (`/platform-admin/me`).

- [ ] **Step 1: Write the failing test**

Create `api/tests/unit/test_platform_admin_repository.py`:

```python
import uuid
from datetime import UTC, datetime

import pytest

from app.core.db import SessionLocal
from app.core.security import hash_password
from app.models.platform_admin import PlatformAdmin
from app.repositories.platform_admin import PlatformAdminRepository


@pytest.mark.asyncio
async def test_get_by_email_and_update_last_login() -> None:
    admin_id = uuid.uuid4()
    async with SessionLocal.begin() as session:
        session.add(
            PlatformAdmin(
                id=admin_id,
                email="repo-test@example.com",
                password_hash=hash_password("password1234"),
            )
        )

    async with SessionLocal.begin() as session:
        repo = PlatformAdminRepository(session)

        found = await repo.get_by_email("repo-test@example.com")
        assert found is not None
        assert found.id == admin_id
        assert found.last_login_at is None

        by_id = await repo.get_by_id(admin_id)
        assert by_id is not None

        before = datetime.now(UTC)
        await repo.update_last_login(found)
        assert found.last_login_at is not None
        assert found.last_login_at >= before

    assert await PlatformAdminRepository(SessionLocal()).get_by_email(
        "nobody@example.com"
    ) is None
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd api && TESTING=true DATABASE_URL=postgresql+asyncpg://idms_app:devpassword@127.0.0.1:5432/idms_test uv run pytest tests/unit/test_platform_admin_repository.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'app.repositories.platform_admin'`.

- [ ] **Step 3: Implement**

Create `api/app/repositories/platform_admin.py`:

```python
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.platform_admin import PlatformAdmin


class PlatformAdminRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def get_by_email(self, email: str) -> PlatformAdmin | None:
        result = await self._s.execute(
            select(PlatformAdmin).where(PlatformAdmin.email == email)
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, admin_id: uuid.UUID) -> PlatformAdmin | None:
        result = await self._s.execute(
            select(PlatformAdmin).where(PlatformAdmin.id == admin_id)
        )
        return result.scalar_one_or_none()

    async def update_last_login(self, admin: PlatformAdmin) -> None:
        admin.last_login_at = datetime.now(UTC)
        await self._s.flush()
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd api && TESTING=true DATABASE_URL=postgresql+asyncpg://idms_app:devpassword@127.0.0.1:5432/idms_test uv run pytest tests/unit/test_platform_admin_repository.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add api/app/repositories/platform_admin.py api/tests/unit/test_platform_admin_repository.py
git commit -m "feat(api): PlatformAdminRepository"
```

---

## Task 6: Wire platform admin login into `services/auth.py`

**Files:**

- Modify: `api/app/schemas/auth.py`
- Modify: `api/app/services/auth.py`
- Modify: `api/tests/conftest.py` (add `platform_admin_client` fixture)
- Test: (extends `api/tests/security/test_platform_admin_isolation.py` from Task 4 — those login-dependent tests now pass)

**Interfaces:**

- Consumes: `PlatformAdminRepository` (Task 5), `create_platform_admin_token`/`admin_refresh_token_redis_key` (Task 3).
- Produces: `TokenResponse.account_type: str`; `login()`/`refresh_tokens()`/`logout()` handle both account types — consumed by every later integration test and the frontend (Task 12).

- [ ] **Step 1: Add `account_type` to `TokenResponse`**

In `api/app/schemas/auth.py`:

```python
class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"  # noqa: S105 — OAuth2 token type, not a secret
    account_type: str = "org_user"
```

- [ ] **Step 2: Add the admin refresh-token store helper and rewrite `login`/`refresh_tokens`/`logout`**

In `api/app/services/auth.py`, add the import:

```python
from app.core.security import (
    admin_refresh_token_redis_key,
    create_access_token,
    create_platform_admin_token,
    hash_password,
    make_refresh_token_id,
    refresh_token_redis_key,
    verify_password,
)
from app.repositories.platform_admin import PlatformAdminRepository
```

Add after `_store_refresh_token`:

```python
async def _store_admin_refresh_token(
    redis_client: aioredis.Redis,  # type: ignore[type-arg]
    token_id: str,
    admin_id: str,
) -> None:
    key = admin_refresh_token_redis_key(token_id)
    value = json.dumps({"admin_id": admin_id})
    expire = int(timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS).total_seconds())
    await redis_client.set(key, value, ex=expire)
```

Replace `login`:

```python
async def login(body: LoginRequest, session: AsyncSession) -> TokenResponse:
    admin_repo = PlatformAdminRepository(session)
    admin = await admin_repo.get_by_email(body.email)
    if admin:
        if not admin.is_active or not verify_password(
            body.password, admin.password_hash
        ):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials"
            )
        await admin_repo.update_last_login(admin)

        access_token = create_platform_admin_token(str(admin.id))
        refresh_id = make_refresh_token_id()
        redis_client = aioredis.from_url(settings.REDIS_URL)
        try:
            await _store_admin_refresh_token(redis_client, refresh_id, str(admin.id))
        finally:
            await redis_client.aclose()
        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_id,
            account_type="platform_admin",
        )

    user_repo = UserRepository(session)
    user = await user_repo.get_by_email(body.email)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials"
        )

    if user.locked_until and user.locked_until > datetime.now(UTC):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account temporarily locked",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account is deactivated. Contact your organization admin.",
        )

    if not verify_password(body.password, user.password_hash):
        # Use a separate transaction so the failed-login count is committed
        # even though the outer transaction will rollback on HTTPException.
        async with SessionLocal.begin() as fail_session:
            fail_repo = UserRepository(fail_session)
            fail_user = await fail_repo.get_by_email(body.email)
            if fail_user:
                await fail_repo.increment_failed_login(fail_user)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials"
        )

    org = await OrgRepository(session).get_by_id(user.org_id)
    if org and org.is_suspended:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This organization has been suspended. Contact support.",
        )

    await user_repo.reset_failed_login(user)

    access_token = create_access_token(str(user.id), str(user.org_id), user.role.value)
    refresh_id = make_refresh_token_id()

    redis_client = aioredis.from_url(settings.REDIS_URL)
    try:
        await _store_refresh_token(
            redis_client,
            refresh_id,
            str(user.id),
            str(user.org_id),
            user.role.value,
        )
    finally:
        await redis_client.aclose()

    return TokenResponse(access_token=access_token, refresh_token=refresh_id)
```

Replace `refresh_tokens`:

```python
async def refresh_tokens(refresh_token_id: str) -> TokenResponse:
    redis_client = aioredis.from_url(settings.REDIS_URL)
    try:
        admin_key = admin_refresh_token_redis_key(refresh_token_id)
        raw_admin = await redis_client.get(admin_key)
        if raw_admin:
            await redis_client.delete(admin_key)
            data = json.loads(raw_admin)
            new_access = create_platform_admin_token(data["admin_id"])
            new_refresh_id = make_refresh_token_id()
            await _store_admin_refresh_token(
                redis_client, new_refresh_id, data["admin_id"]
            )
            return TokenResponse(
                access_token=new_access,
                refresh_token=new_refresh_id,
                account_type="platform_admin",
            )

        key = refresh_token_redis_key(refresh_token_id)
        raw = await redis_client.get(key)
        if not raw:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token"
            )

        await redis_client.delete(key)
        data = json.loads(raw)

        new_access = create_access_token(data["user_id"], data["org_id"], data["role"])
        new_refresh_id = make_refresh_token_id()
        await _store_refresh_token(
            redis_client,
            new_refresh_id,
            data["user_id"],
            data["org_id"],
            data["role"],
        )
        return TokenResponse(access_token=new_access, refresh_token=new_refresh_id)
    finally:
        await redis_client.aclose()
```

Replace `logout`:

```python
async def logout(refresh_token_id: str) -> None:
    redis_client = aioredis.from_url(settings.REDIS_URL)
    try:
        await redis_client.delete(refresh_token_redis_key(refresh_token_id))
        await redis_client.delete(admin_refresh_token_redis_key(refresh_token_id))
    finally:
        await redis_client.aclose()
```

- [ ] **Step 3: Add the `platform_admin_client` fixture**

In `api/tests/conftest.py`, add at the end:

```python
@pytest.fixture
async def platform_admin_client(
    client: AsyncClient,
) -> tuple[AsyncClient, dict]:  # type: ignore[type-arg]
    """Returns (client, tokens) for a freshly created platform admin."""
    import uuid

    from app.core.db import SessionLocal
    from app.core.security import hash_password
    from app.models.platform_admin import PlatformAdmin

    async with SessionLocal.begin() as session:
        session.add(
            PlatformAdmin(
                id=uuid.uuid4(),
                email="platform-admin@dok.example.com",
                password_hash=hash_password("adminpassword123"),
            )
        )

    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "platform-admin@dok.example.com", "password": "adminpassword123"},
    )
    assert resp.status_code == 200, resp.text
    tokens = resp.json()
    client.headers["Authorization"] = f"Bearer {tokens['access_token']}"
    return client, tokens
```

- [ ] **Step 4: Run the Task 4 tests — they should now all pass**

```bash
cd api && TESTING=true DATABASE_URL=postgresql+asyncpg://idms_app:devpassword@127.0.0.1:5432/idms_test PLATFORM_ADMIN_DATABASE_URL=postgresql+asyncpg://idms_platform_admin:devplatformadmin123@127.0.0.1:5432/idms_test uv run pytest tests/security/test_platform_admin_isolation.py -v
```

Expected: all 6 tests PASS.

- [ ] **Step 5: Run the full suite**

```bash
make test
```

Expected: all existing tests still PASS — in particular, `tests/integration/test_auth.py`'s existing login/refresh/logout tests, since `TokenResponse` gained a field with a default and the org-user code path is otherwise unchanged.

- [ ] **Step 6: Commit**

```bash
git add api/app/schemas/auth.py api/app/services/auth.py api/tests/conftest.py
git commit -m "feat(api): platform admin login/refresh/logout + org suspension check at login"
```

---

## Task 7: Platform admin service + schemas + router (organizations, AI toggles, suspend, per-org documents)

**Files:**

- Create: `api/app/schemas/platform_admin.py`
- Create: `api/app/services/platform_admin.py`
- Create: `api/app/api/v1/platform_admin.py`
- Modify: `api/app/main.py`
- Test: `api/tests/integration/test_platform_admin.py`

**Interfaces:**

- Consumes: `AdminSession`, `CurrentPlatformAdminDep` (Task 4), `PlatformAdminRepository` (Task 5), `Organization`/`User`/`Document`/`ApiUsage` models (existing + Task 2).
- Produces: `GET /api/v1/platform-admin/me`, `GET /api/v1/platform-admin/organizations`, `PATCH /api/v1/platform-admin/organizations/{org_id}`, `GET /api/v1/platform-admin/organizations/{org_id}/documents` — consumed by the frontend (Task 13).

- [ ] **Step 1: Write the schemas**

Create `api/app/schemas/platform_admin.py`:

```python
import uuid
from datetime import datetime

from pydantic import BaseModel


class PlatformAdminProfile(BaseModel):
    id: uuid.UUID
    email: str


class AdminOrganizationResponse(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    plan: str
    is_suspended: bool
    monthly_page_quota: int
    pages_used_this_month: int
    user_count: int
    document_count: int
    ai_tokens_total: int
    ai_cost_total_usd: float
    ai_qa_enabled: bool
    ai_summarization_enabled: bool
    ai_search_answer_enabled: bool
    ai_extraction_enabled: bool

    model_config = {"from_attributes": True}


class AdminOrgUpdateRequest(BaseModel):
    is_suspended: bool | None = None
    ai_qa_enabled: bool | None = None
    ai_summarization_enabled: bool | None = None
    ai_search_answer_enabled: bool | None = None
    ai_extraction_enabled: bool | None = None


class AdminDocumentResponse(BaseModel):
    id: uuid.UUID
    filename: str
    mime_type: str
    size_bytes: int
    status: str
    page_count: int | None
    uploaded_by_email: str
    created_at: datetime
```

- [ ] **Step 2: Write the failing integration test**

Create `api/tests/integration/test_platform_admin.py`:

```python
import uuid

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_list_organizations_sees_every_org_with_counts(
    platform_admin_client: tuple[AsyncClient, dict],  # type: ignore[type-arg]
    auth_client: tuple[AsyncClient, dict],  # type: ignore[type-arg]
    second_auth_client: tuple[AsyncClient, dict],  # type: ignore[type-arg]
) -> None:
    admin_client, _ = platform_admin_client
    client_a, _ = auth_client

    resp = await admin_client.get("/api/v1/platform-admin/organizations")
    assert resp.status_code == 200, resp.text
    orgs = resp.json()
    slugs = {o["slug"] for o in orgs}
    assert "test-org-a" in slugs
    assert "test-org-b" in slugs

    org_a = next(o for o in orgs if o["slug"] == "test-org-a")
    assert org_a["user_count"] == 1
    assert org_a["document_count"] == 0
    assert org_a["is_suspended"] is False
    assert org_a["ai_extraction_enabled"] is False
    assert org_a["ai_qa_enabled"] is True


@pytest.mark.asyncio
async def test_patch_organization_toggles_ai_feature(
    platform_admin_client: tuple[AsyncClient, dict],  # type: ignore[type-arg]
    auth_client: tuple[AsyncClient, dict],  # type: ignore[type-arg]
) -> None:
    admin_client, _ = platform_admin_client
    client_a, _ = auth_client

    me = await client_a.get("/api/v1/users/me")
    org_id = me.json()["org_id"]

    resp = await admin_client.patch(
        f"/api/v1/platform-admin/organizations/{org_id}",
        json={"ai_extraction_enabled": True},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["ai_extraction_enabled"] is True

    # Other flags are untouched by a partial update.
    assert resp.json()["ai_qa_enabled"] is True


@pytest.mark.asyncio
async def test_patch_unknown_organization_returns_404(
    platform_admin_client: tuple[AsyncClient, dict],  # type: ignore[type-arg]
) -> None:
    admin_client, _ = platform_admin_client
    resp = await admin_client.patch(
        f"/api/v1/platform-admin/organizations/{uuid.uuid4()}",
        json={"is_suspended": True},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_org_documents_endpoint_returns_metadata_only(
    platform_admin_client: tuple[AsyncClient, dict],  # type: ignore[type-arg]
    auth_client: tuple[AsyncClient, dict],  # type: ignore[type-arg]
) -> None:
    admin_client, _ = platform_admin_client
    client_a, _ = auth_client

    me = await client_a.get("/api/v1/users/me")
    org_id = me.json()["org_id"]

    resp = await admin_client.get(
        f"/api/v1/platform-admin/organizations/{org_id}/documents"
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == []  # no documents uploaded in this test


@pytest.mark.asyncio
async def test_platform_admin_me_returns_profile(
    platform_admin_client: tuple[AsyncClient, dict],  # type: ignore[type-arg]
) -> None:
    admin_client, _ = platform_admin_client
    resp = await admin_client.get("/api/v1/platform-admin/me")
    assert resp.status_code == 200, resp.text
    assert resp.json()["email"] == "platform-admin@dok.example.com"
```

- [ ] **Step 3: Run test to verify it fails**

```bash
cd api && TESTING=true DATABASE_URL=postgresql+asyncpg://idms_app:devpassword@127.0.0.1:5432/idms_test PLATFORM_ADMIN_DATABASE_URL=postgresql+asyncpg://idms_platform_admin:devplatformadmin123@127.0.0.1:5432/idms_test uv run pytest tests/integration/test_platform_admin.py -v
```

Expected: FAIL — 404 on every route (router doesn't exist yet).

- [ ] **Step 4: Write the service**

Create `api/app/services/platform_admin.py`:

```python
"""Platform-admin cross-org queries. Every function here receives a session
opened via core/deps.py:get_admin_db (the BYPASSRLS idms_platform_admin
role) — these queries deliberately span every organization."""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.api_usage import ApiUsage
from app.models.document import Document
from app.models.organization import Organization
from app.models.user import User
from app.schemas.platform_admin import (
    AdminDocumentResponse,
    AdminOrganizationResponse,
    AdminOrgUpdateRequest,
)


async def _build_org_response(
    session: AsyncSession, org: Organization
) -> AdminOrganizationResponse:
    user_count = (
        await session.execute(
            select(func.count(User.id)).where(User.org_id == org.id)
        )
    ).scalar_one()
    document_count = (
        await session.execute(
            select(func.count(Document.id)).where(Document.org_id == org.id)
        )
    ).scalar_one()
    tokens_total, cost_total = (
        await session.execute(
            select(
                func.coalesce(func.sum(ApiUsage.tokens_used), 0),
                func.coalesce(func.sum(ApiUsage.cost_usd), 0.0),
            ).where(ApiUsage.org_id == org.id)
        )
    ).one()

    return AdminOrganizationResponse(
        id=org.id,
        name=org.name,
        slug=org.slug,
        plan=org.plan,
        is_suspended=org.is_suspended,
        monthly_page_quota=org.monthly_page_quota,
        pages_used_this_month=org.pages_used_this_month,
        user_count=user_count,
        document_count=document_count,
        ai_tokens_total=int(tokens_total),
        ai_cost_total_usd=round(float(cost_total), 6),
        ai_qa_enabled=org.ai_qa_enabled,
        ai_summarization_enabled=org.ai_summarization_enabled,
        ai_search_answer_enabled=org.ai_search_answer_enabled,
        ai_extraction_enabled=org.ai_extraction_enabled,
    )


async def list_organizations(session: AsyncSession) -> list[AdminOrganizationResponse]:
    result = await session.execute(
        select(Organization).order_by(Organization.created_at)
    )
    orgs = result.scalars().all()
    return [await _build_org_response(session, org) for org in orgs]


async def update_organization(
    session: AsyncSession, org_id: uuid.UUID, body: AdminOrgUpdateRequest
) -> AdminOrganizationResponse:
    result = await session.execute(
        select(Organization).where(Organization.id == org_id)
    )
    org = result.scalar_one_or_none()
    if not org:
        raise ValueError("Organization not found")

    if body.is_suspended is not None:
        org.is_suspended = body.is_suspended
    if body.ai_qa_enabled is not None:
        org.ai_qa_enabled = body.ai_qa_enabled
    if body.ai_summarization_enabled is not None:
        org.ai_summarization_enabled = body.ai_summarization_enabled
    if body.ai_search_answer_enabled is not None:
        org.ai_search_answer_enabled = body.ai_search_answer_enabled
    if body.ai_extraction_enabled is not None:
        org.ai_extraction_enabled = body.ai_extraction_enabled

    await session.flush()
    return await _build_org_response(session, org)


async def list_org_documents(
    session: AsyncSession, org_id: uuid.UUID
) -> list[AdminDocumentResponse]:
    result = await session.execute(
        select(Document, User.email)
        .join(User, User.id == Document.uploaded_by)
        .where(Document.org_id == org_id)
        .order_by(Document.created_at.desc())
    )
    return [
        AdminDocumentResponse(
            id=doc.id,
            filename=doc.filename,
            mime_type=doc.mime_type,
            size_bytes=doc.size_bytes,
            status=doc.status,
            page_count=doc.page_count,
            uploaded_by_email=email,
            created_at=doc.created_at,
        )
        for doc, email in result.all()
    ]
```

- [ ] **Step 5: Write the router**

Create `api/app/api/v1/platform_admin.py`:

```python
import uuid

from fastapi import APIRouter, HTTPException, status

from app.core.deps import AdminSession, CurrentPlatformAdminDep
from app.repositories.platform_admin import PlatformAdminRepository
from app.schemas.platform_admin import (
    AdminDocumentResponse,
    AdminOrganizationResponse,
    AdminOrgUpdateRequest,
    PlatformAdminProfile,
)
from app.services import platform_admin as admin_service

router = APIRouter(prefix="/platform-admin", tags=["platform-admin"])


@router.get("/me", response_model=PlatformAdminProfile)
async def get_me(
    admin: CurrentPlatformAdminDep, session: AdminSession
) -> PlatformAdminProfile:
    record = await PlatformAdminRepository(session).get_by_id(admin.admin_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Admin not found"
        )
    return PlatformAdminProfile(id=record.id, email=record.email)


@router.get("/organizations", response_model=list[AdminOrganizationResponse])
async def list_organizations(
    admin: CurrentPlatformAdminDep, session: AdminSession
) -> list[AdminOrganizationResponse]:
    return await admin_service.list_organizations(session)


@router.patch("/organizations/{org_id}", response_model=AdminOrganizationResponse)
async def update_organization(
    org_id: uuid.UUID,
    body: AdminOrgUpdateRequest,
    admin: CurrentPlatformAdminDep,
    session: AdminSession,
) -> AdminOrganizationResponse:
    try:
        return await admin_service.update_organization(session, org_id, body)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e


@router.get(
    "/organizations/{org_id}/documents", response_model=list[AdminDocumentResponse]
)
async def list_org_documents(
    org_id: uuid.UUID,
    admin: CurrentPlatformAdminDep,
    session: AdminSession,
) -> list[AdminDocumentResponse]:
    return await admin_service.list_org_documents(session, org_id)
```

- [ ] **Step 6: Wire the router into `main.py`**

In `api/app/main.py`, add the import:

```python
from app.api.v1.platform_admin import router as platform_admin_router
```

And register it alongside the others:

```python
    app.include_router(platform_admin_router, prefix="/api/v1")
```

- [ ] **Step 7: Run tests to verify they pass**

```bash
cd api && TESTING=true DATABASE_URL=postgresql+asyncpg://idms_app:devpassword@127.0.0.1:5432/idms_test PLATFORM_ADMIN_DATABASE_URL=postgresql+asyncpg://idms_platform_admin:devplatformadmin123@127.0.0.1:5432/idms_test uv run pytest tests/integration/test_platform_admin.py -v
```

Expected: all 5 tests PASS.

- [ ] **Step 8: Run the full suite**

```bash
make test
```

Expected: all tests PASS.

- [ ] **Step 9: Commit**

```bash
git add api/app/schemas/platform_admin.py api/app/services/platform_admin.py api/app/api/v1/platform_admin.py api/app/main.py api/tests/integration/test_platform_admin.py
git commit -m "feat(api): platform admin organizations/documents endpoints"
```

---

## Task 8: AI feature toggle enforcement (Q&A, summarization, search answer, extraction)

**Files:**

- Modify: `api/app/services/ai.py`
- Modify: `api/app/services/search.py`
- Modify: `api/app/services/extraction.py`
- Modify: `api/app/api/v1/templates.py`
- Test: `api/tests/integration/test_ai_toggles.py`

**Interfaces:**

- Consumes: `Organization.ai_qa_enabled` / `ai_summarization_enabled` / `ai_search_answer_enabled` / `ai_extraction_enabled` (Task 2), the `PATCH /platform-admin/organizations/{id}` endpoint (Task 7) used by the test to flip flags.
- Produces: `AIFeatureDisabledError` (new, in `extraction.py`) — consumed by `templates.py`'s router.

- [ ] **Step 1: Write the failing tests**

Create `api/tests/integration/test_ai_toggles.py`:

```python
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient


async def _disable(
    admin_client: AsyncClient, org_id: str, **flags: bool
) -> None:
    resp = await admin_client.patch(
        f"/api/v1/platform-admin/organizations/{org_id}", json=flags
    )
    assert resp.status_code == 200, resp.text


@pytest.mark.asyncio
async def test_qa_disabled_short_circuits_without_calling_llm(
    platform_admin_client: tuple[AsyncClient, dict],  # type: ignore[type-arg]
    auth_client: tuple[AsyncClient, dict],  # type: ignore[type-arg]
) -> None:
    """The org's real GROQ_API_KEY is configured in api/.env, so this must
    mock _call_llm directly (the top-level dispatcher, provider-agnostic) —
    otherwise this test would make a real network call, same trap that
    tests/integration/test_ai.py works around by mocking the LLM call."""
    admin_client, _ = platform_admin_client
    client_a, _ = auth_client

    me = await client_a.get("/api/v1/users/me")
    org_id = me.json()["org_id"]
    await _disable(admin_client, org_id, ai_qa_enabled=False)

    with patch(
        "app.services.ai._call_llm", new_callable=AsyncMock
    ) as mock_call_llm:
        resp = await client_a.post(
            "/api/v1/ai/chat", json={"question": "What is in my documents?"}
        )

    assert resp.status_code == 200
    assert "disabled" in resp.json()["answer"].lower()
    mock_call_llm.assert_not_called()


@pytest.mark.asyncio
async def test_extraction_disabled_by_default_returns_403(
    auth_client: tuple[AsyncClient, dict],  # type: ignore[type-arg]
) -> None:
    """ai_extraction_enabled defaults to False for every new org."""
    client_a, _ = auth_client

    tmpl = await client_a.post(
        "/api/v1/templates",
        json={
            "name": "Invoice",
            "fields": [{"key": "total", "label": "Total", "type": "text"}],
        },
    )
    assert tmpl.status_code == 201, tmpl.text

    import uuid

    resp = await client_a.post(
        "/api/v1/templates/extract",
        json={
            "document_id": str(uuid.uuid4()),
            "template_id": tmpl.json()["id"],
        },
    )
    assert resp.status_code == 403
    assert "disabled" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_extraction_enabled_reaches_not_found_instead_of_disabled(
    platform_admin_client: tuple[AsyncClient, dict],  # type: ignore[type-arg]
    auth_client: tuple[AsyncClient, dict],  # type: ignore[type-arg]
) -> None:
    """Once enabled, a bad document_id now fails for the ORIGINAL reason
    (not found) rather than being blocked by the toggle — proves the toggle
    check runs, and runs before the not-found check would otherwise hide it."""
    admin_client, _ = platform_admin_client
    client_a, _ = auth_client

    me = await client_a.get("/api/v1/users/me")
    org_id = me.json()["org_id"]
    await _disable(admin_client, org_id, ai_extraction_enabled=True)

    tmpl = await client_a.post(
        "/api/v1/templates",
        json={
            "name": "Invoice",
            "fields": [{"key": "total", "label": "Total", "type": "text"}],
        },
    )

    import uuid

    resp = await client_a.post(
        "/api/v1/templates/extract",
        json={
            "document_id": str(uuid.uuid4()),
            "template_id": tmpl.json()["id"],
        },
    )
    assert resp.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd api && TESTING=true DATABASE_URL=postgresql+asyncpg://idms_app:devpassword@127.0.0.1:5432/idms_test PLATFORM_ADMIN_DATABASE_URL=postgresql+asyncpg://idms_platform_admin:devplatformadmin123@127.0.0.1:5432/idms_test uv run pytest tests/integration/test_ai_toggles.py -v
```

Expected: FAIL — `test_qa_disabled_...` fails because the flag isn't checked yet (real LLM call attempted/mocked answer returned without the disabled text); `test_extraction_disabled_by_default_returns_403` fails with 404 instead of 403 (no toggle check yet); `test_extraction_enabled_...` fails because there's no toggle-off default blocking it in the first place so behavior may already coincidentally look like 404 — run it anyway to confirm the suite exercises the new code path once added.

- [ ] **Step 3: Add the toggle check to `services/ai.py`**

In `api/app/services/ai.py`, add the import:

```python
from app.models.organization import Organization
```

Add a helper after the imports:

```python
async def _get_org(session: AsyncSession, org_id: uuid.UUID) -> Organization | None:
    result = await session.execute(
        select(Organization).where(Organization.id == org_id)
    )
    return result.scalar_one_or_none()
```

At the top of `ask_document` (right after the docstring):

```python
    org = await _get_org(session, org_id)
    if org and not org.ai_qa_enabled:
        return {"answer": "AI Q&A is disabled for your organization.", "sources": []}
```

At the top of `ask_org` (right after the docstring):

```python
    org = await _get_org(session, org_id)
    if org and not org.ai_qa_enabled:
        return {"answer": "AI Q&A is disabled for your organization.", "sources": []}
```

At the top of `summarize_document` (right after the docstring):

```python
    org = await _get_org(session, org_id)
    if org and not org.ai_summarization_enabled:
        return "AI summarization is disabled for your organization."
```

- [ ] **Step 4: Add the toggle check to `services/search.py`**

In `api/app/services/search.py`, add the import:

```python
from app.models.organization import Organization
```

Change the `ai_summary` block at the end of `hybrid_search`:

```python
    ai_summary = None
    if hits:
        org_result = await session.execute(
            select(Organization).where(Organization.id == org_id)
        )
        org = org_result.scalar_one_or_none()
        if org and org.ai_search_answer_enabled:
            try:
                from app.services.ai import _call_llm

                context = "\n\n".join(
                    f"[p.{h.page}, {h.filename}]\n{h.content[:300]}" for h in hits[:5]
                )
                ai_summary = await _call_llm(
                    "Based on the search results below, write a brief answer to the "
                    f'user\'s query: "{query}"\n\n'
                    "Be concise (2-4 sentences). Cite page numbers.\n\n"
                    f"{context}"
                )
            except Exception:
                logger.warning("AI summary generation failed")
```

- [ ] **Step 5: Add the toggle check to `services/extraction.py`**

In `api/app/services/extraction.py`, add the import:

```python
from app.models.organization import Organization
```

Add the exception class after the imports:

```python
class AIFeatureDisabledError(Exception):
    """Raised when a tenant has this AI capability turned off."""
```

In `extract_fields`, add the toggle check as the very **first** thing in the
function body — before the document/template lookups. This matters: if the
check ran after the document lookup (which raises `ValueError("Document not
found...")` on a missing document), a disabled-extraction org would get a
misleading 404 instead of a 403 whenever the document/template also happens
not to exist, and the check would never fire for that request at all. Checking
first also means a customer on a plan without extraction never expends a
document/template lookup to find that out.

```python
async def extract_fields(
    session: AsyncSession,
    org_id: uuid.UUID,
    document_id: uuid.UUID,
    template_id: uuid.UUID,
) -> Extraction:
    org_result = await session.execute(
        select(Organization).where(Organization.id == org_id)
    )
    org = org_result.scalar_one_or_none()
    if org and not org.ai_extraction_enabled:
        raise AIFeatureDisabledError(
            "AI extraction is disabled for your organization"
        )

    doc_result = await session.execute(
        select(Document).where(Document.id == document_id, Document.org_id == org_id)
    )
```

(Everything from `doc = doc_result.scalar_one_or_none()` onward in the
existing function body is unchanged.)

- [ ] **Step 6: Map the new exception to 403 in `templates.py`**

In `api/app/api/v1/templates.py`, add the import:

```python
from app.services.extraction import AIFeatureDisabledError, extract_fields
```

Change `run_extraction`:

```python
@router.post("/extract", response_model=ExtractionResponse)
async def run_extraction(
    body: ExtractRequest,
    current_user: CurrentUserDep,
    session: AuthSession,
) -> ExtractionResponse:
    try:
        extraction = await extract_fields(
            session, current_user.org_id, body.document_id, body.template_id
        )
    except AIFeatureDisabledError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    return ExtractionResponse.model_validate(extraction)
```

- [ ] **Step 7: Run tests to verify they pass**

```bash
cd api && TESTING=true DATABASE_URL=postgresql+asyncpg://idms_app:devpassword@127.0.0.1:5432/idms_test PLATFORM_ADMIN_DATABASE_URL=postgresql+asyncpg://idms_platform_admin:devplatformadmin123@127.0.0.1:5432/idms_test uv run pytest tests/integration/test_ai_toggles.py -v
```

Expected: all 3 tests PASS.

- [ ] **Step 8: Run the full suite**

```bash
make test
```

Expected: all tests PASS, including the pre-existing `tests/integration/test_ai.py` (unaffected — new orgs default every toggle except extraction to `true`, so untouched behavior is unchanged).

- [ ] **Step 9: Commit**

```bash
git add api/app/services/ai.py api/app/services/search.py api/app/services/extraction.py api/app/api/v1/templates.py api/tests/integration/test_ai_toggles.py
git commit -m "feat(api): enforce per-org AI feature toggles (qa, summarization, search answer, extraction)"
```

---

## Task 9: Bootstrap script — `create_platform_admin`

**Files:**

- Create: `api/app/scripts/__init__.py`
- Create: `api/app/scripts/create_platform_admin.py`
- Test: `api/tests/unit/test_create_platform_admin_script.py`

**Interfaces:**

- Consumes: `PlatformAdminRepository` (Task 5), `hash_password` (existing).
- Produces: a runnable module `python -m app.scripts.create_platform_admin --email <email>` — this is how the very first (and every subsequent) platform admin account gets created; never exposed via the API.

- [ ] **Step 1: Write the failing test**

Create `api/tests/unit/test_create_platform_admin_script.py`:

```python
import pytest

from app.core.db import SessionLocal
from app.repositories.platform_admin import PlatformAdminRepository
from app.scripts.create_platform_admin import _create


@pytest.mark.asyncio
async def test_create_inserts_a_platform_admin() -> None:
    await _create("script-test@example.com", "password1234")

    async with SessionLocal() as session:
        found = await PlatformAdminRepository(session).get_by_email(
            "script-test@example.com"
        )
        assert found is not None
        assert found.is_active is True


@pytest.mark.asyncio
async def test_create_refuses_duplicate_email() -> None:
    await _create("dup-test@example.com", "password1234")
    with pytest.raises(SystemExit):
        await _create("dup-test@example.com", "password1234")
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd api && TESTING=true DATABASE_URL=postgresql+asyncpg://idms_app:devpassword@127.0.0.1:5432/idms_test uv run pytest tests/unit/test_create_platform_admin_script.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'app.scripts'`.

- [ ] **Step 3: Implement**

Create `api/app/scripts/__init__.py` (empty file).

Create `api/app/scripts/create_platform_admin.py`:

```python
"""One-off CLI to create a platform admin account. Never exposed via any API
route — run manually per environment.

Usage:
    uv run python -m app.scripts.create_platform_admin --email you@example.com
"""

import argparse
import asyncio
import getpass
import uuid

from app.core.db import SessionLocal
from app.core.security import hash_password
from app.models.platform_admin import PlatformAdmin
from app.repositories.platform_admin import PlatformAdminRepository


async def _create(email: str, password: str) -> None:
    async with SessionLocal.begin() as session:
        repo = PlatformAdminRepository(session)
        existing = await repo.get_by_email(email)
        if existing:
            raise SystemExit(f"A platform admin with email {email!r} already exists.")
        session.add(
            PlatformAdmin(
                id=uuid.uuid4(), email=email, password_hash=hash_password(password)
            )
        )
    print(f"Platform admin created: {email}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a platform admin account")
    parser.add_argument("--email", required=True)
    args = parser.parse_args()

    password = getpass.getpass("Password (min 10 characters): ")
    if len(password) < 10:
        raise SystemExit("Password must be at least 10 characters")
    confirm = getpass.getpass("Confirm password: ")
    if password != confirm:
        raise SystemExit("Passwords do not match")

    asyncio.run(_create(args.email, password))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd api && TESTING=true DATABASE_URL=postgresql+asyncpg://idms_app:devpassword@127.0.0.1:5432/idms_test uv run pytest tests/unit/test_create_platform_admin_script.py -v
```

Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add api/app/scripts/__init__.py api/app/scripts/create_platform_admin.py api/tests/unit/test_create_platform_admin_script.py
git commit -m "feat(api): bootstrap script to create a platform admin account"
```

---

## Task 10: Frontend — `account_type`-aware login + admin API client

**Files:**

- Modify: `web/lib/auth.ts`
- Modify: `web/app/(auth)/login/page.tsx`
- Create: `web/lib/admin.ts`

**Interfaces:**

- Consumes: `TokenResponse.account_type` (Task 6), `GET/PATCH /api/v1/platform-admin/*` (Task 7).
- Produces: `authApi.login()` resolves with `account_type`; `adminApi.{getOrganizations, updateOrganization, getOrgDocuments, getMe}` — consumed by Task 11's `/admin` page.

- [ ] **Step 1: Extend `TokenResponse` and the login redirect**

In `web/lib/auth.ts`, update the interface:

```typescript
export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  account_type: "org_user" | "platform_admin";
}
```

In `web/app/(auth)/login/page.tsx`, change `handleSubmit`:

```typescript
async function handleSubmit(e: React.FormEvent) {
  e.preventDefault();
  setLoading(true);
  setError("");
  try {
    const tokens = await authApi.login(email, password);
    saveTokens(tokens);
    window.location.href =
      tokens.account_type === "platform_admin" ? "/admin" : "/dashboard";
  } catch (err) {
    setError(err instanceof Error ? err.message : "Login failed");
  } finally {
    setLoading(false);
  }
}
```

- [ ] **Step 2: Write the admin API client**

Create `web/lib/admin.ts`:

```typescript
import { getAccessToken } from "@/lib/auth";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface AdminOrganization {
  id: string;
  name: string;
  slug: string;
  plan: string;
  is_suspended: boolean;
  monthly_page_quota: number;
  pages_used_this_month: number;
  user_count: number;
  document_count: number;
  ai_tokens_total: number;
  ai_cost_total_usd: number;
  ai_qa_enabled: boolean;
  ai_summarization_enabled: boolean;
  ai_search_answer_enabled: boolean;
  ai_extraction_enabled: boolean;
}

export interface AdminOrgUpdate {
  is_suspended?: boolean;
  ai_qa_enabled?: boolean;
  ai_summarization_enabled?: boolean;
  ai_search_answer_enabled?: boolean;
  ai_extraction_enabled?: boolean;
}

export interface AdminDocument {
  id: string;
  filename: string;
  mime_type: string;
  size_bytes: number;
  status: string;
  page_count: number | null;
  uploaded_by_email: string;
  created_at: string;
}

export interface AdminProfile {
  id: string;
  email: string;
}

function authHeaders(): HeadersInit {
  return { Authorization: `Bearer ${getAccessToken()}` };
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${API}${path}`, { headers: authHeaders() });
  if (!res.ok) throw new Error(await res.text());
  return res.json() as Promise<T>;
}

export const adminApi = {
  getMe: () => get<AdminProfile>("/api/v1/platform-admin/me"),
  getOrganizations: () =>
    get<AdminOrganization[]>("/api/v1/platform-admin/organizations"),
  getOrgDocuments: (orgId: string) =>
    get<AdminDocument[]>(
      `/api/v1/platform-admin/organizations/${orgId}/documents`,
    ),
  updateOrganization: async (
    orgId: string,
    body: AdminOrgUpdate,
  ): Promise<AdminOrganization> => {
    const res = await fetch(
      `${API}/api/v1/platform-admin/organizations/${orgId}`,
      {
        method: "PATCH",
        headers: { ...authHeaders(), "Content-Type": "application/json" },
        body: JSON.stringify(body),
      },
    );
    if (!res.ok) throw new Error(await res.text());
    return res.json() as Promise<AdminOrganization>;
  },
};
```

- [ ] **Step 3: Type-check**

```bash
cd web && npm run build
```

Expected: build succeeds (no type errors) — the `/admin` page doesn't exist yet, so nothing consumes `admin.ts` yet, but it must compile standalone.

- [ ] **Step 4: Commit**

```bash
git add web/lib/auth.ts web/app/\(auth\)/login/page.tsx web/lib/admin.ts
git commit -m "feat(web): account_type-aware login redirect and admin API client"
```

---

## Task 11: Frontend — `/admin` organizations dashboard

**Files:**

- Create: `web/app/admin/page.tsx`

**Interfaces:**

- Consumes: `adminApi` (Task 10).
- Produces: the platform admin's landing page after login.

- [ ] **Step 1: Write the page**

Create `web/app/admin/page.tsx`:

```tsx
"use client";

import { useCallback, useEffect, useState } from "react";
import {
  getAccessToken,
  getRefreshToken,
  authApi,
  clearTokens,
} from "@/lib/auth";
import {
  adminApi,
  type AdminDocument,
  type AdminOrganization,
  type AdminOrgUpdate,
} from "@/lib/admin";

const TOGGLE_FIELDS: { key: keyof AdminOrgUpdate; label: string }[] = [
  { key: "ai_qa_enabled", label: "Q&A / Chat" },
  { key: "ai_summarization_enabled", label: "Summarization" },
  { key: "ai_search_answer_enabled", label: "Search AI Answer" },
  { key: "ai_extraction_enabled", label: "Extraction" },
];

export default function AdminPage() {
  const [orgs, setOrgs] = useState<AdminOrganization[] | null>(null);
  const [expandedOrgId, setExpandedOrgId] = useState<string | null>(null);
  const [docs, setDocs] = useState<AdminDocument[]>([]);
  const [error, setError] = useState("");

  const loadOrgs = useCallback(() => {
    adminApi
      .getOrganizations()
      .then(setOrgs)
      .catch(() => {
        window.location.href = "/login";
      });
  }, []);

  useEffect(() => {
    if (!getAccessToken()) {
      window.location.href = "/login";
      return;
    }
    adminApi.getMe().catch(() => {
      window.location.href = "/login";
    });
    loadOrgs();
  }, [loadOrgs]);

  async function handleToggle(
    org: AdminOrganization,
    field: keyof AdminOrgUpdate,
  ) {
    setError("");
    try {
      const updated = await adminApi.updateOrganization(org.id, {
        [field]: !org[field],
      } as AdminOrgUpdate);
      setOrgs((prev) =>
        (prev ?? []).map((o) => (o.id === updated.id ? updated : o)),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Update failed");
    }
  }

  async function handleSuspendToggle(org: AdminOrganization) {
    await handleToggle(org, "is_suspended");
  }

  async function toggleDocuments(orgId: string) {
    if (expandedOrgId === orgId) {
      setExpandedOrgId(null);
      setDocs([]);
      return;
    }
    setExpandedOrgId(orgId);
    try {
      setDocs(await adminApi.getOrgDocuments(orgId));
    } catch {
      setDocs([]);
    }
  }

  async function handleLogout() {
    const refresh = getRefreshToken();
    if (refresh) {
      try {
        await authApi.logout(refresh);
      } catch {
        /* ok */
      }
    }
    clearTokens();
    window.location.href = "/login";
  }

  if (!orgs) {
    return (
      <div
        style={{
          minHeight: "100vh",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        <div
          style={{
            width: 32,
            height: 32,
            border: "3px solid var(--brand-200)",
            borderTopColor: "var(--brand-500)",
            borderRadius: "50%",
            animation: "spin 0.6s linear infinite",
          }}
        />
      </div>
    );
  }

  return (
    <div style={{ maxWidth: 1200, margin: "0 auto", padding: "2rem 1.5rem" }}>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: "1.5rem",
        }}
      >
        <h1
          style={{
            fontSize: "1.4rem",
            fontWeight: 700,
            color: "var(--gray-900)",
          }}
        >
          Platform Admin — Organizations
        </h1>
        <button onClick={handleLogout} className="btn-secondary">
          Log out
        </button>
      </div>

      {error && (
        <div
          style={{
            padding: "0.6rem 0.85rem",
            background: "var(--red-50)",
            color: "var(--red-700)",
            borderRadius: "var(--radius-sm)",
            fontSize: "0.85rem",
            marginBottom: "1rem",
          }}
        >
          {error}
        </div>
      )}

      <div className="card" style={{ overflowX: "auto" }}>
        <table
          style={{
            width: "100%",
            borderCollapse: "collapse",
            fontSize: "0.85rem",
          }}
        >
          <thead>
            <tr style={{ borderBottom: "1px solid var(--gray-100)" }}>
              <th style={{ textAlign: "left", padding: "0.6rem" }}>
                Organization
              </th>
              <th style={{ textAlign: "left", padding: "0.6rem" }}>Plan</th>
              <th style={{ textAlign: "right", padding: "0.6rem" }}>Users</th>
              <th style={{ textAlign: "right", padding: "0.6rem" }}>Docs</th>
              <th style={{ textAlign: "right", padding: "0.6rem" }}>
                AI Tokens
              </th>
              <th style={{ textAlign: "right", padding: "0.6rem" }}>AI Cost</th>
              <th style={{ textAlign: "right", padding: "0.6rem" }}>
                Quota (used/total)
              </th>
              {TOGGLE_FIELDS.map((f) => (
                <th
                  key={f.key}
                  style={{ textAlign: "center", padding: "0.6rem" }}
                >
                  {f.label}
                </th>
              ))}
              <th style={{ textAlign: "center", padding: "0.6rem" }}>
                Suspended
              </th>
              <th style={{ textAlign: "center", padding: "0.6rem" }}>
                Documents
              </th>
            </tr>
          </thead>
          <tbody>
            {orgs.map((org) => (
              <>
                <tr
                  key={org.id}
                  style={{ borderBottom: "1px solid var(--gray-100)" }}
                >
                  <td style={{ padding: "0.6rem", fontWeight: 500 }}>
                    {org.name}
                  </td>
                  <td style={{ padding: "0.6rem", color: "var(--gray-600)" }}>
                    {org.plan}
                  </td>
                  <td style={{ padding: "0.6rem", textAlign: "right" }}>
                    {org.user_count}
                  </td>
                  <td style={{ padding: "0.6rem", textAlign: "right" }}>
                    {org.document_count}
                  </td>
                  <td style={{ padding: "0.6rem", textAlign: "right" }}>
                    {org.ai_tokens_total.toLocaleString()}
                  </td>
                  <td style={{ padding: "0.6rem", textAlign: "right" }}>
                    ${org.ai_cost_total_usd.toFixed(4)}
                  </td>
                  <td style={{ padding: "0.6rem", textAlign: "right" }}>
                    {org.pages_used_this_month}/{org.monthly_page_quota}
                  </td>
                  {TOGGLE_FIELDS.map((f) => (
                    <td
                      key={f.key}
                      style={{ padding: "0.6rem", textAlign: "center" }}
                    >
                      <input
                        type="checkbox"
                        checked={Boolean(org[f.key])}
                        onChange={() => handleToggle(org, f.key)}
                      />
                    </td>
                  ))}
                  <td style={{ padding: "0.6rem", textAlign: "center" }}>
                    <input
                      type="checkbox"
                      checked={org.is_suspended}
                      onChange={() => handleSuspendToggle(org)}
                    />
                  </td>
                  <td style={{ padding: "0.6rem", textAlign: "center" }}>
                    <button
                      onClick={() => toggleDocuments(org.id)}
                      className="btn-secondary"
                      style={{ fontSize: "0.75rem", padding: "0.3rem 0.6rem" }}
                    >
                      {expandedOrgId === org.id ? "Hide" : "View"}
                    </button>
                  </td>
                </tr>
                {expandedOrgId === org.id && (
                  <tr key={`${org.id}-docs`}>
                    <td
                      colSpan={9 + TOGGLE_FIELDS.length}
                      style={{
                        padding: "0.75rem 1.5rem",
                        background: "var(--gray-50)",
                      }}
                    >
                      {docs.length === 0 ? (
                        <span style={{ color: "var(--gray-500)" }}>
                          No documents.
                        </span>
                      ) : (
                        <table style={{ width: "100%", fontSize: "0.8rem" }}>
                          <thead>
                            <tr>
                              <th
                                style={{ textAlign: "left", padding: "0.3rem" }}
                              >
                                Filename
                              </th>
                              <th
                                style={{ textAlign: "left", padding: "0.3rem" }}
                              >
                                Status
                              </th>
                              <th
                                style={{
                                  textAlign: "right",
                                  padding: "0.3rem",
                                }}
                              >
                                Pages
                              </th>
                              <th
                                style={{ textAlign: "left", padding: "0.3rem" }}
                              >
                                Uploaded By
                              </th>
                              <th
                                style={{ textAlign: "left", padding: "0.3rem" }}
                              >
                                Created
                              </th>
                            </tr>
                          </thead>
                          <tbody>
                            {docs.map((d) => (
                              <tr key={d.id}>
                                <td style={{ padding: "0.3rem" }}>
                                  {d.filename}
                                </td>
                                <td style={{ padding: "0.3rem" }}>
                                  {d.status}
                                </td>
                                <td
                                  style={{
                                    padding: "0.3rem",
                                    textAlign: "right",
                                  }}
                                >
                                  {d.page_count ?? "—"}
                                </td>
                                <td style={{ padding: "0.3rem" }}>
                                  {d.uploaded_by_email}
                                </td>
                                <td style={{ padding: "0.3rem" }}>
                                  {new Date(d.created_at).toLocaleString()}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      )}
                    </td>
                  </tr>
                )}
              </>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Type-check and build**

```bash
cd web && npm run build
```

Expected: build succeeds.

- [ ] **Step 3: Commit**

```bash
git add web/app/admin/page.tsx
git commit -m "feat(web): platform admin organizations dashboard"
```

---

## Task 12: End-to-end verification

**Files:** none (verification only).

- [ ] **Step 1: Rebuild and restart the stack**

```bash
docker compose -f infra/docker-compose.yml build api worker web
docker compose -f infra/docker-compose.yml up -d
```

- [ ] **Step 2: Bootstrap a real platform admin against the running dev database**

```bash
cd api && uv run python -m app.scripts.create_platform_admin --email admin@dok.solutions
```

(Enter a password at the prompts.)

- [ ] **Step 3: Manual smoke test**

1. Open the web app, log in with the bootstrapped platform admin's credentials.
2. Confirm redirect to `/admin` (not `/dashboard`).
3. Confirm both existing orgs (`abc`, `dok`) appear with correct user counts.
4. Flip the "Extraction" toggle on for one org; confirm the checkbox reflects the new state after the PATCH resolves.
5. Click "View" on an org with documents; confirm the metadata table shows filename/status/pages/uploader/date and nothing else.
6. Toggle "Suspended" on for one org; log in as a user of that org in a separate browser/incognito window and confirm login is rejected with the suspension message.
7. Un-suspend the org; confirm that org's user can log in again.

- [ ] **Step 4: Run the full backend and frontend checks one more time**

```bash
cd api && make test
cd web && npm run build
```

Expected: both PASS.

- [ ] **Step 5: Final commit (if any manual fixups were needed during verification)**

```bash
git add -A
git commit -m "chore: platform super admin end-to-end verification fixups"
```

(Skip this step if no fixups were needed.)
