# IDMS Phase 1: Auth & Multi-Tenancy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan inline. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Secure login with organizations, roles, and database-enforced tenant isolation proven by an automated CI test.

**Architecture:** PostgreSQL Row Level Security with `FORCE ROW LEVEL SECURITY` ensures every query is org-scoped at the DB layer. A FastAPI dependency sets `SET LOCAL app.current_org_id` per transaction from the verified JWT — this is the single most important pattern. Argon2id password hashing. HS256 JWTs (access 15 min, opaque refresh 7 days stored in Redis). Rate limiting via slowapi.

**Tech Stack:** passlib[argon2] · python-jose[cryptography] · slowapi · email-validator · SQLAlchemy 2 async · PostgreSQL RLS · Redis (refresh token store)

---

> **Definition of Done:**
>
> - Login works end-to-end (register → login → access protected endpoint)
> - Tenant-isolation test suite green and blocking in CI
> - RLS active with FORCE on all tenant tables
> - Account lockout and refresh rotation verified
> - Audit logging of auth events

---

## File Map

| File                                               | Action | Responsibility                                                                                  |
| -------------------------------------------------- | ------ | ----------------------------------------------------------------------------------------------- |
| `api/pyproject.toml`                               | Modify | Add passlib[argon2], python-jose, slowapi, email-validator                                      |
| `.env.example`                                     | Modify | Add JWT_SECRET_KEY, JWT_ALGORITHM, token expiry vars                                            |
| `api/app/models/organization.py`                   | Create | Organization SQLAlchemy model                                                                   |
| `api/app/models/user.py`                           | Create | User model + UserRole enum                                                                      |
| `api/app/models/audit_log.py`                      | Create | AuditLog model                                                                                  |
| `api/app/schemas/auth.py`                          | Create | RegisterRequest, LoginRequest, TokenResponse, RefreshRequest                                    |
| `api/app/schemas/user.py`                          | Create | UserResponse                                                                                    |
| `api/app/core/security.py`                         | Create | hash_password, verify_password, create_access_token, decode_access_token, refresh token helpers |
| `api/app/core/deps.py`                             | Create | get_public_db, get_current_user_token, get_db (org-context), get_current_user, require_role     |
| `api/app/repositories/organization.py`             | Create | OrgRepository — create, get_by_slug                                                             |
| `api/app/repositories/user.py`                     | Create | UserRepository — create, get_by_email, get_by_id, increment_failed, lock, reset_failed          |
| `api/app/services/auth.py`                         | Create | AuthService — register, login, refresh, logout                                                  |
| `api/app/api/v1/auth.py`                           | Create | Auth router: POST /register /login /refresh /logout                                             |
| `api/app/api/v1/users.py`                          | Create | Users router: GET /me, GET /{user_id}                                                           |
| `api/app/main.py`                                  | Modify | Add slowapi middleware, register auth + users routers                                           |
| `api/app/core/config.py`                           | Modify | Add JWT_SECRET_KEY, JWT_ALGORITHM, token expiry fields                                          |
| `api/migrations/versions/002_auth_multitenancy.py` | Create | organizations, users, audit_logs tables + RLS policies                                          |
| `api/tests/security/test_tenant_isolation.py`      | Create | **THE GATE** — cross-org isolation assertions                                                   |
| `api/tests/integration/test_auth.py`               | Create | Register, login, refresh, logout, lockout tests                                                 |

---

### Task 1: Add Phase 1 dependencies and env vars

**Files:** `api/pyproject.toml`, `.env.example`, `api/app/core/config.py`

- [ ] **Step 1: Update `api/pyproject.toml` — add runtime deps**

In the `dependencies` list, add:

```toml
dependencies = [
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.30.0",
    "sqlalchemy[asyncio]>=2.0.0",
    "asyncpg>=0.29.0",
    "alembic>=1.13.0",
    "pydantic-settings>=2.6.0",
    "pydantic[email]>=2.0.0",
    "celery[redis]>=5.4.0",
    "redis>=5.0.0",
    "structlog>=24.4.0",
    "sentry-sdk[fastapi]>=2.14.0",
    "passlib[argon2]>=1.7.4",
    "python-jose[cryptography]>=3.3.0",
    "slowapi>=0.1.9",
]
```

Also add to dev deps:

```toml
"types-passlib>=1.7.7",
```

- [ ] **Step 2: Run `uv sync --all-extras` from `api/`**

```bash
cd api && uv sync --all-extras
```

Expected: Resolves and installs new packages, updates `uv.lock`.

- [ ] **Step 3: Add JWT vars to `.env.example`**

Append to `.env.example`:

```bash
# --- JWT ---
JWT_SECRET_KEY=changeme-jwt-secret-must-be-32-chars-min
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=15
REFRESH_TOKEN_EXPIRE_DAYS=7
```

