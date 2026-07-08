import uuid

from httpx import AsyncClient
from sqlalchemy import text

from app.core.db import SessionLocal
from app.models.organization import Organization
from app.repositories.organization import OrgRepository

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


async def _make_org_with_usage(used: int) -> uuid.UUID:
    async with SessionLocal.begin() as session:
        org = Organization(name="Trueup Org", slug=f"trueup-{uuid.uuid4().hex[:8]}")
        session.add(org)
        await session.flush()
        await session.execute(
            text("UPDATE organizations SET pages_used_this_month = :u WHERE id = :i"),
            {"u": used, "i": str(org.id)},
        )
        return org.id


async def _get_usage(org_id: uuid.UUID) -> int:
    async with SessionLocal() as session:
        org = await OrgRepository(session).get_by_id(org_id)
        assert org is not None
        return org.pages_used_this_month


async def test_adjust_usage_applies_delta() -> None:
    org_id = await _make_org_with_usage(10)
    async with SessionLocal.begin() as session:
        await OrgRepository(session).adjust_usage(org_id, -3)
    assert await _get_usage(org_id) == 7


async def test_adjust_usage_clamps_at_zero() -> None:
    org_id = await _make_org_with_usage(10)
    async with SessionLocal.begin() as session:
        await OrgRepository(session).adjust_usage(org_id, -100)
    assert await _get_usage(org_id) == 0


async def test_reset_monthly_usage_zeroes_all_orgs() -> None:
    import asyncio

    from app.workers.tasks import reset_monthly_usage

    org_a = await _make_org_with_usage(5)
    org_b = await _make_org_with_usage(9)

    result = await asyncio.to_thread(reset_monthly_usage.run)

    assert result["orgs_reset"] >= 2
    assert await _get_usage(org_a) == 0
    assert await _get_usage(org_b) == 0
