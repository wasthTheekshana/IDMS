"""Search integration tests.

Chunks and embeddings are inserted directly via repository.
No real OCR/embed API calls are made.
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
    """Register a new org, return (access_token, org_id)."""
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "org_name": f"Search Org {suffix}",
            "email": f"searcher{suffix}@test.com",
            "password": "searchpass123",
        },
    )
    assert resp.status_code == 201, resp.text
    token = resp.json()["access_token"]
    client.headers["Authorization"] = f"Bearer {token}"

    me = await client.get("/api/v1/users/me")
    org_id = me.json()["org_id"]
    return token, org_id


async def _insert_chunk(org_id: uuid.UUID, doc_id: uuid.UUID, content: str) -> None:
    """Directly insert a chunk with a zero-vector embedding (bypasses Celery)."""
    chunk = DocumentChunk(
        id=uuid.uuid4(),
        org_id=org_id,
        document_id=doc_id,
        page=1,
        chunk_index=0,
        content=content,
        token_count=10,
        embedding=[0.1] * 1024,
    )
    async with SessionLocal.begin() as session:
        await session.execute(text(f"SET LOCAL app.current_org_id = '{org_id}'"))
        repo = ChunkRepository(session)
        await repo.bulk_insert([chunk])


async def _insert_document(org_id: uuid.UUID, user_id: uuid.UUID) -> uuid.UUID:
    doc_id = uuid.uuid4()
    async with SessionLocal.begin() as session:
        await session.execute(text(f"SET LOCAL app.current_org_id = '{org_id}'"))
        doc = Document(
            id=doc_id,
            org_id=org_id,
            uploaded_by=user_id,
            filename="test.pdf",
            mime_type="application/pdf",
            size_bytes=1024,
            r2_key=f"orgs/{org_id}/docs/{doc_id}/test.pdf",
            status="ready",
        )
        session.add(doc)
        await session.flush()
    return doc_id


@pytest.mark.asyncio
async def test_search_returns_empty_when_no_chunks(client: AsyncClient) -> None:
    _, _ = await _register(client, "empty")

    # Mock embed so no real API call
    with patch(
        "app.services.search.MistralEmbed.embed_batch",
        new_callable=AsyncMock,
        return_value=[[0.0] * 1024],
    ):
        resp = await client.get("/api/v1/search?q=anything")

    assert resp.status_code == 200
    data = resp.json()
    assert data["hits"] == []
    assert data["total"] == 0
    assert data["query"] == "anything"


@pytest.mark.asyncio
async def test_search_finds_chunk_by_fulltext(client: AsyncClient) -> None:
    _, org_id = await _register(client, "fulltext")

    # Get user id
    me = await client.get("/api/v1/users/me")
    user_id = uuid.UUID(me.json()["id"])
    _org_id = uuid.UUID(org_id)

    doc_id = await _insert_document(_org_id, user_id)
    await _insert_chunk(
        _org_id,
        doc_id,
        "The quick brown fox jumps over the lazy dog",
    )

    with patch(
        "app.services.search.MistralEmbed.embed_batch",
        new_callable=AsyncMock,
        return_value=[[0.1] * 1024],
    ):
        resp = await client.get("/api/v1/search?q=quick+brown+fox")

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
    assert any("fox" in hit["content"] for hit in data["hits"])


@pytest.mark.asyncio
async def test_search_cross_org_returns_no_results(client: AsyncClient) -> None:
    """Org B's search must not surface Org A's chunks."""
    _, org_id_a = await _register(client, "corg_a")
    me = await client.get("/api/v1/users/me")
    user_id_a = uuid.UUID(me.json()["id"])
    _org_a = uuid.UUID(org_id_a)

    doc_id = await _insert_document(_org_a, user_id_a)
    await _insert_chunk(_org_a, doc_id, "confidential data belongs to org A")

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client_b:
        _, _ = await _register(client_b, "corg_b")
        with patch(
            "app.services.search.MistralEmbed.embed_batch",
            new_callable=AsyncMock,
            return_value=[[0.1] * 1024],
        ):
            resp = await client_b.get("/api/v1/search?q=confidential")

    assert resp.status_code == 200
    assert resp.json()["total"] == 0, "Cross-org chunk leak detected"


@pytest.mark.asyncio
async def test_search_requires_auth(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/search?q=test")
    assert resp.status_code in (401, 403)