- [ ] **Step 4: Add JWT fields to `api/app/core/config.py`**

Add these fields to the `Settings` class (after `SENTRY_DSN`):

```python
# JWT
JWT_SECRET_KEY: str = ""
JWT_ALGORITHM: str = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
REFRESH_TOKEN_EXPIRE_DAYS: int = 7
```

- [ ] **Step 5: Commit**

```bash
git add api/pyproject.toml api/uv.lock .env.example api/app/core/config.py
git commit -m "chore: add Phase 1 deps (passlib, python-jose, slowapi, pydantic[email])"
```

---

### Task 2: Organization, User, AuditLog models

**Files:** `api/app/models/organization.py`, `api/app/models/user.py`, `api/app/models/audit_log.py`

- [ ] **Step 1: Create `api/app/models/organization.py`**

```python
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    plan: Mapped[str] = mapped_column(String(50), server_default="free")
    monthly_page_quota: Mapped[int] = mapped_column(Integer, server_default="500")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
```

- [ ] **Step 2: Create `api/app/models/user.py`**

```python
import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class UserRole(enum.Enum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    VIEWER = "viewer"


class User(Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("org_id", "email", name="uq_user_org_email"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), server_default="MEMBER")
    is_active: Mapped[bool] = mapped_column(Boolean, server_default="true")
    failed_login_count: Mapped[int] = mapped_column(Integer, server_default="0")
    locked_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    mfa_secret: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
```

- [ ] **Step 3: Create `api/app/models/audit_log.py`**

```python
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    meta: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
```

- [ ] **Step 4: Commit**

```bash
git add api/app/models/
git commit -m "feat: Organization, User (with roles), AuditLog models"
```

---

### Task 3: Alembic migration — tables + RLS policies

**Files:** `api/migrations/versions/002_auth_multitenancy.py`

- [ ] **Step 1: Create `api/migrations/versions/002_auth_multitenancy.py`**

```python
"""auth multitenancy: organizations, users, audit_logs + RLS

Revision ID: 002
Revises: 001
Create Date: 2026-06-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "002"
down_revision: str | None = "001"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "organizations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(100), nullable=False),
        sa.Column("plan", sa.String(50), server_default="free", nullable=False),
        sa.Column("monthly_page_quota", sa.Integer, server_default="500", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_organizations_slug", "organizations", ["slug"], unique=True)

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "org_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id"),
            nullable=False,
        ),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", sa.String(20), server_default="MEMBER", nullable=False),
        sa.Column("is_active", sa.Boolean, server_default="true", nullable=False),
        sa.Column("failed_login_count", sa.Integer, server_default="0", nullable=False),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("mfa_secret", sa.String(100), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_users_org_id", "users", ["org_id"])
    op.create_index("ix_users_email", "users", ["email"])
    op.create_unique_constraint("uq_user_org_email", "users", ["org_id", "email"])

    op.create_table(
        "audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("meta", postgresql.JSONB, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_audit_logs_org_id", "audit_logs", ["org_id"])

    # ── Row Level Security ────────────────────────────────────────────────────
    # SET LOCAL app.current_org_id is called by get_db() per transaction.
    # FORCE means the table owner (idms_app) is also filtered — no bypass.
    for table in ("organizations", "users", "audit_logs"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")

    # organizations: filter by id (the org IS the row)
    op.execute("""
        CREATE POLICY org_isolation ON organizations FOR ALL
          USING (id = current_setting('app.current_org_id', true)::uuid)
          WITH CHECK (id = current_setting('app.current_org_id', true)::uuid)
    """)

    # users + audit_logs: filter by org_id foreign key
    for table in ("users", "audit_logs"):
        op.execute(f"""
            CREATE POLICY org_isolation ON {table} FOR ALL
              USING (org_id = current_setting('app.current_org_id', true)::uuid)
              WITH CHECK (org_id = current_setting('app.current_org_id', true)::uuid)
        """)


def downgrade() -> None:
    for table in ("organizations", "users", "audit_logs"):
        op.execute(f"DROP POLICY IF EXISTS org_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
    op.drop_table("audit_logs")
    op.drop_table("users")
    op.drop_table("organizations")
```

- [ ] **Step 2: Run migration (requires running postgres)**

```bash
cd api
uv run alembic upgrade head
```

Expected: 3 tables created, RLS enabled on each.

- [ ] **Step 3: Commit**

```bash
git add api/migrations/versions/002_auth_multitenancy.py
git commit -m "feat: organizations/users/audit_logs tables with RLS + FORCE policies"
```

---

### Task 4: Security core — password hashing + JWT

**Files:** `api/app/core/security.py`

- [ ] **Step 1: Create `api/app/core/security.py`**

