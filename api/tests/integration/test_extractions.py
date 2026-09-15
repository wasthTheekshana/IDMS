import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import text

from app.core.db import SessionLocal
from app.models.document import Document
from app.models.template import Extraction, ExtractionTemplate


async def _setup_extraction(org_id: uuid.UUID, user_id: uuid.UUID) -> uuid.UUID:
    doc_id = uuid.uuid4()
    tmpl_id = uuid.uuid4()
    ext_id = uuid.uuid4()
    async with SessionLocal.begin() as session:
        await session.execute(text(f"SET LOCAL app.current_org_id = '{org_id}'"))
        session.add(
            Document(
                id=doc_id,
                org_id=org_id,
                uploaded_by=user_id,
                filename="invoice.pdf",
                mime_type="application/pdf",
                size_bytes=1024,
                r2_key=f"orgs/{org_id}/docs/{doc_id}/invoice.pdf",
                status="indexed",
                extracted_text="Total: $100",
            )
        )
        session.add(
            ExtractionTemplate(
                id=tmpl_id,
                org_id=org_id,
                name="Invoice",
                fields=[{"key": "total", "label": "Total", "type": "text"}],
            )
        )
        await session.flush()
        session.add(
            Extraction(
                id=ext_id,
                org_id=org_id,
                document_id=doc_id,
                template_id=tmpl_id,
                data={"total": "$100"},
            )
        )
    return ext_id


@pytest.mark.asyncio
async def test_list_extractions_includes_id(
    auth_client: tuple[AsyncClient, dict],  # type: ignore[type-arg]
) -> None:
    client, _ = auth_client
    me = await client.get("/api/v1/users/me")
    org_id = uuid.UUID(me.json()["org_id"])
    user_id = uuid.UUID(me.json()["id"])
    ext_id = await _setup_extraction(org_id, user_id)

    resp = await client.get("/api/v1/templates/extractions")
    assert resp.status_code == 200, resp.text
    rows = resp.json()
    assert len(rows) == 1
    assert rows[0]["id"] == str(ext_id)


@pytest.mark.asyncio
async def test_delete_extraction_removes_it(
    auth_client: tuple[AsyncClient, dict],  # type: ignore[type-arg]
) -> None:
    client, _ = auth_client
    me = await client.get("/api/v1/users/me")
    org_id = uuid.UUID(me.json()["org_id"])
    user_id = uuid.UUID(me.json()["id"])
    ext_id = await _setup_extraction(org_id, user_id)

    resp = await client.delete(f"/api/v1/templates/extractions/{ext_id}")
    assert resp.status_code == 204, resp.text

    listed = await client.get("/api/v1/templates/extractions")
    assert listed.json() == []


@pytest.mark.asyncio
async def test_delete_unknown_extraction_returns_404(
    auth_client: tuple[AsyncClient, dict],  # type: ignore[type-arg]
) -> None:
    client, _ = auth_client
    resp = await client.delete(f"/api/v1/templates/extractions/{uuid.uuid4()}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_cannot_delete_another_orgs_extraction(
    auth_client: tuple[AsyncClient, dict],  # type: ignore[type-arg]
    second_auth_client: tuple[AsyncClient, dict],  # type: ignore[type-arg]
) -> None:
    client_a, _ = auth_client
    client_b, _ = second_auth_client

    me_a = await client_a.get("/api/v1/users/me")
    org_a_id = uuid.UUID(me_a.json()["org_id"])
    user_a_id = uuid.UUID(me_a.json()["id"])
    ext_id = await _setup_extraction(org_a_id, user_a_id)

    resp = await client_b.delete(f"/api/v1/templates/extractions/{ext_id}")
    assert resp.status_code == 404

    still_there = await client_a.get("/api/v1/templates/extractions")
    assert len(still_there.json()) == 1
