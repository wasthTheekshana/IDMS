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

    me_a = await client_a.get("/api/v1/users/me")
    assert me_a.status_code == 200
    user_a_id = me_a.json()["id"]

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

    assert (
        me_a.json()["org_id"] != me_b.json()["org_id"]
    ), "Different orgs must have different org_ids"
    assert (
        me_a.json()["id"] != me_b.json()["id"]
    ), "Different users must have different user IDs"


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

    response = await client_a.get(f"/api/v1/users/{user_b_id}")
    assert (
        response.status_code == 404
    ), f"Expected 404 but got {response.status_code}. Cross-tenant leakage detected."