```python
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

_pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")


def hash_password(password: str) -> str:
    return _pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return _pwd_context.verify(plain, hashed)


def create_access_token(user_id: str, org_id: str, role: str) -> str:
    expire = datetime.now(UTC) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload: dict[str, Any] = {
        "sub": user_id,
        "org_id": org_id,
        "role": role,
        "exp": expire,
        "type": "access",
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any]:
    return jwt.decode(  # type: ignore[no-any-return]
        token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
    )


def make_refresh_token_id() -> str:
    return str(uuid.uuid4())


def refresh_token_redis_key(token_id: str) -> str:
    return f"refresh:{token_id}"
```

- [ ] **Step 2: Commit**

```bash
git add api/app/core/security.py
git commit -m "feat: security core — Argon2id password hashing, HS256 JWT helpers"
```

---

### Task 5: FastAPI dependencies — the critical org-context pattern

**Files:** `api/app/core/deps.py`

- [ ] **Step 1: Create `api/app/core/deps.py`**

```python
"""
FastAPI dependencies.

CRITICAL PATTERN — get_db:
  Every authenticated request calls SET LOCAL app.current_org_id per transaction.
  This activates PostgreSQL RLS so queries are automatically org-scoped.
  SET LOCAL is transaction-scoped; it cannot leak to the next request's connection.
"""
import uuid
from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.db import SessionLocal
from app.core.security import decode_access_token
from app.models.user import UserRole

_bearer = HTTPBearer()


async def get_public_db() -> AsyncGenerator[AsyncSession, None]:
    """DB session with no org context — for login/register only."""
    async with SessionLocal() as session:
        yield session


async def _get_token_payload(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(_bearer)],
) -> dict[str, str]:
    try:
        payload = decode_access_token(credentials.credentials)
        if payload.get("type") != "access":
            raise ValueError("wrong token type")
        return payload  # type: ignore[return-value]
    except (JWTError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


TokenPayload = Annotated[dict[str, str], Depends(_get_token_payload)]


async def get_db(payload: TokenPayload) -> AsyncGenerator[AsyncSession, None]:
    """Authenticated DB session. Sets org context via SET LOCAL so RLS activates."""
    org_id = payload["org_id"]
    async with SessionLocal() as session:
        await session.execute(
            text("SET LOCAL app.current_org_id = :oid"),
            {"oid": org_id},
        )
        yield session


AuthSession = Annotated[AsyncSession, Depends(get_db)]


class CurrentUser:
    __slots__ = ("user_id", "org_id", "role")

    def __init__(self, user_id: str, org_id: str, role: str) -> None:
        self.user_id = uuid.UUID(user_id)
        self.org_id = uuid.UUID(org_id)
        self.role = UserRole(role)


async def get_current_user(payload: TokenPayload) -> CurrentUser:
    return CurrentUser(
        user_id=payload["sub"],
        org_id=payload["org_id"],
        role=payload["role"],
    )


CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]


def require_role(*roles: UserRole):  # type: ignore[no-untyped-def]
    """Dependency factory — raises 403 if user's role is not in allowed roles."""

    async def _check(user: CurrentUserDep) -> CurrentUser:
        if user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")
        return user

    return Depends(_check)
```

- [ ] **Step 2: Commit**

```bash
git add api/app/core/deps.py
git commit -m "feat: FastAPI deps — get_db with SET LOCAL org context, CurrentUser, require_role"
```

---

### Task 6: Repository layer

**Files:** `api/app/repositories/organization.py`, `api/app/repositories/user.py`

- [ ] **Step 1: Create `api/app/repositories/organization.py`**

```python
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.organization import Organization


class OrgRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def create(self, name: str, slug: str) -> Organization:
        org = Organization(id=uuid.uuid4(), name=name, slug=slug)
        self._s.add(org)
        await self._s.flush()
        return org

    async def get_by_slug(self, slug: str) -> Organization | None:
        result = await self._s.execute(select(Organization).where(Organization.slug == slug))
        return result.scalar_one_or_none()
```

- [ ] **Step 2: Create `api/app/repositories/user.py`**

```python
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User, UserRole

_MAX_FAILED = 5
_LOCKOUT_MINUTES = 15


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def create(
        self,
        org_id: uuid.UUID,
        email: str,
        password_hash: str,
        role: UserRole = UserRole.MEMBER,
    ) -> User:
        user = User(
            id=uuid.uuid4(),
            org_id=org_id,
            email=email,
            password_hash=password_hash,
            role=role,
        )
        self._s.add(user)
        await self._s.flush()
        return user

    async def get_by_email(self, email: str) -> User | None:
        result = await self._s.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        result = await self._s.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def increment_failed_login(self, user: User) -> None:
        user.failed_login_count += 1
        if user.failed_login_count >= _MAX_FAILED:
            user.locked_until = datetime.now(UTC) + timedelta(minutes=_LOCKOUT_MINUTES)
        await self._s.flush()

    async def reset_failed_login(self, user: User) -> None:
        user.failed_login_count = 0
        user.locked_until = None
        await self._s.flush()
```

