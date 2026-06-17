# IDMS Phase 3: Semantic Search & Embeddings

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** After a document is OCR-processed, each text chunk is embedded with Mistral's embedding API and stored in pgvector. Users can search across their org's documents with hybrid retrieval (semantic cosine similarity + PostgreSQL full-text), returning ranked snippets with source page numbers.

**Architecture:** `run_ocr` enqueues `embed_document` on completion → Celery `embed` worker batches chunks → calls Mistral embeddings API → stores `(chunk_text, embedding, page, document_id)` in `document_chunks` → search endpoint queries with `<=>` cosine distance + `ts_rank` weighted sum → returns top-K hits with context window. Full-text uses `tsvector` generated column (auto-updated). Document status transitions: `ready → indexed`.

**Tech Stack:** pgvector 0.7+ · Mistral `mistral-embed` (1024-dim) · SQLAlchemy `pgvector` type · Celery `embed` queue · FastAPI · pytest with vector fixture data

---

> **Definition of Done:**
>
> - Chunks stored with embeddings after OCR completes (visible in DB)
> - `GET /search?q=...` returns hits ranked by hybrid score
> - Cross-org search returns 0 results (RLS enforced)
> - `embed_document` is idempotent — re-run does not duplicate chunks
> - Integration tests: happy path, empty result, cross-org isolation

---

## File Map

| File                                            | Action | Responsibility                                                   |
| ----------------------------------------------- | ------ | ---------------------------------------------------------------- |
| `infra/docker-compose.yml`                      | Modify | Use `pgvector/pgvector:pg16` image                               |
| `api/pyproject.toml`                            | Modify | Add `pgvector`, `numpy` deps                                     |
| `api/app/models/chunk.py`                       | Create | `DocumentChunk` model with `vector` column                       |
| `api/app/models/document.py`                    | Modify | Add `chunks` relationship (optional)                             |
| `api/app/schemas/search.py`                     | Create | `SearchRequest`, `SearchHit`, `SearchResponse`                   |
| `api/app/repositories/chunk.py`                 | Create | `ChunkRepository` (bulk insert, vector search, full-text search) |
| `api/app/services/embed.py`                     | Create | `EmbedProvider` Protocol + `MistralEmbed` + stub                 |
| `api/app/services/search.py`                    | Create | Hybrid search: semantic + BM25-like full-text, weighted merge    |
| `api/app/workers/tasks.py`                      | Modify | Add `embed_document` task; `run_ocr` enqueues it on success      |
| `api/app/api/v1/search.py`                      | Create | `GET /search` endpoint                                           |
| `api/app/main.py`                               | Modify | Register search router                                           |
| `api/migrations/versions/004_chunks_vectors.py` | Create | pgvector ext, `document_chunks` table + RLS + tsvector index     |
| `api/tests/integration/test_search.py`          | Create | Search happy path, empty result, cross-org isolation             |

---

### Task 1: Add pgvector to docker-compose and dependencies

- [ ] **Step 1: Update `infra/docker-compose.yml` postgres image**

Change:

```yaml
image: postgres:16-alpine
```

To:

```yaml
image: pgvector/pgvector:pg16
```

- [ ] **Step 2: Add deps to `api/pyproject.toml`**

```toml
"pgvector>=0.3.0",
"numpy>=1.26.0",
```

- [ ] **Step 3: Run `uv sync --all-extras`**

- [ ] **Step 4: Add embedding config to `api/app/core/config.py`**

```python
# Embeddings
EMBED_MODEL: str = "mistral-embed"
EMBED_DIM: int = 1024
EMBED_BATCH_SIZE: int = 32
```

- [ ] **Step 5: Commit**

---

### Task 2: DocumentChunk model

- [ ] **Step 1: Create `api/app/models/chunk.py`**

```python
import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True)
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("documents.id"), nullable=False, index=True)
    page: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, server_default="0")
    embedding: Mapped[list[float]] = mapped_column(Vector(1024), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```

- [ ] **Step 2: Commit**

---

### Task 3: Migration 004 — pgvector + document_chunks

- [ ] **Step 1: Create `api/migrations/versions/004_chunks_vectors.py`**

