from httpx import AsyncClient
from sqlalchemy import text

from app.core.db import SessionLocal


async def _set_active(email: str, active: bool) -> None:
    async with SessionLocal.begin() as session:
        await session.execute(
            text("UPDATE users SET is_active = :a WHERE email = :e"),
            {"a": active, "e": email},
        )


async def test_deactivated_user_cannot_login(
    auth_client: tuple[AsyncClient, dict],  # type: ignore[type-arg]
) -> None:
    client, _ = auth_client
    await _set_active("owner-a@example.com", False)
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "owner-a@example.com", "password": "password1234"},
    )
    assert resp.status_code == 401
    assert "deactivated" in resp.json()["detail"].lower()


async def test_active_user_can_login(
    auth_client: tuple[AsyncClient, dict],  # type: ignore[type-arg]
) -> None:
    client, _ = auth_client
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "owner-a@example.com", "password": "password1234"},
    )
    assert resp.status_code == 200
