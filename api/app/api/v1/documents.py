import asyncio
import json
import logging
import uuid

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse

from app.core.deps import AuthSession, CurrentUserDep
from app.repositories.chunk import ChunkRepository
from app.repositories.document import DocumentRepository
from app.schemas.document import (
    BulkDeleteResponse,
    BulkDocumentRequest,
    CompareDoc,
    CompareRequest,
    CompareResponse,
    DocumentDetailResponse,
    DocumentResponse,
    PreviewUrlResponse,
    UploadConfirmRequest,
    UploadInitRequest,
    UploadInitResponse,
)
from app.services import storage
from app.services import upload as upload_service

logger = logging.getLogger(__name__)

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


@router.get("/{document_id}", response_model=DocumentDetailResponse)
async def get_document(
    document_id: uuid.UUID,
    current_user: CurrentUserDep,
    session: AuthSession,
) -> DocumentDetailResponse:
    repo = DocumentRepository(session)
    doc = await repo.get_by_id(document_id, org_id=current_user.org_id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Document not found"
        )
    detail = DocumentDetailResponse.model_validate(doc)
    try:
        detail.preview_url = storage.presign_download(doc.r2_key)
    except Exception:
        detail.preview_url = None
    return detail


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


# ---------------------------------------------------------------------------
# Preview
# ---------------------------------------------------------------------------

_TIFF_TYPES = {"image/tiff", "image/x-tiff"}
_DOCX_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


@router.get("/{document_id}/preview-url", response_model=PreviewUrlResponse)
async def get_preview_url(
    document_id: uuid.UUID,
    current_user: CurrentUserDep,
    session: AuthSession,
) -> PreviewUrlResponse:
    repo = DocumentRepository(session)
    doc = await repo.get_by_id(document_id, org_id=current_user.org_id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Document not found"
        )

    mime = doc.mime_type.lower()

    if mime in _TIFF_TYPES:
        preview_url = f"/api/v1/documents/{document_id}/preview-tiff"
        return PreviewUrlResponse(preview_url=preview_url, content_type="image/png")

    if mime == _DOCX_TYPE:
        return PreviewUrlResponse(preview_url=None, content_type=_DOCX_TYPE)

    # PDF, JPEG, PNG — presigned R2 URL
    url = storage.presign_download(doc.r2_key)
    return PreviewUrlResponse(preview_url=url, content_type=mime)


@router.get("/{document_id}/preview-tiff")
async def preview_tiff(
    document_id: uuid.UUID,
    current_user: CurrentUserDep,
    session: AuthSession,
) -> StreamingResponse:
    repo = DocumentRepository(session)
    doc = await repo.get_by_id(document_id, org_id=current_user.org_id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Document not found"
        )

    from io import BytesIO

    from PIL import Image

    data = storage.get_object_bytes(doc.r2_key)
    buf = BytesIO()
    Image.open(BytesIO(data)).convert("RGB").save(buf, "PNG")
    buf.seek(0)

    return StreamingResponse(buf, media_type="image/png")


# ---------------------------------------------------------------------------
# Compare
# ---------------------------------------------------------------------------


@router.post("/compare", response_model=CompareResponse)
async def compare_documents(
    body: CompareRequest,
    current_user: CurrentUserDep,
    session: AuthSession,
) -> CompareResponse:
    repo = DocumentRepository(session)
    doc_a = await repo.get_by_id(body.doc_a_id, org_id=current_user.org_id)
    doc_b = await repo.get_by_id(body.doc_b_id, org_id=current_user.org_id)
    if not doc_a or not doc_b:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="One or both documents not found",
        )

    ai_summary = None
    text_a = (doc_a.extracted_text or "")[:5000]
    text_b = (doc_b.extracted_text or "")[:5000]
    if text_a and text_b:
        try:
            from app.services.ai import _call_llm

            prompt = (
                "Compare these two documents. Summarize the key differences "
                "and similarities in 3-5 bullet points. Be concise.\n\n"
                f"## Document A: {doc_a.filename}\n{text_a}\n\n"
                f"## Document B: {doc_b.filename}\n{text_b}"
            )
            ai_summary = await _call_llm(prompt)
        except Exception:
            logger.warning("AI comparison failed")

    return CompareResponse(
        doc_a=CompareDoc(
            id=doc_a.id,
            filename=doc_a.filename,
            extracted_text=doc_a.extracted_text,
            page_count=doc_a.page_count,
        ),
        doc_b=CompareDoc(
            id=doc_b.id,
            filename=doc_b.filename,
            extracted_text=doc_b.extracted_text,
            page_count=doc_b.page_count,
        ),
        ai_summary=ai_summary,
    )


