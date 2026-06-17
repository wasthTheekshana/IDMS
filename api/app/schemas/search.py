import uuid

from pydantic import BaseModel


class SearchHit(BaseModel):
    document_id: uuid.UUID
    filename: str
    page: int
    content: str
    score: float


class SearchResponse(BaseModel):
    query: str
    hits: list[SearchHit]
    total: int