```python
"""pgvector extension + document_chunks table with RLS

Revision ID: 004
Revises: 003
Create Date: 2026-06-17
"""
from collections.abc import Sequence
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "004"
down_revision: str | None = "003"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "document_chunks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("page", sa.Integer, nullable=False),
        sa.Column("chunk_index", sa.Integer, nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("token_count", sa.Integer, server_default="0", nullable=False),
        sa.Column("embedding", sa.Text, nullable=True),  # stored as vector via pgvector
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    # Use raw SQL for vector type and tsvector generated column
    op.execute("ALTER TABLE document_chunks ALTER COLUMN embedding TYPE vector(1024) USING NULL")
    op.execute("""
        ALTER TABLE document_chunks
        ADD COLUMN content_tsv tsvector
            GENERATED ALWAYS AS (to_tsvector('english', content)) STORED
    """)

    op.create_index("ix_chunks_org_id", "document_chunks", ["org_id"])
    op.create_index("ix_chunks_document_id", "document_chunks", ["document_id"])
    op.execute("CREATE INDEX ix_chunks_embedding ON document_chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)")
    op.execute("CREATE INDEX ix_chunks_tsv ON document_chunks USING GIN (content_tsv)")

    op.execute("ALTER TABLE document_chunks ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE document_chunks FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY org_isolation ON document_chunks FOR ALL
          USING (org_id = current_setting('app.current_org_id', true)::uuid)
          WITH CHECK (org_id = current_setting('app.current_org_id', true)::uuid)
    """)


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS org_isolation ON document_chunks")
    op.execute("ALTER TABLE document_chunks DISABLE ROW LEVEL SECURITY")
    op.drop_table("document_chunks")
```

- [ ] **Step 2: Run `uv run alembic upgrade head`**

- [ ] **Step 3: Commit**

---

### Task 4: ChunkRepository

- [ ] **Step 1: Create `api/app/repositories/chunk.py`**

```python
import uuid
from typing import Sequence

from pgvector.sqlalchemy import Vector
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chunk import DocumentChunk


class ChunkRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def bulk_insert(self, chunks: list[DocumentChunk]) -> None:
        self._s.add_all(chunks)
        await self._s.flush()

    async def delete_for_document(self, document_id: uuid.UUID) -> None:
        from sqlalchemy import delete
        await self._s.execute(
            delete(DocumentChunk).where(DocumentChunk.document_id == document_id)
        )
        await self._s.flush()

    async def semantic_search(
        self, org_id: uuid.UUID, embedding: list[float], limit: int = 10
    ) -> list[DocumentChunk]:
        """Cosine similarity search via pgvector <=> operator."""
        result = await self._s.execute(
            select(DocumentChunk)
            .where(DocumentChunk.org_id == org_id)
            .where(DocumentChunk.embedding.isnot(None))
            .order_by(DocumentChunk.embedding.cosine_distance(embedding))
            .limit(limit)
        )
        return list(result.scalars().all())

    async def fulltext_search(
        self, org_id: uuid.UUID, query: str, limit: int = 10
    ) -> list[DocumentChunk]:
        """tsvector full-text search ranked by ts_rank."""
        result = await self._s.execute(
            text("""
                SELECT dc.*,
                       ts_rank(dc.content_tsv, plainto_tsquery('english', :q)) AS rank
                  FROM document_chunks dc
                 WHERE dc.org_id = :org_id
                   AND dc.content_tsv @@ plainto_tsquery('english', :q)
                 ORDER BY rank DESC
                 LIMIT :lim
            """),
            {"org_id": str(org_id), "q": query, "lim": limit},
        )
        rows = result.fetchall()
        # map back to ORM objects by loading by id
        if not rows:
            return []
        ids = [r[0] for r in rows]
        orm_result = await self._s.execute(
            select(DocumentChunk).where(DocumentChunk.id.in_(ids))
        )
        chunks = {c.id: c for c in orm_result.scalars().all()}
        return [chunks[i] for i in ids if i in chunks]
```

- [ ] **Step 2: Commit**

---

### Task 5: Embed service

- [ ] **Step 1: Create `api/app/services/embed.py`**

```python
"""Embedding provider protocol + Mistral implementation."""
import asyncio
from typing import Protocol, runtime_checkable

from app.core.config import settings


@runtime_checkable
class EmbedProvider(Protocol):
    async def embed_batch(self, texts: list[str]) -> list[list[float]]: ...


class MistralEmbed:
    """Embed texts with Mistral's mistral-embed model (1024-dim)."""

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        from mistralai import Mistral

        client = Mistral(api_key=settings.MISTRAL_API_KEY)
        response = await client.embeddings.create_async(
            model=settings.EMBED_MODEL,
            inputs=texts,
        )
        return [e.embedding for e in response.data]


class StubEmbed:
    """Fallback — returns zero vectors. Used when no API key configured."""

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [[0.0] * settings.EMBED_DIM for _ in texts]
```

