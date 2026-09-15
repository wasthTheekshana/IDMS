"""
FastAPI dependencies.

CRITICAL PATTERN — get_db:
  Every authenticated request calls SET LOCAL app.current_org_id per transaction.
  This activates PostgreSQL RLS so queries are automatically org-scoped.
  SET LOCAL is transaction-scoped; it cannot leak to the next request's connection.
"""

import uuid
import uuid as _uuid_module
from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError  # type: ignore[import-untyped]
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import SessionLocal, admin_session_factory
from app.core.security import decode_access_token
from app.models.user import UserRole
from app.repositories.platform_admin import PlatformAdminRepository

_bearer = HTTPBearer()


async def get_public_db() -> AsyncGenerator[AsyncSession, None]:
    """DB session with no org context — for login/register only."""
    async with SessionLocal.begin() as session:
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


async def get_admin_db() -> AsyncGenerator[AsyncSession, None]:
    """Cross-org session via the BYPASSRLS idms_platform_admin role.
    No SET LOCAL org context — the whole point is reading across every org.
    Only platform-admin routes may depend on this."""
    async with admin_session_factory().begin() as session:
        yield session


AdminSession = Annotated[AsyncSession, Depends(get_admin_db)]


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


AuthSession = Annotated[AsyncSession, Depends(get_db)]


class CurrentUser:
    __slots__ = ("user_id", "org_id", "role")

    def __init__(self, user_id: str, org_id: str, role: str) -> None:
        self.user_id = uuid.UUID(user_id)
        self.org_id = uuid.UUID(org_id)
        self.role = UserRole(role)


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


CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]


class CurrentPlatformAdmin:
    __slots__ = ("admin_id",)

    def __init__(self, admin_id: str) -> None:
        self.admin_id = uuid.UUID(admin_id)


async def get_current_platform_admin(
    payload: TokenPayload, session: AdminSession
) -> CurrentPlatformAdmin:
    """Validates the token AND the live platform_admins row.

    Checking the row on every request (not just at login) is what makes
    `is_active = false` a working kill switch for an already-issued token.
    """
    if payload.get("account_type") != "platform_admin":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not a platform admin token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        admin_id = uuid.UUID(payload["sub"])
    except (KeyError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or inactive admin",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    admin = await PlatformAdminRepository(session).get_by_id(admin_id)
    if not admin or not admin.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or inactive admin",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return CurrentPlatformAdmin(admin_id=payload["sub"])


CurrentPlatformAdminDep = Annotated[
    CurrentPlatformAdmin, Depends(get_current_platform_admin)
]


def require_role(*roles: UserRole):  # type: ignore[no-untyped-def]
    """Dependency factory — raises 403 if user's role is not in allowed roles."""

    async def _check(user: CurrentUserDep) -> CurrentUser:
        if user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role"
            )
        return user

    return Depends(_check)
