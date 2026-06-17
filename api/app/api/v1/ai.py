import uuid

from fastapi import APIRouter, HTTPException, status

from app.core.deps import AuthSession, CurrentUserDep
from app.repositories.document import DocumentRepository
from app.schemas.ai import AskRequest, AskResponse, SummarizeResponse
from app.services import ai as ai_service

router = APIRouter(prefix="/ai", tags=["ai"])


@router.post("/documents/{document_id}/ask", response_model=AskResponse)
async def ask_document(
    document_id: uuid.UUID,
    body: AskRequest,
    current_user: CurrentUserDep,
    session: AuthSession,
) -> AskResponse:
    """RAG Q&A on a single document."""
    repo = DocumentRepository(session)
    doc = await repo.get_by_id(document_id, org_id=current_user.org_id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )
    result = await ai_service.ask_document(
        session, current_user.org_id, document_id, body.question
    )
    return AskResponse(**result)  # type: ignore[arg-type]


@router.post(
    "/documents/{document_id}/summarize",
    response_model=SummarizeResponse,
)
async def summarize_document(
    document_id: uuid.UUID,
    current_user: CurrentUserDep,
    session: AuthSession,
) -> SummarizeResponse:
    """Generate a summary of a document via Gemini."""
    repo = DocumentRepository(session)
    doc = await repo.get_by_id(document_id, org_id=current_user.org_id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )
    summary = await ai_service.summarize_document(
        session, current_user.org_id, document_id
    )
    return SummarizeResponse(document_id=document_id, summary=summary)


@router.post("/chat", response_model=AskResponse)
async def chat(
    body: AskRequest,
    current_user: CurrentUserDep,
    session: AuthSession,
) -> AskResponse:
    """Org-wide RAG chat — search across all documents."""
    result = await ai_service.ask_org(session, current_user.org_id, body.question)
    return AskResponse(**result)  # type: ignore[arg-type]