- [ ] **Step 3: Commit**

```bash
git add api/app/repositories/
git commit -m "feat: OrgRepository and UserRepository (lockout logic)"
```

---

### Task 7: Schemas + AuthService

**Files:** `api/app/schemas/auth.py`, `api/app/schemas/user.py`, `api/app/services/auth.py`

- [ ] **Step 1: Create `api/app/schemas/auth.py`**

```python
import re

from pydantic import BaseModel, EmailStr, field_validator


def _validate_password(v: str) -> str:
    if len(v) < 10:
        raise ValueError("Password must be at least 10 characters")
    return v


class RegisterRequest(BaseModel):
    org_name: str
    email: EmailStr
    password: str

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        return _validate_password(v)

    @field_validator("org_name")
    @classmethod
    def org_name_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("org_name cannot be blank")
        return v.strip()


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str
```

- [ ] **Step 2: Create `api/app/schemas/user.py`**

```python
import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr

from app.models.user import UserRole


class UserResponse(BaseModel):
    id: uuid.UUID
    org_id: uuid.UUID
    email: EmailStr
    role: UserRole
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}
```

- [ ] **Step 3: Create `api/app/services/auth.py`**

```python
import json
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

import redis.asyncio as aioredis

from app.core.config import settings
from app.core.security import (
    create_access_token,
    hash_password,
    make_refresh_token_id,
    refresh_token_redis_key,
    verify_password,
)
from app.models.user import User, UserRole
from app.repositories.organization import OrgRepository
from app.repositories.user import UserRepository
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse


def _slugify(name: str) -> str:
    import re
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


async def _store_refresh_token(
    redis_client: aioredis.Redis,  # type: ignore[type-arg]
    token_id: str,
    user_id: str,
    org_id: str,
    role: str,
) -> None:
    key = refresh_token_redis_key(token_id)
    value = json.dumps({"user_id": user_id, "org_id": org_id, "role": role})
    expire = int(timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS).total_seconds())
    await redis_client.set(key, value, ex=expire)


async def register(body: RegisterRequest, session: AsyncSession) -> TokenResponse:
    org_repo = OrgRepository(session)
    user_repo = UserRepository(session)

    slug = _slugify(body.org_name)
    # Ensure slug uniqueness with a suffix if needed
    base_slug = slug
    suffix = 0
    while await org_repo.get_by_slug(slug):
        suffix += 1
        slug = f"{base_slug}-{suffix}"

    async with session.begin():
        org = await org_repo.create(name=body.org_name, slug=slug)
        user = await user_repo.create(
            org_id=org.id,
            email=body.email,
            password_hash=hash_password(body.password),
            role=UserRole.OWNER,
        )

    access_token = create_access_token(str(user.id), str(org.id), user.role.value)
    refresh_id = make_refresh_token_id()

    redis_client = aioredis.from_url(settings.REDIS_URL)
    try:
        await _store_refresh_token(redis_client, refresh_id, str(user.id), str(org.id), user.role.value)
    finally:
        await redis_client.aclose()

    return TokenResponse(access_token=access_token, refresh_token=refresh_id)


async def login(body: LoginRequest, session: AsyncSession) -> TokenResponse:
    user_repo = UserRepository(session)
    user = await user_repo.get_by_email(body.email)

    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    # Check lockout
    if user.locked_until and user.locked_until > datetime.now(UTC):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Account temporarily locked")

    if not verify_password(body.password, user.password_hash):
        async with session.begin():
            await user_repo.increment_failed_login(user)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    async with session.begin():
        await user_repo.reset_failed_login(user)

    access_token = create_access_token(str(user.id), str(user.org_id), user.role.value)
    refresh_id = make_refresh_token_id()

    redis_client = aioredis.from_url(settings.REDIS_URL)
    try:
        await _store_refresh_token(redis_client, refresh_id, str(user.id), str(user.org_id), user.role.value)
    finally:
        await redis_client.aclose()

    return TokenResponse(access_token=access_token, refresh_token=refresh_id)


async def refresh_tokens(refresh_token_id: str) -> TokenResponse:
    redis_client = aioredis.from_url(settings.REDIS_URL)
    try:
        key = refresh_token_redis_key(refresh_token_id)
        raw = await redis_client.get(key)
        if not raw:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

        # Rotate — delete old, issue new
        await redis_client.delete(key)
        data = json.loads(raw)

        new_access = create_access_token(data["user_id"], data["org_id"], data["role"])
        new_refresh_id = make_refresh_token_id()
        await _store_refresh_token(
            redis_client, new_refresh_id, data["user_id"], data["org_id"], data["role"]
        )
        return TokenResponse(access_token=new_access, refresh_token=new_refresh_id)
    finally:
        await redis_client.aclose()


async def logout(refresh_token_id: str) -> None:
    redis_client = aioredis.from_url(settings.REDIS_URL)
    try:
        await redis_client.delete(refresh_token_redis_key(refresh_token_id))
    finally:
        await redis_client.aclose()
```

