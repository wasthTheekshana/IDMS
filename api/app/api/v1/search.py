import uuid

from fastapi import APIRouter, Query

from app.core.deps import AuthSession, CurrentUserDep
from app.schemas.search import SearchResponse
from app.services.search import hybrid_search

router = APIRouter(prefix="/search", tags=["search"])


@router.get("", response_model=SearchResponse)
async def search_documents(
    q: str = Query(..., min_length=1, max_length=500),
    limit: int = Query(default=10, ge=1, le=50),
    document_id: uuid.UUID | None = Query(default=None),
    current_user: CurrentUserDep = ...,
    session: AuthSession = ...,
) -> SearchResponse:
    return await hybrid_search(
        q, current_user.org_id, session, limit=limit, document_id=document_id
    )