- [ ] **Step 2: Commit**

---

### Task 6: Celery embed_document task

- [ ] **Step 1: Update `api/app/workers/tasks.py`**

Add `embed_document` task and update `run_ocr` to enqueue it on success.

In `_run_ocr_async`, after the `set_status(READY)` call, add:

```python
embed_document.apply_async(
    args=[str(doc_id), str(_org_id)],
    queue="embed",
    task_id=f"embed-{doc_id}",
)
```

New task:

```python
@celery_app.task(name="app.workers.tasks.embed_document", queue="embed", bind=True, max_retries=3)
def embed_document(self, document_id: str, org_id: str) -> dict:
    return asyncio.run(_embed_async(self, document_id, org_id))


async def _embed_async(task, document_id: str, org_id: str) -> dict:
    import uuid
    from sqlalchemy import text
    from app.core.config import settings
    from app.core.db import SessionLocal
    from app.models.chunk import DocumentChunk
    from app.models.document import DocumentStatus
    from app.repositories.chunk import ChunkRepository
    from app.repositories.document import DocumentRepository
    from app.services.embed import MistralEmbed, StubEmbed
    from app.services.ocr import chunk_markdown

    doc_id = uuid.UUID(document_id)
    _org_id = uuid.UUID(org_id)

    async with SessionLocal.begin() as session:
        await session.execute(text(f"SET LOCAL app.current_org_id = '{_org_id}'"))
        doc_repo = DocumentRepository(session)
        doc = await doc_repo.get_by_id(doc_id, org_id=_org_id)

        if not doc or not doc.extracted_text:
            return {"status": "no_text"}

        # Idempotency: INDEXED means already done
        if doc.status == DocumentStatus.INDEXED.value:
            return {"status": "already_indexed"}

        # Rechunk from stored text (idempotent)
        pages = doc.extracted_text.split("\n\n---PAGE---\n\n")
        chunks_data = chunk_markdown(pages)

        chunk_repo = ChunkRepository(session)
        # Delete existing chunks for this doc (idempotent re-run)
        await chunk_repo.delete_for_document(doc_id)

        # Embed in batches
        provider = MistralEmbed() if settings.MISTRAL_API_KEY else StubEmbed()
        texts = [c["content"] for c in chunks_data]
        batch_size = settings.EMBED_BATCH_SIZE

        all_embeddings: list[list[float]] = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            vecs = await provider.embed_batch(batch)
            all_embeddings.extend(vecs)

        orm_chunks = [
            DocumentChunk(
                id=uuid.uuid4(),
                org_id=_org_id,
                document_id=doc_id,
                page=int(cd["page"]),
                chunk_index=idx,
                content=str(cd["content"]),
                token_count=int(cd["token_count"]),
                embedding=emb,
            )
            for idx, (cd, emb) in enumerate(zip(chunks_data, all_embeddings))
        ]
        await chunk_repo.bulk_insert(orm_chunks)
        await doc_repo.set_status(doc_id, DocumentStatus.INDEXED)

    return {"status": "indexed", "chunk_count": len(orm_chunks)}
```

- [ ] **Step 2: Commit**

---

### Task 7: Search service + schemas

- [ ] **Step 1: Create `api/app/schemas/search.py`**

```python
import uuid
from pydantic import BaseModel


class SearchHit(BaseModel):
    document_id: uuid.UUID
    filename: str
    page: int
    content: str
    score: float


class SearchResponse(BaseModel):
    query: str
    hits: list[SearchHit]
    total: int
```

- [ ] **Step 2: Create `api/app/services/search.py`**