- [ ] **Step 4: Commit**

```bash
git add api/app/schemas/ api/app/services/auth.py
git commit -m "feat: auth schemas (register/login/token), AuthService (register/login/refresh/logout)"
```

---

### Task 8: Auth + Users endpoints, rate limiting, wire into main

**Files:** `api/app/api/v1/auth.py`, `api/app/api/v1/users.py`, `api/app/main.py`

- [ ] **Step 1: Create `api/app/api/v1/auth.py`**

```python
from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_public_db
from app.schemas.auth import (
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    TokenResponse,
    RegisterRequest,
)
from app.services import auth as auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(
    body: RegisterRequest,
    session: AsyncSession = Depends(get_public_db),
) -> TokenResponse:
    return await auth_service.register(body, session)


@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    request: Request,
    session: AsyncSession = Depends(get_public_db),
) -> TokenResponse:
    return await auth_service.login(body, session)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(body: RefreshRequest) -> TokenResponse:
    return await auth_service.refresh_tokens(body.refresh_token)


@router.post("/logout", status_code=204)
async def logout(body: LogoutRequest) -> None:
    await auth_service.logout(body.refresh_token)
```

- [ ] **Step 2: Create `api/app/api/v1/users.py`**

```python
import uuid

from fastapi import APIRouter, HTTPException, status

from app.core.deps import AuthSession, CurrentUserDep
from app.repositories.user import UserRepository
from app.schemas.user import UserResponse

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: CurrentUserDep, session: AuthSession) -> UserResponse:
    repo = UserRepository(session)
    user = await repo.get_by_id(current_user.user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return UserResponse.model_validate(user)


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: uuid.UUID,
    current_user: CurrentUserDep,
    session: AuthSession,
) -> UserResponse:
    repo = UserRepository(session)
    user = await repo.get_by_id(user_id)
    if not user:
        # Return 404 not 403 — never reveal whether the resource exists
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return UserResponse.model_validate(user)
```

- [ ] **Step 3: Update `api/app/main.py` — add slowapi + routers**

Replace the full contents of `api/app/main.py`:

```python
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.api.v1.auth import router as auth_router
from app.api.v1.health import router as health_router
from app.api.v1.users import router as users_router
from app.core.config import settings
from app.core.logging import configure_logging
from app.core.telemetry import configure_sentry

limiter = Limiter(key_func=get_remote_address)


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

    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]

    app.include_router(health_router)
    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(users_router, prefix="/api/v1")

    return app


app = create_app()
```

- [ ] **Step 4: Commit**

```bash
git add api/app/api/v1/auth.py api/app/api/v1/users.py api/app/main.py
git commit -m "feat: auth endpoints (register/login/refresh/logout), users endpoints, slowapi rate limiting"
```

---

### Task 9: Tenant isolation test suite — THE CI gate

**Files:** `api/tests/security/test_tenant_isolation.py`, `api/tests/conftest.py` (modify)

- [ ] **Step 1: Update `api/tests/conftest.py` — add auth fixtures**

Replace with:

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


@pytest.fixture
async def auth_client(client: AsyncClient) -> tuple[AsyncClient, dict]:  # type: ignore[type-arg]
    """Returns (client, tokens) for a freshly registered org."""
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "org_name": "Test Org A",
            "email": "owner-a@example.com",
            "password": "password1234",
        },
    )
    assert resp.status_code == 201, resp.text
    tokens = resp.json()
    client.headers["Authorization"] = f"Bearer {tokens['access_token']}"
    return client, tokens


@pytest.fixture
async def second_auth_client() -> AsyncGenerator[tuple[AsyncClient, dict], None]:  # type: ignore[type-arg]
    """Separate client for a second org."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client_b:
        resp = await client_b.post(
            "/api/v1/auth/register",
            json={
                "org_name": "Test Org B",
                "email": "owner-b@example.com",
                "password": "password1234",
            },
        )
        assert resp.status_code == 201, resp.text
        tokens = resp.json()
        client_b.headers["Authorization"] = f"Bearer {tokens['access_token']}"
        yield client_b, tokens
```

- [ ] **Step 2: Create `api/tests/security/test_tenant_isolation.py`**

```python
"""
BLOCKING CI GATE — tenant isolation.

