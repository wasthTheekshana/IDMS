import uuid
from datetime import datetime

from pydantic import BaseModel


class PlatformAdminProfile(BaseModel):
    id: uuid.UUID
    email: str


class AdminOrganizationResponse(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    plan: str
    is_suspended: bool
    monthly_page_quota: int
    pages_used_this_month: int
    user_count: int
    document_count: int
    ai_tokens_total: int
    ai_cost_total_usd: float
    ai_qa_enabled: bool
    ai_summarization_enabled: bool
    ai_search_answer_enabled: bool
    ai_extraction_enabled: bool

    model_config = {"from_attributes": True}


class AdminOrgUpdateRequest(BaseModel):
    is_suspended: bool | None = None
    ai_qa_enabled: bool | None = None
    ai_summarization_enabled: bool | None = None
    ai_search_answer_enabled: bool | None = None
    ai_extraction_enabled: bool | None = None


class AdminDocumentResponse(BaseModel):
    id: uuid.UUID
    filename: str
    mime_type: str
    size_bytes: int
    status: str
    page_count: int | None
    uploaded_by_email: str
    created_at: datetime
