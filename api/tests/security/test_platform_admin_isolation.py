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

from app.core.db import admin_session_factory
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


async def _deactivate_platform_admin(email: str) -> None:
    """Flip is_active off.

    Uses SessionLocal, not the admin session: idms_platform_admin is granted
    SELECT only (migration 007) — it is deliberately a read-only role.
    """
    from app.core.db import SessionLocal

    async with SessionLocal.begin() as session:
        result = await session.execute(
            select(PlatformAdmin).where(PlatformAdmin.email == email)
        )
        result.scalar_one().is_active = False


@pytest.mark.asyncio
async def test_admin_session_sees_rows_across_multiple_orgs(
    auth_client: tuple[AsyncClient, dict],  # type: ignore[type-arg]
    second_auth_client: tuple[AsyncClient, dict],  # type: ignore[type-arg]
) -> None:
    """Proves the BYPASSRLS bypass actually works — the whole point of the role."""
    async with admin_session_factory()() as session:
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
    """Precondition sanity-check, NOT a security proof.

    This only verifies that the `auth_client` and `second_auth_client` fixtures
    genuinely produced two distinct organizations — which is what makes the
    BYPASSRLS assertion in test_admin_session_sees_rows_across_multiple_orgs
    meaningful. It guards against a fixture regression (e.g. both fixtures
    collapsing onto one org, which would make that test pass vacuously). It
    asserts nothing about RLS enforcement itself.
    """
    client_a, _ = auth_client
    client_b, _ = second_auth_client

    orgs_a = await client_a.get("/api/v1/users/me")
    orgs_b = await client_b.get("/api/v1/users/me")
    assert orgs_a.json()["org_id"] != orgs_b.json()["org_id"]

    # Cross-org data isolation over the HTTP API is covered by
    # tests/security/test_tenant_isolation.py.
    #
    # KNOWN GAP: a genuinely adversarial test of the BYPASSRLS boundary —
    # opening a raw SessionLocal session, SET LOCAL app.current_org_id to org
    # A, and asserting org B's row is invisible — cannot be written honestly
    # here. It requires the application's database role to NOT be a superuser,
    # and the local/CI Postgres role is one (see infra/docker-compose.yml:
    # POSTGRES_USER: idms_app, which is created as the cluster superuser).
    # Superusers bypass RLS unconditionally, so such a test would report a
    # false PASS regardless of whether the real boundary is sound. Fixing this
    # means provisioning a non-superuser application role in
    # docker-compose/CI first; that is deliberately out of scope here.


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

    async with admin_session_factory().begin() as session:
        result = await session.execute(
            select(Organization).where(Organization.id == uuid.UUID(org_id))
        )
        org = result.scalar_one()
        org.is_suspended = True

    resp = await client.get("/api/v1/users/me")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_deactivated_platform_admin_blocked_on_next_request(
    platform_admin_client: tuple[AsyncClient, dict],  # type: ignore[type-arg]
) -> None:
    """is_active = false must be a working kill switch for an already-issued
    token — not merely a login-time check."""
    admin_client, _ = platform_admin_client

    assert (await admin_client.get("/api/v1/platform-admin/me")).status_code == 200

    await _deactivate_platform_admin("platform-admin@dok.example.com")

    resp = await admin_client.get("/api/v1/platform-admin/me")
    assert resp.status_code == 401, resp.text


@pytest.mark.asyncio
async def test_deactivated_platform_admin_cannot_refresh(
    platform_admin_client: tuple[AsyncClient, dict],  # type: ignore[type-arg]
) -> None:
    """A deactivated admin must not be able to keep minting token pairs off
    the Redis refresh-token state alone."""
    admin_client, tokens = platform_admin_client

    await _deactivate_platform_admin("platform-admin@dok.example.com")

    resp = await admin_client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert resp.status_code == 401, resp.text