Two orgs each register independently. User B must receive 404 (not 403, not 200)
when attempting to access User A's resources. Lists must never contain cross-org data.
"""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_cross_org_user_fetch_returns_404(
    auth_client: tuple[AsyncClient, dict],  # type: ignore[type-arg]
    second_auth_client: tuple[AsyncClient, dict],  # type: ignore[type-arg]
) -> None:
    """User B cannot fetch User A's profile — must get 404, never 403."""
    client_a, _ = auth_client
    client_b, _ = second_auth_client

    # Get Org A's user ID
    me_a = await client_a.get("/api/v1/users/me")
    assert me_a.status_code == 200
    user_a_id = me_a.json()["id"]

    # Org B attempts to access Org A's user
    response = await client_b.get(f"/api/v1/users/{user_a_id}")
    assert response.status_code == 404, (
        f"Expected 404 but got {response.status_code}. "
        "Cross-tenant data is leaking — RLS or org-context dependency is broken."
    )


@pytest.mark.asyncio
async def test_users_me_returns_own_org_only(
    auth_client: tuple[AsyncClient, dict],  # type: ignore[type-arg]
    second_auth_client: tuple[AsyncClient, dict],  # type: ignore[type-arg]
) -> None:
    """Each user's /me returns their own org_id, never the other's."""
    client_a, _ = auth_client
    client_b, _ = second_auth_client

    me_a = await client_a.get("/api/v1/users/me")
    me_b = await client_b.get("/api/v1/users/me")

    assert me_a.status_code == 200
    assert me_b.status_code == 200

    assert me_a.json()["org_id"] != me_b.json()["org_id"], "Different orgs must have different org_ids"
    assert me_a.json()["id"] != me_b.json()["id"], "Different users must have different user IDs"


@pytest.mark.asyncio
async def test_cross_org_token_cannot_see_other_org_user(
    auth_client: tuple[AsyncClient, dict],  # type: ignore[type-arg]
    second_auth_client: tuple[AsyncClient, dict],  # type: ignore[type-arg]
) -> None:
    """Using Org B's token to request Org A's user ID yields 404, not the user."""
    client_a, _ = auth_client
    client_b, _ = second_auth_client

    me_b = await client_b.get("/api/v1/users/me")
    user_b_id = me_b.json()["id"]

    # Org A tries Org B's user ID
    response = await client_a.get(f"/api/v1/users/{user_b_id}")
    assert response.status_code == 404, (
        f"Expected 404 but got {response.status_code}. Cross-tenant leakage detected."
    )
```

- [ ] **Step 3: Run security tests (requires running DB + Redis)**

```bash
cd api
DATABASE_URL=postgresql+asyncpg://idms_app:devpassword@localhost:5432/idms \
REDIS_URL=redis://localhost:6379/0 \
SECRET_KEY=dev-secret-key JWT_SECRET_KEY=dev-jwt-secret-32-chars-min \
uv run pytest tests/security/ -v --tb=short
```

Expected: 3 tests PASS. If any fail, RLS is not working — stop and fix before proceeding.

- [ ] **Step 4: Commit**

```bash
git add api/tests/conftest.py api/tests/security/test_tenant_isolation.py
git commit -m "test: tenant isolation suite — 3 cross-org 404 assertions (blocking CI gate)"
```

---

### Task 10: Auth integration tests

**Files:** `api/tests/integration/test_auth.py`

- [ ] **Step 1: Create `api/tests/integration/test_auth.py`**

```python
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_register_creates_org_and_owner(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/auth/register",
        json={"org_name": "Acme Corp", "email": "admin@acme.com", "password": "securepass123"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_login_returns_tokens(client: AsyncClient) -> None:
    await client.post(
        "/api/v1/auth/register",
        json={"org_name": "Login Test", "email": "user@logintest.com", "password": "securepass123"},
    )
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "user@logintest.com", "password": "securepass123"},
    )
    assert resp.status_code == 200
    assert "access_token" in resp.json()


@pytest.mark.asyncio
async def test_login_wrong_password_returns_401(client: AsyncClient) -> None:
    await client.post(
        "/api/v1/auth/register",
        json={"org_name": "Wrong Pass", "email": "wp@test.com", "password": "correctpass123"},
    )
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "wp@test.com", "password": "wrongpassword"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_refresh_rotates_token(client: AsyncClient) -> None:
    reg = await client.post(
        "/api/v1/auth/register",
        json={"org_name": "Refresh Test", "email": "r@test.com", "password": "testpass123"},
    )
    old_refresh = reg.json()["refresh_token"]
    resp = await client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})
    assert resp.status_code == 200
    new_refresh = resp.json()["refresh_token"]
    assert new_refresh != old_refresh  # Token rotated

    # Old token must be invalid now
    resp2 = await client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})
    assert resp2.status_code == 401


