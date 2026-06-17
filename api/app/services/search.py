"""Hybrid search: semantic cosine + full-text tsvector, RRF-merged."""

import uuid
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.document import Document
from app.repositories.chunk import ChunkRepository
from app.schemas.search import SearchHit, SearchResponse
from app.services.embed import MistralEmbed, StubEmbed

_ALPHA = 0.7  # weight for semantic; (1-_ALPHA) for full-text


async def hybrid_search(
    query: str,
    org_id: uuid.UUID,
    session: AsyncSession,
    limit: int = 10,
) -> SearchResponse:
    provider: MistralEmbed | StubEmbed = (
        MistralEmbed() if settings.MISTRAL_API_KEY else StubEmbed()
    )
    embeddings = await provider.embed_batch([query])
    query_vec = embeddings[0]

    repo = ChunkRepository(session)
    semantic_hits = await repo.semantic_search(org_id, query_vec, limit=limit * 2)
    text_hits = await repo.fulltext_search(org_id, query, limit=limit * 2)

    # Reciprocal Rank Fusion weighted by _ALPHA
    scores: dict[uuid.UUID, float] = defaultdict(float)
    chunk_map: dict[uuid.UUID, object] = {}

    for rank, chunk in enumerate(semantic_hits):
        scores[chunk.id] += _ALPHA * (1.0 / (rank + 1))
        chunk_map[chunk.id] = chunk
    for rank, chunk in enumerate(text_hits):
        scores[chunk.id] += (1.0 - _ALPHA) * (1.0 / (rank + 1))
        chunk_map[chunk.id] = chunk

    ranked_ids = sorted(scores, key=lambda k: scores[k], reverse=True)[:limit]

    if not ranked_ids:
        return SearchResponse(query=query, hits=[], total=0)

    doc_ids = {chunk_map[cid].document_id for cid in ranked_ids}  # type: ignore[attr-defined]
    doc_result = await session.execute(select(Document).where(Document.id.in_(doc_ids)))
    docs = {d.id: d for d in doc_result.scalars().all()}

    hits = []
    for cid in ranked_ids:
        chunk = chunk_map[cid]  # type: ignore[assignment]
        doc = docs.get(chunk.document_id)  # type: ignore[attr-defined]
        hits.append(
            SearchHit(
                document_id=chunk.document_id,  # type: ignore[attr-defined]
                filename=doc.filename if doc else "unknown",
                page=chunk.page,  # type: ignore[attr-defined]
                content=chunk.content,  # type: ignore[attr-defined]
                score=round(scores[cid], 4),
            )
        )

    return SearchResponse(query=query, hits=hits, total=len(hits))
