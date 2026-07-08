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


# ---- update user (role / deactivate) ----


async def _create_and_get_id(client: AsyncClient, payload: dict) -> str:  # type: ignore[type-arg]
    resp = await client.post("/api/v1/users", json=payload)
    assert resp.status_code == 201, resp.text
    return str(resp.json()["id"])


async def test_owner_deactivates_member_blocking_login(
    auth_client: tuple[AsyncClient, dict],  # type: ignore[type-arg]
) -> None:
    client, _ = auth_client
    user_id = await _create_and_get_id(client, _NEW_USER)

    resp = await client.patch(f"/api/v1/users/{user_id}", json={"is_active": False})
    assert resp.status_code == 200
    assert resp.json()["is_active"] is False

    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "member-1@example.com", "password": "memberpass123"},
    )
    assert login.status_code == 401


async def test_owner_promotes_member_to_admin(
    auth_client: tuple[AsyncClient, dict],  # type: ignore[type-arg]
) -> None:
    client, _ = auth_client
    user_id = await _create_and_get_id(client, _NEW_USER)
    resp = await client.patch(f"/api/v1/users/{user_id}", json={"role": "admin"})
    assert resp.status_code == 200
    assert resp.json()["role"] == "admin"


async def test_cannot_modify_owner(
    auth_client: tuple[AsyncClient, dict],  # type: ignore[type-arg]
) -> None:
    client, _ = auth_client
    me = await client.get("/api/v1/users/me")
    owner_id = me.json()["id"]
    resp = await client.patch(f"/api/v1/users/{owner_id}", json={"is_active": False})
    assert resp.status_code == 403


async def test_admin_cannot_modify_admin(
    auth_client: tuple[AsyncClient, dict],  # type: ignore[type-arg]
    client: AsyncClient,
) -> None:
    owner_client, _ = auth_client
    admin_a = {
        "email": "adm-a@example.com",
        "password": "password1234",
        "role": "admin",
    }
    admin_b = {
        "email": "adm-b@example.com",
        "password": "password1234",
        "role": "admin",
    }
    await _create_and_get_id(owner_client, admin_a)
    admin_b_id = await _create_and_get_id(owner_client, admin_b)

    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "adm-a@example.com", "password": "password1234"},
    )
    token = login.json()["access_token"]
    resp = await client.patch(
        f"/api/v1/users/{admin_b_id}",
        json={"is_active": False},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


async def test_cross_org_update_returns_404(
    auth_client: tuple[AsyncClient, dict],  # type: ignore[type-arg]
    second_auth_client: tuple[AsyncClient, dict],  # type: ignore[type-arg]
) -> None:
    client_a, _ = auth_client
    client_b, _ = second_auth_client
    me_b = await client_b.get("/api/v1/users/me")
    b_owner_id = me_b.json()["id"]
    resp = await client_a.patch(
        f"/api/v1/users/{b_owner_id}", json={"is_active": False}
    )
    assert resp.status_code == 404


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
