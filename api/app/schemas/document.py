import uuid
from datetime import datetime

from pydantic import BaseModel


class UploadInitRequest(BaseModel):
    filename: str
    content_type: str
    size_bytes: int


class UploadInitResponse(BaseModel):
    document_id: uuid.UUID
    upload_url: str
    r2_key: str


class UploadConfirmRequest(BaseModel):
    document_id: uuid.UUID


class DocumentResponse(BaseModel):
    id: uuid.UUID
    org_id: uuid.UUID
    filename: str
    mime_type: str
    size_bytes: int
    status: str
    page_count: int | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
