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


# ---- create user ----

_NEW_USER = {
    "email": "member-1@example.com",
    "password": "memberpass123",
    "role": "member",
}


async def test_owner_creates_member_who_can_login(
    auth_client: tuple[AsyncClient, dict],  # type: ignore[type-arg]
) -> None:
    client, _ = auth_client
    resp = await client.post("/api/v1/users", json=_NEW_USER)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["email"] == "member-1@example.com"
    assert body["role"] == "member"

    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "member-1@example.com", "password": "memberpass123"},
    )
    assert login.status_code == 200


async def test_duplicate_email_returns_409(
    auth_client: tuple[AsyncClient, dict],  # type: ignore[type-arg]
) -> None:
    client, _ = auth_client
    assert (await client.post("/api/v1/users", json=_NEW_USER)).status_code == 201
    resp = await client.post("/api/v1/users", json=_NEW_USER)
    assert resp.status_code == 409


async def test_member_cannot_create_users(
    auth_client: tuple[AsyncClient, dict],  # type: ignore[type-arg]
    client: AsyncClient,
) -> None:
    owner_client, _ = auth_client
    assert (await owner_client.post("/api/v1/users", json=_NEW_USER)).status_code == 201

    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "member-1@example.com", "password": "memberpass123"},
    )
    member_token = login.json()["access_token"]
    resp = await client.post(
        "/api/v1/users",
        json={"email": "x@example.com", "password": "password1234", "role": "viewer"},
        headers={"Authorization": f"Bearer {member_token}"},
    )
    assert resp.status_code == 403


async def test_cannot_create_owner_role(
    auth_client: tuple[AsyncClient, dict],  # type: ignore[type-arg]
) -> None:
    client, _ = auth_client
    resp = await client.post(
        "/api/v1/users",
        json={"email": "o2@example.com", "password": "password1234", "role": "owner"},
    )
    assert resp.status_code == 403


async def test_admin_cannot_create_admin(
    auth_client: tuple[AsyncClient, dict],  # type: ignore[type-arg]
    client: AsyncClient,
) -> None:
    owner_client, _ = auth_client
    resp = await owner_client.post(
        "/api/v1/users",
        json={"email": "adm@example.com", "password": "password1234", "role": "admin"},
    )
    assert resp.status_code == 201

    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "adm@example.com", "password": "password1234"},
    )
    admin_token = login.json()["access_token"]
    resp = await client.post(
        "/api/v1/users",
        json={"email": "a2@example.com", "password": "password1234", "role": "admin"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 403
