from collections.abc import Generator

import pytest
from httpx import AsyncClient

from app.core.ratelimit import limiter


@pytest.fixture
def rate_limits_on() -> Generator[None, None, None]:
    limiter.reset()
    limiter.enabled = True
    yield
    limiter.enabled = False
    limiter.reset()


async def test_login_returns_429_after_10_attempts(
    client: AsyncClient, rate_limits_on: None
) -> None:
    payload = {"email": "nobody@example.com", "password": "wrongpassword"}
    for _ in range(10):
        resp = await client.post("/api/v1/auth/login", json=payload)
        assert resp.status_code != 429
    resp = await client.post("/api/v1/auth/login", json=payload)
    assert resp.status_code == 429


async def test_register_returns_429_after_5_attempts(
    client: AsyncClient, rate_limits_on: None
) -> None:
    for i in range(5):
        resp = await client.post(
            "/api/v1/auth/register",
            json={
                "org_name": f"RL Org {i}",
                "email": f"rl-{i}@example.com",
                "password": "password1234",
            },
        )
        assert resp.status_code != 429
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "org_name": "RL Org 5",
            "email": "rl-5@example.com",
            "password": "password1234",
        },
    )
    assert resp.status_code == 429
