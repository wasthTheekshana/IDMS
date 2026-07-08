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


# ---- list users ----


async def test_list_users_shows_own_org_only(
    auth_client: tuple[AsyncClient, dict],  # type: ignore[type-arg]
    second_auth_client: tuple[AsyncClient, dict],  # type: ignore[type-arg]
) -> None:
    client, _ = auth_client
    resp = await client.get("/api/v1/users")
    assert resp.status_code == 200
    emails = [u["email"] for u in resp.json()]
    assert emails == ["owner-a@example.com"]  # org B's owner not visible


async def test_list_users_requires_auth(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/users")
    assert resp.status_code == 401
