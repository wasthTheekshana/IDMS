import uuid
from unittest.mock import AsyncMock, patch

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


@pytest.mark.asyncio
async def test_label_echo_on_first_attempt_is_recovered_by_retry(
    platform_admin_client: tuple[AsyncClient, dict],  # type: ignore[type-arg]
    auth_client: tuple[AsyncClient, dict],  # type: ignore[type-arg]
) -> None:
    """If the first LLM call echoes a field's own label back (the known
    failure mode), a second attempt at the same prompt should recover the
    real value rather than leaving the field blank."""
    admin_client, _ = platform_admin_client
    client, _ = auth_client

    me = await client.get("/api/v1/users/me")
    org_id = me.json()["org_id"]
    await admin_client.patch(
        f"/api/v1/platform-admin/organizations/{org_id}",
        json={"ai_extraction_enabled": True},
    )

    doc_id = uuid.uuid4()
    tmpl_id = uuid.uuid4()
    async with SessionLocal.begin() as session:
        await session.execute(text(f"SET LOCAL app.current_org_id = '{org_id}'"))
        session.add(
            Document(
                id=doc_id,
                org_id=uuid.UUID(org_id),
                uploaded_by=uuid.UUID(me.json()["id"]),
                filename="pod.pdf",
                mime_type="application/pdf",
                size_bytes=512,
                r2_key=f"orgs/{org_id}/docs/{doc_id}/pod.pdf",
                status="indexed",
                extracted_text="PROOF OF DELIVERY NOTE\n\n1225650",
            )
        )
        session.add(
            ExtractionTemplate(
                id=tmpl_id,
                org_id=uuid.UUID(org_id),
                name="POD",
                fields=[
                    {
                        "key": "proof_of_delivery_note",
                        "label": "PROOF OF DELIVERY NOTE",
                        "type": "text",
                    }
                ],
            )
        )

    with patch(
        "app.services.extraction._call_llm",
        new_callable=AsyncMock,
        side_effect=[
            '{"proof_of_delivery_note": "PROOF OF DELIVERY NOTE"}',
            '{"proof_of_delivery_note": "1225650"}',
        ],
    ) as mock_call_llm:
        resp = await client.post(
            "/api/v1/templates/extract",
            json={"document_id": str(doc_id), "template_id": str(tmpl_id)},
        )

    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["proof_of_delivery_note"] == "1225650"
    assert mock_call_llm.call_count == 2


@pytest.mark.asyncio
async def test_repeated_label_echo_leaves_field_null_not_wrong(
    platform_admin_client: tuple[AsyncClient, dict],  # type: ignore[type-arg]
    auth_client: tuple[AsyncClient, dict],  # type: ignore[type-arg]
) -> None:
    """If the retry ALSO echoes the label, the field ends up null (honest
    "not found") rather than the wrong label text landing in the data."""
    admin_client, _ = platform_admin_client
    client, _ = auth_client

    me = await client.get("/api/v1/users/me")
    org_id = me.json()["org_id"]
    await admin_client.patch(
        f"/api/v1/platform-admin/organizations/{org_id}",
        json={"ai_extraction_enabled": True},
    )

    doc_id = uuid.uuid4()
    tmpl_id = uuid.uuid4()
    async with SessionLocal.begin() as session:
        await session.execute(text(f"SET LOCAL app.current_org_id = '{org_id}'"))
        session.add(
            Document(
                id=doc_id,
                org_id=uuid.UUID(org_id),
                uploaded_by=uuid.UUID(me.json()["id"]),
                filename="pod.pdf",
                mime_type="application/pdf",
                size_bytes=512,
                r2_key=f"orgs/{org_id}/docs/{doc_id}/pod.pdf",
                status="indexed",
                extracted_text="PROOF OF DELIVERY NOTE\n\n1225650",
            )
        )
        session.add(
            ExtractionTemplate(
                id=tmpl_id,
                org_id=uuid.UUID(org_id),
                name="POD",
                fields=[
                    {
                        "key": "proof_of_delivery_note",
                        "label": "PROOF OF DELIVERY NOTE",
                        "type": "text",
                    }
                ],
            )
        )

    with patch(
        "app.services.extraction._call_llm",
        new_callable=AsyncMock,
        return_value='{"proof_of_delivery_note": "PROOF OF DELIVERY NOTE"}',
    ) as mock_call_llm:
        resp = await client.post(
            "/api/v1/templates/extract",
            json={"document_id": str(doc_id), "template_id": str(tmpl_id)},
        )

    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["proof_of_delivery_note"] is None
    assert mock_call_llm.call_count == 2
