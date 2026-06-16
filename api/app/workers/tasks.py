import asyncio
import logging

from celery import Task  # type: ignore[import-untyped]

from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(queue="default", name="app.workers.tasks.health_check")  # type: ignore[untyped-decorator]
def health_check() -> dict[str, str]:
    """Smoke-test task — verifies the worker is alive and processing."""
    return {"status": "ok"}


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
    """OCR pipeline: quota check → fetch R2 → OCR → chunk → mark ready."""
    return asyncio.run(_run_ocr_async(self, document_id, org_id))


async def _run_ocr_async(
    task: Task, document_id: str, org_id: str
) -> dict[str, object]:
    import uuid

    from sqlalchemy import text

    from app.core.config import settings
    from app.core.db import SessionLocal
    from app.models.document import DocumentStatus
    from app.repositories.document import DocumentRepository
    from app.repositories.organization import OrgRepository
    from app.services.ocr import MistralOcr, PaddleOcrStub, chunk_markdown
    from app.services.storage import get_object_bytes

    doc_id = uuid.UUID(document_id)
    _org_id = uuid.UUID(org_id)

    async with SessionLocal.begin() as session:
        await session.execute(text(f"SET LOCAL app.current_org_id = '{_org_id}'"))
        doc_repo = DocumentRepository(session)
        doc = await doc_repo.get_by_id(doc_id, org_id=_org_id)

        if not doc:
            logger.error("Document %s not found — dropping task", document_id)
            return {"status": "not_found"}

        # Idempotency: skip if already processed
        terminal = {
            DocumentStatus.OCR_DONE.value,
            DocumentStatus.INDEXED.value,
            DocumentStatus.READY.value,
        }
        if doc.status in terminal:
            logger.info("Document %s already processed, skipping", document_id)
            return {"status": "already_done"}

        # Atomic quota check + increment before paid work
        org_repo = OrgRepository(session)
        estimated_pages = max(1, doc.size_bytes // 50_000)
        if not await org_repo.check_and_increment_quota(_org_id, estimated_pages):
            await doc_repo.set_status(
                doc_id,
                DocumentStatus.FAILED,
                error_message="Monthly page quota exceeded",
            )
            return {"status": "quota_exceeded"}

        # Fetch file bytes from R2
        try:
            file_bytes = get_object_bytes(doc.r2_key)
        except Exception as exc:
            logger.exception("Failed to fetch %s from R2", doc.r2_key)
            return await _retry_or_fail(task, doc_repo, doc_id, exc, "R2 fetch failed")

        # Run OCR
        try:
            provider: MistralOcr | PaddleOcrStub = (
                MistralOcr() if settings.MISTRAL_API_KEY else PaddleOcrStub()
            )
            result = await provider.extract(file_bytes, doc.mime_type)
        except Exception as exc:
            logger.exception("OCR failed for document %s", document_id)
            return await _retry_or_fail(task, doc_repo, doc_id, exc, "OCR failed")

        chunks = chunk_markdown(result.pages)

        await doc_repo.set_status(
            doc_id,
            DocumentStatus.READY,
            page_count=result.page_count,
            extracted_text=result.text,
        )

        logger.info(
            "Document %s ready: %d pages, %d chunks",
            document_id,
            result.page_count,
            len(chunks),
        )
        return {
            "status": "ready",
            "page_count": result.page_count,
            "chunk_count": len(chunks),
        }


async def _retry_or_fail(
    task: Task,
    doc_repo: object,
    doc_id: object,
    exc: Exception,
    message: str,
) -> dict[str, object]:
    """Retry with exponential backoff; on final attempt mark document failed."""
    from app.models.document import DocumentStatus
    from app.repositories.document import DocumentRepository

    if task.request.retries < task.max_retries:
        countdown = 30 * (2**task.request.retries)
        raise task.retry(exc=exc, countdown=countdown)

    assert isinstance(doc_repo, DocumentRepository)
    assert isinstance(doc_id, __import__("uuid").UUID)
    await doc_repo.set_status(doc_id, DocumentStatus.FAILED, error_message=message)
    return {"status": "failed"}
