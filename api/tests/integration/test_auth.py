import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_register_creates_org_and_owner(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "org_name": "Acme Corp",
            "email": "admin@acme.com",
            "password": "securepass123",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"  # noqa: S105


@pytest.mark.asyncio
async def test_login_returns_tokens(client: AsyncClient) -> None:
    await client.post(
        "/api/v1/auth/register",
        json={
            "org_name": "Login Test",
            "email": "user@logintest.com",
            "password": "securepass123",
        },
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
        json={
            "org_name": "Wrong Pass",
            "email": "wp@test.com",
            "password": "correctpass123",
        },
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
        json={
            "org_name": "Refresh Test",
            "email": "r@test.com",
            "password": "testpass123",
        },
    )
    old_refresh = reg.json()["refresh_token"]
    resp = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": old_refresh}
    )
    assert resp.status_code == 200
    new_refresh = resp.json()["refresh_token"]
    assert new_refresh != old_refresh

    resp2 = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": old_refresh}
    )
    assert resp2.status_code == 401


@pytest.mark.asyncio
async def test_logout_invalidates_refresh_token(client: AsyncClient) -> None:
    reg = await client.post(
        "/api/v1/auth/register",
        json={
            "org_name": "Logout Test",
            "email": "lo@test.com",
            "password": "testpass123",
        },
    )
    refresh = reg.json()["refresh_token"]
    await client.post("/api/v1/auth/logout", json={"refresh_token": refresh})

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
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_account_lockout_after_5_failures(client: AsyncClient) -> None:
    await client.post(
        "/api/v1/auth/register",
        json={
            "org_name": "Lockout Test",
            "email": "lock@test.com",
            "password": "correctpass123",
        },
    )
    for _ in range(5):
        await client.post(
            "/api/v1/auth/login",
            json={"email": "lock@test.com", "password": "wrongwrong"},
        )
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "lock@test.com", "password": "correctpass123"},
    )
    assert resp.status_code == 401
    assert "locked" in resp.json()["detail"].lower()
