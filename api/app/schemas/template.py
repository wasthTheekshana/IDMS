import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class FieldDefinition(BaseModel):
    key: str
    label: str
    type: str = "text"


class TemplateCreate(BaseModel):
    name: str
    description: str | None = None
    fields: list[FieldDefinition]


class TemplateUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    fields: list[FieldDefinition] | None = None


class TemplateResponse(BaseModel):
    id: uuid.UUID
    org_id: uuid.UUID
    name: str
    description: str | None
    fields: list[dict[str, Any]]
    created_at: datetime

    model_config = {"from_attributes": True}


class ExtractRequest(BaseModel):
    document_id: uuid.UUID
    template_id: uuid.UUID


class ExtractionResponse(BaseModel):
    id: uuid.UUID
    document_id: uuid.UUID
    template_id: uuid.UUID
    data: dict[str, Any]
    confidence: dict[str, Any] | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ExtractionRow(BaseModel):
    document_id: uuid.UUID
    filename: str
    template_name: str
    data: dict[str, Any]
    created_at: datetime
