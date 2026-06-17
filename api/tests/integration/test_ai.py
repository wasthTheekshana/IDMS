"""AI feature integration tests.

Gemini and embedding calls are mocked.
"""

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.core.db import SessionLocal
from app.main import app
from app.models.chunk import DocumentChunk
from app.models.document import Document
from app.repositories.chunk import ChunkRepository


async def _register(client: AsyncClient, suffix: str) -> tuple[str, str]:
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "org_name": f"AI Org {suffix}",
            "email": f"ai{suffix}@test.com",
            "password": "aipass12345",
        },
    )
    assert resp.status_code == 201, resp.text
    token = resp.json()["access_token"]
    client.headers["Authorization"] = f"Bearer {token}"
    me = await client.get("/api/v1/users/me")
    return token, me.json()["org_id"]


async def _setup_doc_with_chunks(
    org_id: uuid.UUID, user_id: uuid.UUID, content: str
) -> uuid.UUID:
    doc_id = uuid.uuid4()
    async with SessionLocal.begin() as session:
        await session.execute(text(f"SET LOCAL app.current_org_id = '{org_id}'"))
        doc = Document(
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
        session.add(doc)
        await session.flush()
        chunk = DocumentChunk(
            id=uuid.uuid4(),
            org_id=org_id,
            document_id=doc_id,
            page=1,
            chunk_index=0,
            content=content,
            token_count=20,
            embedding=[0.1] * 1024,
        )
        repo = ChunkRepository(session)
        await repo.bulk_insert([chunk])
    return doc_id


@pytest.mark.asyncio
async def test_ask_document_returns_answer(client: AsyncClient) -> None:
    _, org_id = await _register(client, "ask")
    me = await client.get("/api/v1/users/me")
    user_id = uuid.UUID(me.json()["id"])
    _org = uuid.UUID(org_id)

    doc_id = await _setup_doc_with_chunks(
        _org, user_id, "The company revenue was $5M in 2025."
    )

    with (
        patch(
            "app.services.ai.MistralEmbed.embed_batch",
            new_callable=AsyncMock,
            return_value=[[0.1] * 1024],
        ),
        patch(
            "app.services.ai._call_gemini",
            new_callable=AsyncMock,
            return_value="The revenue was $5M in 2025.",
        ),
    ):
        resp = await client.post(
            f"/api/v1/ai/documents/{doc_id}/ask",
            json={"question": "What was the revenue?"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert "answer" in data
    assert "$5M" in data["answer"]
    assert len(data["sources"]) >= 1


@pytest.mark.asyncio
async def test_summarize_document(client: AsyncClient) -> None:
    _, org_id = await _register(client, "sum")
    me = await client.get("/api/v1/users/me")
    user_id = uuid.UUID(me.json()["id"])
    _org = uuid.UUID(org_id)

    doc_id = await _setup_doc_with_chunks(
        _org, user_id, "This report covers Q1 2025 financials."
    )

    with patch(
        "app.services.ai._call_gemini",
        new_callable=AsyncMock,
        return_value="Q1 2025 financial report summary.",
    ):
        resp = await client.post(
            f"/api/v1/ai/documents/{doc_id}/summarize",
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["document_id"] == str(doc_id)
    assert "Q1" in data["summary"]


@pytest.mark.asyncio
async def test_chat_across_org(client: AsyncClient) -> None:
    _, org_id = await _register(client, "chat")
    me = await client.get("/api/v1/users/me")
    user_id = uuid.UUID(me.json()["id"])
    _org = uuid.UUID(org_id)

    await _setup_doc_with_chunks(
        _org, user_id, "Project Alpha is scheduled for Q3 2025."
    )

    with (
        patch(
            "app.services.ai.MistralEmbed.embed_batch",
            new_callable=AsyncMock,
            return_value=[[0.1] * 1024],
        ),
        patch(
            "app.services.ai._call_gemini",
            new_callable=AsyncMock,
            return_value="Project Alpha is in Q3 2025.",
        ),
    ):
        resp = await client.post(
            "/api/v1/ai/chat",
            json={"question": "When is Project Alpha?"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert "Alpha" in data["answer"]


@pytest.mark.asyncio
async def test_ask_cross_org_returns_404(client: AsyncClient) -> None:
    """Org B cannot ask questions about Org A's document."""
    _, org_id_a = await _register(client, "xorg_a")
    me = await client.get("/api/v1/users/me")
    user_id_a = uuid.UUID(me.json()["id"])
    _org_a = uuid.UUID(org_id_a)

    doc_id = await _setup_doc_with_chunks(_org_a, user_id_a, "Secret data")

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client_b:
        await _register(client_b, "xorg_b")
        resp = await client_b.post(
            f"/api/v1/ai/documents/{doc_id}/ask",
            json={"question": "What is the secret?"},
        )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_ai_requires_auth(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/ai/chat",
        json={"question": "test"},
    )
    assert resp.status_code in (401, 403)
