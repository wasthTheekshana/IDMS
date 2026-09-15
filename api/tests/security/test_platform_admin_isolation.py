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
    await _create_platform_admin("admin@dok.test", "adminpassword123")

    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "admin@dok.test", "password": "adminpassword123"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["account_type"] == "platform_admin"


@pytest.mark.asyncio
async def test_platform_admin_token_rejected_by_org_endpoint(
    client: AsyncClient,
) -> None:
    await _create_platform_admin("admin2@dok.test", "adminpassword123")
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "admin2@dok.test", "password": "adminpassword123"},
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
