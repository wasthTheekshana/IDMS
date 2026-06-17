import uuid

from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)


class AskSource(BaseModel):
    page: int
    excerpt: str
    document_id: str | None = None
    filename: str | None = None


class AskResponse(BaseModel):
    answer: str
    sources: list[AskSource]


class SummarizeResponse(BaseModel):
    document_id: uuid.UUID
    summary: str
