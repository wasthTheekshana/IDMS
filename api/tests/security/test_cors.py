from httpx import AsyncClient


async def test_preflight_allows_configured_origin(client: AsyncClient) -> None:
    resp = await client.options(
        "/api/v1/auth/login",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert resp.status_code == 200
    assert resp.headers["access-control-allow-origin"] == "http://localhost:3000"


async def test_preflight_rejects_unknown_origin(client: AsyncClient) -> None:
    resp = await client.options(
        "/api/v1/auth/login",
        headers={
            "Origin": "https://evil.example.com",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert "access-control-allow-origin" not in resp.headers


async def test_preflight_rejects_disallowed_method(client: AsyncClient) -> None:
    resp = await client.options(
        "/api/v1/auth/login",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "TRACE",
        },
    )
    assert resp.status_code == 400