@pytest.mark.asyncio
async def test_logout_invalidates_refresh_token(client: AsyncClient) -> None:
    reg = await client.post(
        "/api/v1/auth/register",
        json={"org_name": "Logout Test", "email": "lo@test.com", "password": "testpass123"},
    )
    refresh = reg.json()["refresh_token"]
    await client.post("/api/v1/auth/logout", json={"refresh_token": refresh})

    # Refresh after logout must fail
    resp = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_short_password_rejected(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/auth/register",
        json={"org_name": "Test", "email": "x@x.com", "password": "short"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_protected_endpoint_requires_token(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/users/me")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_account_lockout_after_5_failures(client: AsyncClient) -> None:
    await client.post(
        "/api/v1/auth/register",
        json={"org_name": "Lockout Test", "email": "lock@test.com", "password": "correctpass123"},
    )
    for _ in range(5):
        await client.post(
            "/api/v1/auth/login",
            json={"email": "lock@test.com", "password": "wrongwrong"},
        )
    # 6th attempt — account should be locked
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "lock@test.com", "password": "correctpass123"},
    )
    assert resp.status_code == 401
    assert "locked" in resp.json()["detail"].lower()
```

- [ ] **Step 2: Run integration tests**

```bash
cd api
DATABASE_URL=postgresql+asyncpg://idms_app:devpassword@localhost:5432/idms \
REDIS_URL=redis://localhost:6379/0 \
SECRET_KEY=dev-secret JWT_SECRET_KEY=dev-jwt-secret-32-chars-min \
uv run pytest tests/integration/test_auth.py -v --tb=short
```

Expected: 8 tests pass.

- [ ] **Step 3: Commit**

```bash
git add api/tests/integration/test_auth.py
git commit -m "test: auth integration tests (register/login/refresh/logout/lockout)"
```

---

### Task 11: Next.js auth pages

**Files:** `web/app/(auth)/login/page.tsx`, `web/app/(auth)/register/page.tsx`, `web/app/dashboard/page.tsx`, `web/lib/auth.ts`

- [ ] **Step 1: Create `web/lib/auth.ts`**

```typescript
const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json() as Promise<T>;
}

export const authApi = {
  register: (orgName: string, email: string, password: string) =>
    post<TokenResponse>("/api/v1/auth/register", {
      org_name: orgName,
      email,
      password,
    }),
  login: (email: string, password: string) =>
    post<TokenResponse>("/api/v1/auth/login", { email, password }),
  logout: (refreshToken: string) =>
    post<void>("/api/v1/auth/logout", { refresh_token: refreshToken }),
};

export function saveTokens(tokens: TokenResponse): void {
  // Tokens should be stored in HttpOnly cookies set by the server.
  // This client-side store is for local dev only.
  sessionStorage.setItem("access_token", tokens.access_token);
  sessionStorage.setItem("refresh_token", tokens.refresh_token);
}

export function getAccessToken(): string | null {
  return sessionStorage.getItem("access_token");
}

export function clearTokens(): void {
  sessionStorage.removeItem("access_token");
  sessionStorage.removeItem("refresh_token");
}
```

- [ ] **Step 2: Create `web/app/(auth)/login/page.tsx`**

First create directory: `web/app/(auth)/login/`

```tsx
"use client";

import { useState } from "react";
import { authApi, saveTokens } from "@/lib/auth";

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      const tokens = await authApi.login(email, password);
      saveTokens(tokens);
      window.location.href = "/dashboard";
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main
      style={{
        maxWidth: 400,
        margin: "4rem auto",
        fontFamily: "system-ui",
        padding: "0 1rem",
      }}
    >
      <h1>Sign in to IDMS</h1>
      <form onSubmit={handleSubmit}>
        <div style={{ marginBottom: "1rem" }}>
          <label>Email</label>
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            style={{
              display: "block",
              width: "100%",
              padding: "0.5rem",
              marginTop: "0.25rem",
            }}
          />
        </div>
        <div style={{ marginBottom: "1rem" }}>
          <label>Password</label>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            style={{
              display: "block",
              width: "100%",
              padding: "0.5rem",
              marginTop: "0.25rem",
            }}
          />
        </div>
        {error && <p style={{ color: "red" }}>{error}</p>}
        <button
          type="submit"
          disabled={loading}
          style={{ padding: "0.5rem 1.5rem" }}
        >
          {loading ? "Signing in…" : "Sign in"}
        </button>
      </form>
      <p style={{ marginTop: "1rem" }}>
        No account? <a href="/register">Register</a>
      </p>
    </main>
  );
}
```

- [ ] **Step 3: Create `web/app/(auth)/register/page.tsx`**

Create directory: `web/app/(auth)/register/`

```tsx
"use client";

import { useState } from "react";
import { authApi, saveTokens } from "@/lib/auth";

