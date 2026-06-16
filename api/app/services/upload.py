"""Upload flow: init presigned URL, confirm after client upload."""

import uuid

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.document import DocumentStatus
from app.repositories.document import DocumentRepository
from app.schemas.document import (
    DocumentResponse,
    UploadConfirmRequest,
    UploadInitRequest,
    UploadInitResponse,
)
from app.services import storage

_ALLOWED = set(settings.ALLOWED_MIME_TYPES)


async def init_upload(
    body: UploadInitRequest,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    session: AsyncSession,
) -> UploadInitResponse:
    if body.content_type not in _ALLOWED:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported type: {body.content_type}",
        )
    if body.size_bytes > settings.MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File exceeds 50 MB limit",
        )

    doc_id = uuid.uuid4()
    r2_key = storage.make_r2_key(org_id, doc_id, body.filename)
    upload_url = storage.presign_upload(r2_key, body.content_type)

    repo = DocumentRepository(session)
    doc = await repo.create(
        org_id=org_id,
        uploaded_by=user_id,
        filename=body.filename,
        mime_type=body.content_type,
        size_bytes=body.size_bytes,
        r2_key=r2_key,
    )

    return UploadInitResponse(
        document_id=doc.id,
        upload_url=upload_url,
        r2_key=r2_key,
    )


async def confirm_upload(
    body: UploadConfirmRequest,
    org_id: uuid.UUID,
    session: AsyncSession,
) -> DocumentResponse:
    from app.workers.tasks import run_ocr

    repo = DocumentRepository(session)
    doc = await repo.get_by_id(body.document_id, org_id=org_id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Document not found"
        )
    if doc.status != DocumentStatus.UPLOADED.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Document is already {doc.status}",
        )

    await repo.set_status(doc.id, DocumentStatus.PROCESSING)

    run_ocr.apply_async(
        args=[str(doc.id), str(org_id)],
        queue="ocr",
        task_id=f"ocr-{doc.id}",
    )

    # Re-fetch after Core UPDATE so all server-generated columns (updated_at) are fresh
    refreshed = await repo.get_by_id(doc.id, org_id=org_id)
    assert refreshed is not None
    return DocumentResponse.model_validate(refreshed)
