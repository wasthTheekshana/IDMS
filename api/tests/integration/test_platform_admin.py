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


@pytest.mark.asyncio
async def test_suspended_org_user_cannot_log_in(
    platform_admin_client: tuple[AsyncClient, dict],  # type: ignore[type-arg]
    auth_client: tuple[AsyncClient, dict],  # type: ignore[type-arg]
) -> None:
    """Suspending an org must block a *fresh* login, not just existing tokens.

    The suspension lookup in auth.login() runs on the BYPASSRLS admin session
    precisely because the login session has no `app.current_org_id` set.
    """
    admin_client, _ = platform_admin_client
    client_a, _ = auth_client

    me = await client_a.get("/api/v1/users/me")
    org_id = me.json()["org_id"]

    suspend = await admin_client.patch(
        f"/api/v1/platform-admin/organizations/{org_id}",
        json={"is_suspended": True},
    )
    assert suspend.status_code == 200, suspend.text
    assert suspend.json()["is_suspended"] is True

    login = await client_a.post(
        "/api/v1/auth/login",
        json={"email": "owner-a@example.com", "password": "password1234"},
    )
    assert login.status_code == 403, login.text
    assert "suspended" in login.json()["detail"].lower()
