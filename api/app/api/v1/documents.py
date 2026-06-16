import asyncio
import json
import uuid

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse

from app.core.deps import AuthSession, CurrentUserDep
from app.repositories.document import DocumentRepository
from app.schemas.document import (
    DocumentResponse,
    UploadConfirmRequest,
    UploadInitRequest,
    UploadInitResponse,
)
from app.services import upload as upload_service

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("/upload-url", response_model=UploadInitResponse, status_code=201)
async def init_upload(
    body: UploadInitRequest,
    current_user: CurrentUserDep,
    session: AuthSession,
) -> UploadInitResponse:
    return await upload_service.init_upload(
        body, current_user.org_id, current_user.user_id, session
    )


@router.post("/confirm", response_model=DocumentResponse)
async def confirm_upload(
    body: UploadConfirmRequest,
    current_user: CurrentUserDep,
    session: AuthSession,
) -> DocumentResponse:
    return await upload_service.confirm_upload(body, current_user.org_id, session)


@router.get("", response_model=list[DocumentResponse])
async def list_documents(
    current_user: CurrentUserDep,
    session: AuthSession,
) -> list[DocumentResponse]:
    repo = DocumentRepository(session)
    docs = await repo.list_for_org(current_user.org_id)
    return [DocumentResponse.model_validate(d) for d in docs]


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: uuid.UUID,
    current_user: CurrentUserDep,
    session: AuthSession,
) -> DocumentResponse:
    repo = DocumentRepository(session)
    doc = await repo.get_by_id(document_id, org_id=current_user.org_id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Document not found"
        )
    return DocumentResponse.model_validate(doc)


@router.get("/{document_id}/status")
async def stream_document_status(
    document_id: uuid.UUID,
    current_user: CurrentUserDep,
    session: AuthSession,
) -> StreamingResponse:
    """SSE: poll document status every 2 s until terminal state."""
    org_id = current_user.org_id

    async def event_generator():  # type: ignore[no-untyped-def]
        from sqlalchemy import text

        from app.core.db import SessionLocal
        from app.models.document import DocumentStatus

        terminal = {
            DocumentStatus.READY.value,
            DocumentStatus.FAILED.value,
            DocumentStatus.INDEXED.value,
        }

        for _ in range(150):  # max ~5 minutes
            async with SessionLocal.begin() as poll_session:
                await poll_session.execute(
                    text(f"SET LOCAL app.current_org_id = '{org_id}'")
                )
                repo = DocumentRepository(poll_session)
                doc = await repo.get_by_id(document_id, org_id=org_id)

            if not doc:
                yield f"data: {json.dumps({'error': 'not_found'})}\n\n"
                return

            payload = json.dumps(
                {
                    "document_id": str(doc.id),
                    "status": doc.status,
                    "page_count": doc.page_count,
                    "error_message": doc.error_message,
                }
            )
            yield f"data: {payload}\n\n"

            if doc.status in terminal:
                return

            await asyncio.sleep(2.0)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
