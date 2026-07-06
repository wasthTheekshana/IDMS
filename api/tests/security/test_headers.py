from httpx import AsyncClient


async def test_security_headers_on_api_response(client: AsyncClient) -> None:
    resp = await client.get("/healthz")
    assert resp.status_code == 200
    assert (
        resp.headers["Strict-Transport-Security"]
        == "max-age=63072000; includeSubDomains; preload"
    )
    assert resp.headers["X-Frame-Options"] == "DENY"
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.headers["Referrer-Policy"] == "no-referrer"
    assert (
        resp.headers["Content-Security-Policy"]
        == "default-src 'none'; frame-ancestors 'none'"
    )


async def test_docs_page_exempt_from_strict_csp(client: AsyncClient) -> None:
    """Swagger UI loads CDN assets; a default-src 'none' CSP would break it."""
    resp = await client.get("/api/docs")
    assert resp.status_code == 200
    assert "Content-Security-Policy" not in resp.headers
    # Non-CSP headers still apply everywhere.
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
