import uuid
from collections.abc import Sequence

from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chunk import DocumentChunk


class ChunkRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def bulk_insert(self, chunks: list[DocumentChunk]) -> None:
        self._s.add_all(chunks)
        await self._s.flush()

    async def delete_for_document(self, document_id: uuid.UUID) -> None:
        await self._s.execute(
            delete(DocumentChunk).where(DocumentChunk.document_id == document_id)
        )
        await self._s.flush()

    async def delete_for_documents(self, doc_ids: list[uuid.UUID]) -> None:
        await self._s.execute(
            delete(DocumentChunk).where(DocumentChunk.document_id.in_(doc_ids))
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
    ) -> Sequence[DocumentChunk]:
        """tsvector full-text search ranked by ts_rank."""
        result = await self._s.execute(
            text(
                """
                SELECT dc.id
                  FROM document_chunks dc
                 WHERE dc.org_id = CAST(:org_id AS uuid)
                   AND dc.content_tsv @@ plainto_tsquery('english', :q)
                 ORDER BY ts_rank(dc.content_tsv, plainto_tsquery('english', :q)) DESC
                 LIMIT :lim
                """
            ),
            {"org_id": str(org_id), "q": query, "lim": limit},
        )
        ids = [row[0] for row in result.fetchall()]
        if not ids:
            return []
        orm_result = await self._s.execute(
            select(DocumentChunk).where(DocumentChunk.id.in_(ids))
        )
        chunks_by_id = {c.id: c for c in orm_result.scalars().all()}
        return [chunks_by_id[i] for i in ids if i in chunks_by_id]
