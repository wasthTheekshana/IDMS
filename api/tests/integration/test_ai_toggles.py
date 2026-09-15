import uuid
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import text

from app.core.db import SessionLocal
from app.models.chunk import DocumentChunk
from app.models.document import Document
from app.repositories.chunk import ChunkRepository


async def _disable(admin_client: AsyncClient, org_id: str, **flags: bool) -> None:
    resp = await admin_client.patch(
        f"/api/v1/platform-admin/organizations/{org_id}", json=flags
    )
    assert resp.status_code == 200, resp.text


async def _setup_doc_with_chunks(
    org_id: uuid.UUID, user_id: uuid.UUID, content: str
) -> uuid.UUID:
    """Same shape as tests/integration/test_ai.py's helper — an indexed
    document with extracted_text plus one embedded chunk."""
    doc_id = uuid.uuid4()
    async with SessionLocal.begin() as session:
        await session.execute(text(f"SET LOCAL app.current_org_id = '{org_id}'"))
        session.add(
            Document(
                id=doc_id,
                org_id=org_id,
                uploaded_by=user_id,
                filename="report.pdf",
                mime_type="application/pdf",
                size_bytes=2048,
                r2_key=f"orgs/{org_id}/docs/{doc_id}/report.pdf",
                status="indexed",
                extracted_text=content,
            )
        )
        await session.flush()
        await ChunkRepository(session).bulk_insert(
            [
                DocumentChunk(
                    id=uuid.uuid4(),
                    org_id=org_id,
                    document_id=doc_id,
                    page=1,
                    chunk_index=0,
                    content=content,
                    token_count=20,
                    embedding=[0.1] * 1024,
                )
            ]
        )
    return doc_id


@pytest.mark.asyncio
async def test_qa_disabled_short_circuits_without_calling_llm(
    platform_admin_client: tuple[AsyncClient, dict],  # type: ignore[type-arg]
    auth_client: tuple[AsyncClient, dict],  # type: ignore[type-arg]
) -> None:
    """The org's real GROQ_API_KEY is configured in api/.env, so this must
    mock _call_llm directly (the top-level dispatcher, provider-agnostic) —
    otherwise this test would make a real network call, same trap that
    tests/integration/test_ai.py works around by mocking the LLM call."""
    admin_client, _ = platform_admin_client
    client_a, _ = auth_client

    me = await client_a.get("/api/v1/users/me")
    org_id = me.json()["org_id"]
    await _disable(admin_client, org_id, ai_qa_enabled=False)

    with patch("app.services.ai._call_llm", new_callable=AsyncMock) as mock_call_llm:
        resp = await client_a.post(
            "/api/v1/ai/chat", json={"question": "What is in my documents?"}
        )

    assert resp.status_code == 200
    assert "disabled" in resp.json()["answer"].lower()
    mock_call_llm.assert_not_called()


@pytest.mark.asyncio
async def test_extraction_disabled_by_default_returns_403(
    auth_client: tuple[AsyncClient, dict],  # type: ignore[type-arg]
) -> None:
    """ai_extraction_enabled defaults to False for every new org."""
    client_a, _ = auth_client

    tmpl = await client_a.post(
        "/api/v1/templates",
        json={
            "name": "Invoice",
            "fields": [{"key": "total", "label": "Total", "type": "text"}],
        },
    )
    assert tmpl.status_code == 201, tmpl.text

    import uuid

    resp = await client_a.post(
        "/api/v1/templates/extract",
        json={
            "document_id": str(uuid.uuid4()),
            "template_id": tmpl.json()["id"],
        },
    )
    assert resp.status_code == 403
    assert "disabled" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_extraction_enabled_reaches_not_found_instead_of_disabled(
    platform_admin_client: tuple[AsyncClient, dict],  # type: ignore[type-arg]
    auth_client: tuple[AsyncClient, dict],  # type: ignore[type-arg]
) -> None:
    """Once enabled, a bad document_id now fails for the ORIGINAL reason
    (not found) rather than being blocked by the toggle — proves the toggle
    check runs, and runs before the not-found check would otherwise hide it."""
    admin_client, _ = platform_admin_client
    client_a, _ = auth_client

    me = await client_a.get("/api/v1/users/me")
    org_id = me.json()["org_id"]
    await _disable(admin_client, org_id, ai_extraction_enabled=True)

    tmpl = await client_a.post(
        "/api/v1/templates",
        json={
            "name": "Invoice",
            "fields": [{"key": "total", "label": "Total", "type": "text"}],
        },
    )

    import uuid

    resp = await client_a.post(
        "/api/v1/templates/extract",
        json={
            "document_id": str(uuid.uuid4()),
            "template_id": tmpl.json()["id"],
        },
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_summarization_disabled_short_circuits_without_calling_llm(
    platform_admin_client: tuple[AsyncClient, dict],  # type: ignore[type-arg]
    auth_client: tuple[AsyncClient, dict],  # type: ignore[type-arg]
) -> None:
    admin_client, _ = platform_admin_client
    client_a, _ = auth_client

    me = await client_a.get("/api/v1/users/me")
    org_id = uuid.UUID(me.json()["org_id"])
    user_id = uuid.UUID(me.json()["id"])
    await _disable(admin_client, str(org_id), ai_summarization_enabled=False)

    doc_id = await _setup_doc_with_chunks(
        org_id, user_id, "The company revenue was $5M in 2025."
    )

    with patch("app.services.ai._call_llm", new_callable=AsyncMock) as mock_call_llm:
        resp = await client_a.post(f"/api/v1/ai/documents/{doc_id}/summarize")

    assert resp.status_code == 200, resp.text
    assert "disabled" in resp.json()["summary"].lower()
    mock_call_llm.assert_not_called()


@pytest.mark.asyncio
async def test_search_answer_disabled_returns_hits_without_ai_summary(
    platform_admin_client: tuple[AsyncClient, dict],  # type: ignore[type-arg]
    auth_client: tuple[AsyncClient, dict],  # type: ignore[type-arg]
) -> None:
    """Only the AI answer is gated — the underlying search still runs."""
    admin_client, _ = platform_admin_client
    client_a, _ = auth_client

    me = await client_a.get("/api/v1/users/me")
    org_id = uuid.UUID(me.json()["org_id"])
    user_id = uuid.UUID(me.json()["id"])
    await _disable(admin_client, str(org_id), ai_search_answer_enabled=False)

    await _setup_doc_with_chunks(
        org_id, user_id, "The company revenue was $5M in 2025."
    )

    with patch("app.services.ai._call_llm", new_callable=AsyncMock) as mock_call_llm:
        resp = await client_a.get("/api/v1/search", params={"q": "revenue"})

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body.get("ai_summary") is None
    assert isinstance(body["hits"], list)
    mock_call_llm.assert_not_called()
