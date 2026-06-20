import uuid
from datetime import datetime

from pydantic import BaseModel, field_validator


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


class DocumentDetailResponse(DocumentResponse):
    extracted_text: str | None


class BulkDocumentRequest(BaseModel):
    document_ids: list[uuid.UUID]

    @field_validator("document_ids")
    @classmethod
    def validate_ids(cls, v: list[uuid.UUID]) -> list[uuid.UUID]:
        if len(v) == 0:
            raise ValueError("document_ids must not be empty")
        if len(v) > 100:
            raise ValueError("document_ids must not exceed 100 items")
        return v


class BulkDeleteResponse(BaseModel):
    deleted: int
