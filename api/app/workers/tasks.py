import asyncio
import logging

from celery import Task, chain  # type: ignore[import-untyped]

from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


def _load_models() -> None:
    """Import all models so SQLAlchemy metadata is complete."""
    from app.models.chunk import DocumentChunk  # noqa: F401
    from app.models.document import Document  # noqa: F401
    from app.models.organization import Organization  # noqa: F401
    from app.models.template import Extraction, ExtractionTemplate  # noqa: F401
    from app.models.user import User  # noqa: F401


# ---------------------------------------------------------------------------
# 1. Health check
# ---------------------------------------------------------------------------


@celery_app.task(queue="default", name="app.workers.tasks.health_check")  # type: ignore[untyped-decorator]
def health_check() -> dict[str, str]:
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# 2. OCR task — does OCR only, then chains embed via Celery chain
# ---------------------------------------------------------------------------


@celery_app.task(  # type: ignore[untyped-decorator]
    name="app.workers.tasks.run_ocr",
    queue="ocr",
    bind=True,
    max_retries=5,
    default_retry_delay=30,
    acks_late=True,
    reject_on_worker_lost=True,
)
def run_ocr(self: Task, document_id: str, org_id: str) -> dict[str, object]:
    """OCR phase: fetch R2 → OCR → save text → sets 'ready'."""
    return asyncio.run(_run_ocr_async(self, document_id, org_id))


# ---------------------------------------------------------------------------
# 3. Embed task — creates chunks with embeddings, sets 'indexed'
# ---------------------------------------------------------------------------


@celery_app.task(  # type: ignore[untyped-decorator]
    name="app.workers.tasks.embed_document",
    queue="embed",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    acks_late=True,
)
def embed_document(self: Task, document_id: str, org_id: str) -> dict[str, object]:
    """Embed all chunks for a document and mark it indexed."""
    return asyncio.run(_embed_async(self, document_id, org_id))


# ---------------------------------------------------------------------------
# 4. Self-healing beat task — finds stuck "ready" docs and re-dispatches embed
# ---------------------------------------------------------------------------


@celery_app.task(queue="default", name="app.workers.tasks.heal_stuck_documents")  # type: ignore[untyped-decorator]
def heal_stuck_documents() -> dict[str, object]:
    """Periodic: find docs stuck at 'ready' for >60s with no chunks, re-embed."""
    return asyncio.run(_heal_stuck())


async def _heal_stuck() -> dict[str, object]:
    from sqlalchemy import text

    from app.core.db import worker_session_factory

    _load_models()
    worker_session = worker_session_factory()

    async with worker_session.begin() as session:
        result = await session.execute(
            text(
                """
                SELECT d.id::text, d.org_id::text
                FROM documents d
                WHERE d.status = 'ready'
                  AND d.extracted_text IS NOT NULL
                  AND d.updated_at < NOW() - INTERVAL '60 seconds'
                  AND NOT EXISTS (
                      SELECT 1 FROM document_chunks dc
                      WHERE dc.document_id = d.id
                  )
                LIMIT 20
                """
            )
        )
        stuck = result.fetchall()

    if not stuck:
        return {"healed": 0}

    for doc_id, org_id in stuck:
        embed_document.apply_async(
            args=[doc_id, org_id],
            queue="embed",
        )
        logger.info("Healed stuck document %s — re-dispatched embed", doc_id[:8])

    return {"healed": len(stuck)}


# ---------------------------------------------------------------------------
# 5. Pipeline launcher — called from upload confirm
# ---------------------------------------------------------------------------


def launch_pipeline(document_id: str, org_id: str) -> None:
    """Launch OCR → Embed as a Celery chain. Atomic dispatch — both or neither."""
    pipeline = chain(
        run_ocr.s(document_id, org_id),
        embed_document.si(document_id, org_id),
    )
    pipeline.apply_async()


# ---------------------------------------------------------------------------
# Async implementations
# ---------------------------------------------------------------------------