```python
"""Hybrid search: semantic (cosine) + full-text (tsvector), score-merged."""
import uuid
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.document import Document
from app.repositories.chunk import ChunkRepository
from app.schemas.search import SearchHit, SearchResponse
from app.services.embed import MistralEmbed, StubEmbed

_ALPHA = 0.7  # semantic weight; (1-_ALPHA) for full-text


async def hybrid_search(
    query: str,
    org_id: uuid.UUID,
    session: AsyncSession,
    limit: int = 10,
) -> SearchResponse:
    provider = MistralEmbed() if settings.MISTRAL_API_KEY else StubEmbed()
    embeddings = await provider.embed_batch([query])
    query_vec = embeddings[0]

    repo = ChunkRepository(session)
    semantic_hits = await repo.semantic_search(org_id, query_vec, limit=limit * 2)
    text_hits = await repo.fulltext_search(org_id, query, limit=limit * 2)

    # Merge by chunk id with normalised score
    scores: dict[uuid.UUID, float] = defaultdict(float)
    chunk_map = {}

    for rank, chunk in enumerate(semantic_hits):
        scores[chunk.id] += _ALPHA * (1.0 / (rank + 1))
        chunk_map[chunk.id] = chunk
    for rank, chunk in enumerate(text_hits):
        scores[chunk.id] += (1 - _ALPHA) * (1.0 / (rank + 1))
        chunk_map[chunk.id] = chunk

    ranked_ids = sorted(scores, key=lambda k: scores[k], reverse=True)[:limit]

    # Fetch document filenames
    doc_ids = {chunk_map[cid].document_id for cid in ranked_ids}
    doc_result = await session.execute(
        select(Document).where(Document.id.in_(doc_ids))
    )
    docs = {d.id: d for d in doc_result.scalars().all()}

    hits = []
    for cid in ranked_ids:
        chunk = chunk_map[cid]
        doc = docs.get(chunk.document_id)
        hits.append(
            SearchHit(
                document_id=chunk.document_id,
                filename=doc.filename if doc else "unknown",
                page=chunk.page,
                content=chunk.content,
                score=round(scores[cid], 4),
            )
        )

    return SearchResponse(query=query, hits=hits, total=len(hits))
```

- [ ] **Step 3: Commit**

---

### Task 8: Search API router

- [ ] **Step 1: Create `api/app/api/v1/search.py`**

```python
from fastapi import APIRouter, Query

from app.core.deps import AuthSession, CurrentUserDep
from app.schemas.search import SearchResponse
from app.services.search import hybrid_search

router = APIRouter(prefix="/search", tags=["search"])


@router.get("", response_model=SearchResponse)
async def search_documents(
    q: str = Query(..., min_length=1, max_length=500),
    limit: int = Query(default=10, ge=1, le=50),
    current_user: CurrentUserDep = ...,
    session: AuthSession = ...,
) -> SearchResponse:
    return await hybrid_search(q, current_user.org_id, session, limit=limit)
```

- [ ] **Step 2: Register in `api/app/main.py`**

- [ ] **Step 3: Commit**

---

### Task 9: Integration tests

- [ ] **Step 1: Create `api/tests/integration/test_search.py`**

Tests:

- `test_search_returns_empty_when_no_docs` — fresh org, `GET /search?q=anything` → `{"hits": [], "total": 0}`
- `test_search_finds_embedded_chunk` — insert chunk + embed directly via repo, search returns it
- `test_search_cross_org_returns_empty` — Org A's chunks not visible to Org B

- [ ] **Step 2: Run tests, fix failures**

- [ ] **Step 3: Commit**

---

### Task 10: Search UI

- [ ] **Step 1: Create `web/components/SearchBox.tsx`**

Input field → POST to `/api/v1/search` → render hits list with filename, page, excerpt, score.

- [ ] **Step 2: Add `SearchBox` to dashboard below upload zone**

- [ ] **Step 3: Commit**

---

## Self-Review

| Requirement                                        | Covered                           |
| -------------------------------------------------- | --------------------------------- |
| pgvector extension + document_chunks table + RLS   | Task 3                            |
| EmbedProvider protocol + MistralEmbed + StubEmbed  | Task 5                            |
| embed_document Celery task, idempotent             | Task 6                            |
| run_ocr enqueues embed on success                  | Task 6                            |
| Hybrid search: semantic + full-text weighted merge | Task 7                            |
| Search API GET /search                             | Task 8                            |
| Cross-org isolation: chunks RLS                    | Tasks 3, 9                        |
| Integration tests: happy path + cross-org          | Task 9                            |
| Search UI                                          | Task 10                           |
| ClamAV scan                                        | Deferred to Phase 5 (hardening)   |
| Reranking with LLM                                 | Deferred to Phase 4 (AI features) |