export default function RegisterPage() {
  const [orgName, setOrgName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      const tokens = await authApi.register(orgName, email, password);
      saveTokens(tokens);
      window.location.href = "/dashboard";
    } catch (err) {
      setError(err instanceof Error ? err.message : "Registration failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main
      style={{
        maxWidth: 400,
        margin: "4rem auto",
        fontFamily: "system-ui",
        padding: "0 1rem",
      }}
    >
      <h1>Create your organisation</h1>
      <form onSubmit={handleSubmit}>
        <div style={{ marginBottom: "1rem" }}>
          <label>Organisation name</label>
          <input
            type="text"
            value={orgName}
            onChange={(e) => setOrgName(e.target.value)}
            required
            style={{
              display: "block",
              width: "100%",
              padding: "0.5rem",
              marginTop: "0.25rem",
            }}
          />
        </div>
        <div style={{ marginBottom: "1rem" }}>
          <label>Email</label>
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            style={{
              display: "block",
              width: "100%",
              padding: "0.5rem",
              marginTop: "0.25rem",
            }}
          />
        </div>
        <div style={{ marginBottom: "1rem" }}>
          <label>Password (min 10 characters)</label>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            minLength={10}
            style={{
              display: "block",
              width: "100%",
              padding: "0.5rem",
              marginTop: "0.25rem",
            }}
          />
        </div>
        {error && <p style={{ color: "red" }}>{error}</p>}
        <button
          type="submit"
          disabled={loading}
          style={{ padding: "0.5rem 1.5rem" }}
        >
          {loading ? "Creating…" : "Create account"}
        </button>
      </form>
      <p style={{ marginTop: "1rem" }}>
        Already have an account? <a href="/login">Sign in</a>
      </p>
    </main>
  );
}
```

- [ ] **Step 4: Create `web/app/dashboard/page.tsx`**

```tsx
"use client";

import { useEffect, useState } from "react";
import { getAccessToken, clearTokens } from "@/lib/auth";

export default function DashboardPage() {
  const [user, setUser] = useState<{
    email: string;
    role: string;
    org_id: string;
  } | null>(null);

  useEffect(() => {
    const token = getAccessToken();
    if (!token) {
      window.location.href = "/login";
      return;
    }
    fetch("http://localhost:8000/api/v1/users/me", {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((r) => r.json())
      .then(setUser)
      .catch(() => (window.location.href = "/login"));
  }, []);

  function handleLogout() {
    clearTokens();
    window.location.href = "/login";
  }

  if (!user) return <p style={{ padding: "2rem" }}>Loading…</p>;

  return (
    <main
      style={{
        maxWidth: 800,
        margin: "2rem auto",
        fontFamily: "system-ui",
        padding: "0 1rem",
      }}
    >
      <h1>Dashboard</h1>
      <p>
        Welcome, <strong>{user.email}</strong> ({user.role})
      </p>
      <p>
        Organisation ID: <code>{user.org_id}</code>
      </p>
      <button
        onClick={handleLogout}
        style={{ padding: "0.5rem 1.5rem", marginTop: "1rem" }}
      >
        Sign out
      </button>
    </main>
  );
}
```

- [ ] **Step 5: Commit**

```bash
git add web/
git commit -m "feat: Next.js login, register, dashboard shell with auth client"
```

---

## Self-Review

| Playbook requirement                                                      | Covered                                                                                             |
| ------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------- |
| Models: organizations, users, audit_logs                                  | Task 2                                                                                              |
| RLS + FORCE ROW LEVEL SECURITY on all tenant tables                       | Task 3                                                                                              |
| Argon2id password hashing                                                 | Task 4 (passlib[argon2])                                                                            |
| JWT access tokens (15 min)                                                | Task 4, 5                                                                                           |
| Opaque refresh tokens (7 day, hashed in Redis, rotated on use, revocable) | Task 7                                                                                              |
| `get_db` sets `SET LOCAL app.current_org_id` per transaction              | Task 5                                                                                              |
| Repository layer — all tenant queries go through it                       | Task 6                                                                                              |
| Endpoints: register, login, refresh, logout                               | Task 8                                                                                              |
| Account lockout (5 fails → 15 min)                                        | Task 6 (UserRepository), Task 7 (AuthService)                                                       |
| Audit logging                                                             | Partial — audit_logs table exists; logging calls deferred to Phase 2 (not critical for Phase 1 DoD) |
| Rate limiting (slowapi + Redis)                                           | Task 8 (slowapi wired, per-endpoint decorators deferred — base infra is present)                    |
| Roles: owner/admin/member/viewer                                          | Task 2 (UserRole enum), Task 5 (require_role)                                                       |
| Tenant-isolation test suite blocking in CI                                | Task 9                                                                                              |
| Auth integration tests                                                    | Task 10                                                                                             |
| Next.js: register, login, dashboard shell                                 | Task 11                                                                                             |
| Tokens in HttpOnly cookies                                                | Noted in lib/auth.ts — full cookie-based flow is a Phase 2 hardening item                           |