async def _run_ocr_async(
    task: Task, document_id: str, org_id: str
) -> dict[str, object]:
    import uuid

    from sqlalchemy import text

    from app.core.config import settings
    from app.core.db import worker_session_factory
    from app.models.document import DocumentStatus
    from app.repositories.document import DocumentRepository
    from app.repositories.organization import OrgRepository
    from app.services.ocr import MistralOcr, PaddleOcrStub, chunk_markdown
    from app.services.storage import get_object_bytes

    _load_models()

    doc_id = uuid.UUID(document_id)
    _org_id = uuid.UUID(org_id)
    worker_session = worker_session_factory()

    async with worker_session.begin() as session:
        await session.execute(text(f"SET LOCAL app.current_org_id = '{_org_id}'"))
        doc_repo = DocumentRepository(session)
        doc = await doc_repo.get_by_id(doc_id, org_id=_org_id)

        if not doc:
            logger.error("Document %s not found", document_id)
            return {"status": "not_found"}

        terminal = {
            DocumentStatus.OCR_DONE.value,
            DocumentStatus.INDEXED.value,
            DocumentStatus.READY.value,
        }
        if doc.status in terminal:
            logger.info("Document %s already has OCR, skipping", document_id)
            return {"status": "already_done"}

        org_repo = OrgRepository(session)
        estimated_pages = max(1, doc.size_bytes // 50_000)
        if not await org_repo.check_and_increment_quota(_org_id, estimated_pages):
            await doc_repo.set_status(
                doc_id,
                DocumentStatus.FAILED,
                error_message="Monthly page quota exceeded",
            )
            return {"status": "quota_exceeded"}

        try:
            file_bytes = get_object_bytes(doc.r2_key)
        except Exception as exc:
            logger.exception("R2 fetch failed for %s", doc.r2_key)
            return await _retry_or_fail(task, doc_repo, doc_id, exc, "R2 fetch failed")

        try:
            provider: MistralOcr | PaddleOcrStub = (
                MistralOcr() if settings.MISTRAL_API_KEY else PaddleOcrStub()
            )
            result = await provider.extract(file_bytes, doc.mime_type)
        except Exception as exc:
            logger.exception("OCR failed for %s", document_id)
            return await _retry_or_fail(task, doc_repo, doc_id, exc, "OCR failed")

        chunks = chunk_markdown(result.pages)

        await doc_repo.set_status(
            doc_id,
            DocumentStatus.READY,
            page_count=result.page_count,
            extracted_text=result.text,
        )

        logger.info(
            "Document %s OCR done: %d pages, %d chunks",
            document_id,
            result.page_count,
            len(chunks),
        )

    return {
        "status": "ready",
        "page_count": result.page_count,
        "chunk_count": len(chunks),
    }


async def _embed_async(task: Task, document_id: str, org_id: str) -> dict[str, object]:
    import uuid

    from sqlalchemy import text

    from app.core.config import settings
    from app.core.db import worker_session_factory
    from app.models.chunk import DocumentChunk
    from app.models.document import DocumentStatus
    from app.repositories.chunk import ChunkRepository
    from app.repositories.document import DocumentRepository
    from app.services.embed import MistralEmbed, StubEmbed
    from app.services.ocr import chunk_markdown

    _load_models()

    doc_id = uuid.UUID(document_id)
    _org_id = uuid.UUID(org_id)
    worker_session = worker_session_factory()

    async with worker_session.begin() as session:
        await session.execute(text(f"SET LOCAL app.current_org_id = '{_org_id}'"))
        doc_repo = DocumentRepository(session)
        doc = await doc_repo.get_by_id(doc_id, org_id=_org_id)

        if not doc or not doc.extracted_text:
            logger.warning("Document %s has no text to embed", document_id)
            return {"status": "no_text"}

        if doc.status == DocumentStatus.INDEXED.value:
            logger.info("Document %s already indexed", document_id)
            return {"status": "already_indexed"}

        pages = doc.extracted_text.split("\n\n---PAGE---\n\n")
        chunks_data = chunk_markdown(pages)

        if not chunks_data:
            await doc_repo.set_status(doc_id, DocumentStatus.INDEXED)
            return {"status": "indexed", "chunk_count": 0}

        chunk_repo = ChunkRepository(session)
        await chunk_repo.delete_for_document(doc_id)

        provider: MistralEmbed | StubEmbed = (
            MistralEmbed() if settings.MISTRAL_API_KEY else StubEmbed()
        )
        texts = [str(c["content"]) for c in chunks_data]
        batch_size = settings.EMBED_BATCH_SIZE

        all_embeddings: list[list[float]] = []
        for i in range(0, len(texts), batch_size):
            try:
                vecs = await provider.embed_batch(texts[i : i + batch_size])
                all_embeddings.extend(vecs)
            except Exception as exc:
                logger.exception("Embed batch failed at offset %d", i)
                if task.request.retries < task.max_retries:
                    countdown = 60 * (2**task.request.retries)
                    raise task.retry(exc=exc, countdown=countdown)
                await doc_repo.set_status(
                    doc_id,
                    DocumentStatus.FAILED,
                    error_message="Embedding failed",
                )
                return {"status": "failed"}

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

        logger.info("Document %s indexed: %d chunks", document_id, len(orm_chunks))
        return {"status": "indexed", "chunk_count": len(orm_chunks)}


async def _retry_or_fail(
    task: Task,
    doc_repo: object,
    doc_id: object,
    exc: Exception,
    message: str,
) -> dict[str, object]:
    from app.models.document import DocumentStatus
    from app.repositories.document import DocumentRepository

    if task.request.retries < task.max_retries:
        countdown = 30 * (2**task.request.retries)
        raise task.retry(exc=exc, countdown=countdown)

    assert isinstance(doc_repo, DocumentRepository)
    assert isinstance(doc_id, __import__("uuid").UUID)
    await doc_repo.set_status(doc_id, DocumentStatus.FAILED, error_message=message)
    return {"status": "failed"}