# ---------------------------------------------------------------------------
# Bulk actions
# ---------------------------------------------------------------------------


@router.post("/bulk/delete", response_model=BulkDeleteResponse)
async def bulk_delete(
    body: BulkDocumentRequest,
    current_user: CurrentUserDep,
    session: AuthSession,
) -> BulkDeleteResponse:
    repo = DocumentRepository(session)
    docs = await repo.get_by_ids(body.document_ids, current_user.org_id)
    if len(docs) != len(body.document_ids):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="One or more documents not found",
        )

    r2_keys = [d.r2_key for d in docs]
    doc_ids = [d.id for d in docs]

    chunk_repo = ChunkRepository(session)
    await chunk_repo.delete_for_documents(doc_ids)
    count = await repo.delete_by_ids(doc_ids, current_user.org_id)

    try:
        storage.delete_objects(r2_keys)
    except Exception:
        logger.warning("R2 bulk delete failed for keys=%s", r2_keys)

    return BulkDeleteResponse(deleted=count)


_MAX_DOWNLOAD_FILES = 20
_MAX_DOWNLOAD_BYTES = 500 * 1024 * 1024  # 500 MB


@router.post("/bulk/download")
async def bulk_download(
    body: BulkDocumentRequest,
    current_user: CurrentUserDep,
    session: AuthSession,
) -> StreamingResponse:
    if len(body.document_ids) > _MAX_DOWNLOAD_FILES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot download more than {_MAX_DOWNLOAD_FILES} files at once",
        )

    repo = DocumentRepository(session)
    docs = await repo.get_by_ids(body.document_ids, current_user.org_id)
    if len(docs) != len(body.document_ids):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="One or more documents not found",
        )

    total_size = sum(d.size_bytes for d in docs)
    if total_size > _MAX_DOWNLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Total file size exceeds 500 MB limit",
        )

    import io
    import zipfile
    from datetime import datetime as dt

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for doc in docs:
            data = storage.get_object_bytes(doc.r2_key)
            zf.writestr(doc.filename, data)
    buf.seek(0)

    ts = dt.utcnow().strftime("%Y%m%d-%H%M%S")
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="documents-{ts}.zip"',
        },
    )


_EXCEL_TEXT_LIMIT = 32000  # Excel cell character limit
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _safe_excel_str(value: str) -> str:
    """Prevent formula injection by prefixing suspicious cell values with apostrophe."""
    if value and value[0] in _FORMULA_PREFIXES:
        return "'" + value
    return value


@router.post("/bulk/export")
async def bulk_export(
    body: BulkDocumentRequest,
    current_user: CurrentUserDep,
    session: AuthSession,
) -> StreamingResponse:
    repo = DocumentRepository(session)
    docs = await repo.get_by_ids(body.document_ids, current_user.org_id)
    if len(docs) != len(body.document_ids):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="One or more documents not found",
        )

    import io
    from datetime import datetime as dt

    from openpyxl import Workbook
    from openpyxl.styles import Font

    wb = Workbook()
    ws = wb.active
    ws.title = "Documents"

    columns = [
        "Filename",
        "Type",
        "Size (KB)",
        "Pages",
        "Status",
        "Uploaded At",
        "Extracted Text",
    ]
    ws.append(columns)
    for cell in ws[1]:
        cell.font = Font(bold=True)

    for doc in docs:
        text = doc.extracted_text or ""
        if len(text) > _EXCEL_TEXT_LIMIT:
            text = text[:_EXCEL_TEXT_LIMIT] + "... [truncated]"
        ws.append(
            [
                _safe_excel_str(doc.filename),
                _safe_excel_str(doc.mime_type),
                round(doc.size_bytes / 1024, 1),
                doc.page_count,
                doc.status,
                doc.created_at.isoformat() if doc.created_at else "",
                _safe_excel_str(text),
            ]
        )

    for col in ws.columns:
        max_len = max(len(str(cell.value or "")) for cell in col)
        ws.column_dimensions[col[0].column_letter].width = min(max_len + 2, 50)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    ts = dt.utcnow().strftime("%Y%m%d-%H%M%S")
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="documents-export-{ts}.xlsx"',
        },
    )
