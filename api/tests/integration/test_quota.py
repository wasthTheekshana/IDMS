from httpx import AsyncClient
from sqlalchemy import text

from app.core.db import SessionLocal

_UPLOAD_BODY = {
    "filename": "test.pdf",
    "content_type": "application/pdf",
    "size_bytes": 100_000,
}


async def _exhaust_quota(org_slug_prefix: str = "") -> None:
    async with SessionLocal.begin() as session:
        await session.execute(
            text("UPDATE organizations SET pages_used_this_month = monthly_page_quota")
        )


async def test_upload_rejected_402_when_quota_exhausted(
    auth_client: tuple[AsyncClient, dict],  # type: ignore[type-arg]
) -> None:
    client, _ = auth_client
    await _exhaust_quota()
    resp = await client.post("/api/v1/documents/upload-url", json=_UPLOAD_BODY)
    assert resp.status_code == 402
    assert "quota" in resp.json()["detail"].lower()


async def test_upload_allowed_when_quota_available(
    auth_client: tuple[AsyncClient, dict],  # type: ignore[type-arg]
) -> None:
    client, _ = auth_client
    resp = await client.post("/api/v1/documents/upload-url", json=_UPLOAD_BODY)
    assert resp.status_code == 201
