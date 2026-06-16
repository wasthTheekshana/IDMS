from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.core.db import SessionLocal
from app.main import app


@pytest.fixture(autouse=True)
async def clean_db() -> None:
    """Truncate all tenant tables before each test so tests are independent."""
    _sql = "TRUNCATE TABLE audit_logs, users, organizations RESTART IDENTITY CASCADE"
    async with SessionLocal.begin() as session:
        await session.execute(text(_sql))


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
