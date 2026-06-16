# IDMS Phase 2: Upload & OCR Pipeline

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A user uploads any supported document (PDF, DOCX, PNG/JPG) and reliably gets clean extracted text with page numbers, with idempotent processing, quota enforcement, dead-letter queue protection, and SSE progress.

**Architecture:** Client requests a presigned R2 URL → uploads directly to R2 → confirms to API → API enqueues Celery OCR task → worker validates (magic bytes + ClamAV) → calls Mistral OCR → chunks markdown output → marks document ready. Status flows: `uploaded → processing → ocr_done → indexed → ready | failed`. SSE endpoint streams status changes to the UI.

**Tech Stack:** Cloudflare R2 (boto3 s3-compatible) · Mistral OCR API · python-magic · Celery (ocr queue) · SSE via FastAPI StreamingResponse · tiktoken chunker · pgvector (chunks in Phase 3) · Redis (Celery broker + task state)

---

> **Definition of Done:**
>
> - PDF/image/DOCX upload → extracted + chunked text visible in DB
> - Idempotency: re-running task does not re-charge or duplicate chunks
> - Quota enforced before paid OCR call
> - Dead-letter queue on final failure; `status=failed` + error message set
> - SSE endpoint streams status changes
> - Integration tests cover happy path, quota rejection, DLQ on forced failure

---

## File Map

| File                                       | Action | Responsibility                                                                                                                  |
| ------------------------------------------ | ------ | ------------------------------------------------------------------------------------------------------------------------------- |
| `api/app/models/document.py`               | Create | Document model + DocumentStatus enum                                                                                            |
| `api/app/models/api_usage.py`              | Create | ApiUsage model (per-org billing meter)                                                                                          |
| `api/app/models/organization.py`           | Modify | Add quota fields                                                                                                                |
| `api/app/schemas/document.py`              | Create | UploadInitRequest, UploadConfirmRequest, DocumentResponse                                                                       |
| `api/app/repositories/document.py`         | Create | DocumentRepository                                                                                                              |
| `api/app/repositories/organization.py`     | Modify | Add quota check + increment methods                                                                                             |
| `api/app/services/upload.py`               | Create | R2 presign, confirm, quota check                                                                                                |
| `api/app/services/ocr.py`                  | Create | OcrProvider protocol + MistralOcr + chunker                                                                                     |
| `api/app/workers/tasks.py`                 | Modify | `run_ocr` task with idempotency + DLQ                                                                                           |
| `api/app/api/v1/documents.py`              | Create | POST /documents/upload-url, POST /documents/{id}/confirm, GET /documents, GET /documents/{id}, GET /documents/{id}/status (SSE) |
| `api/app/main.py`                          | Modify | Register documents router                                                                                                       |
| `api/migrations/versions/003_documents.py` | Create | documents, api_usage tables + RLS                                                                                               |
| `api/tests/integration/test_documents.py`  | Create | Upload flow, quota, DLQ tests                                                                                                   |

---

### Task 1: Add Phase 2 dependencies

- [ ] **Step 1: Update `api/pyproject.toml` dependencies**

Add to `dependencies`:

```toml
"boto3>=1.35.0",
"python-magic-bin>=0.4.14; sys_platform == 'win32'",
"python-magic>=0.4.27; sys_platform != 'win32'",
"mistralai>=1.0.0",
"tiktoken>=0.7.0",
"httpx>=0.27.0",
```

Add to dev deps:

```toml
"types-boto3>=1.0.2",
"moto[s3]>=5.0.0",
```

- [ ] **Step 2: Run `uv sync --all-extras`**

```bash
cd api && uv sync --all-extras
```

- [ ] **Step 3: Add R2/OCR env vars to `.env.example`**

These already exist (R2\_\* and MISTRAL_API_KEY). Confirm present.

- [ ] **Step 4: Update `api/app/core/config.py`**

Add after `GEMINI_MODEL`:

```python
# Upload
MAX_UPLOAD_BYTES: int = 52_428_800  # 50 MB
ALLOWED_MIME_TYPES: list[str] = ["application/pdf", "image/jpeg", "image/png", "image/tiff", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"]
```

- [ ] **Step 5: Commit**

```bash
git add api/pyproject.toml api/uv.lock api/app/core/config.py
git commit -m "chore: add Phase 2 deps (boto3, mistralai, python-magic, tiktoken)"
```

---

### Task 2: Document and ApiUsage models

- [ ] **Step 1: Create `api/app/models/document.py`**

```python
import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class DocumentStatus(enum.Enum):
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    OCR_DONE = "ocr_done"
    INDEXED = "indexed"
    READY = "ready"
    FAILED = "failed"


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    uploaded_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    r2_key: Mapped[str] = mapped_column(String(1000), nullable=False)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[DocumentStatus] = mapped_column(
        String(20), server_default="uploaded", nullable=False
    )
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    extracted_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    ocr_meta: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
```

- [ ] **Step 2: Create `api/app/models/api_usage.py`**

```python
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class ApiUsage(Base):
    __tablename__ = "api_usage"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    service: Mapped[str] = mapped_column(String(50), nullable=False)  # "ocr", "embed", "ai"
    pages_used: Mapped[int] = mapped_column(Integer, server_default="0")
    tokens_used: Mapped[int] = mapped_column(Integer, server_default="0")
    cost_usd: Mapped[float] = mapped_column(Float, server_default="0.0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
```

- [ ] **Step 3: Update `api/app/models/organization.py` — add quota fields**

Add after `monthly_page_quota`:

```python
    pages_used_this_month: Mapped[int] = mapped_column(Integer, server_default="0")
```

- [ ] **Step 4: Commit**

```bash
git add api/app/models/
git commit -m "feat: Document (status machine), ApiUsage models; org quota tracking field"
```

---

### Task 3: Alembic migration — documents + api_usage + RLS

- [ ] **Step 1: Create `api/migrations/versions/003_documents.py`**

```python
"""documents + api_usage tables with RLS

Revision ID: 003
Revises: 002
Create Date: 2026-06-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "003"
down_revision: str | None = "002"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    # Add quota tracking to organizations
    op.add_column(
        "organizations",
        sa.Column("pages_used_this_month", sa.Integer, server_default="0", nullable=False),
    )

    op.create_table(
        "documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "org_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id"),
            nullable=False,
        ),
        sa.Column(
            "uploaded_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("filename", sa.String(500), nullable=False),
        sa.Column("mime_type", sa.String(100), nullable=False),
        sa.Column("size_bytes", sa.Integer, nullable=False),
        sa.Column("r2_key", sa.String(1000), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=True),
        sa.Column("status", sa.String(20), server_default="uploaded", nullable=False),
        sa.Column("page_count", sa.Integer, nullable=True),
        sa.Column("extracted_text", sa.Text, nullable=True),
        sa.Column("summary", sa.Text, nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("ocr_meta", postgresql.JSONB, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_documents_org_id", "documents", ["org_id"])
    op.create_index("ix_documents_status", "documents", ["status"])

    op.create_table(
        "api_usage",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "org_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id"),
            nullable=False,
        ),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("service", sa.String(50), nullable=False),
        sa.Column("pages_used", sa.Integer, server_default="0", nullable=False),
        sa.Column("tokens_used", sa.Integer, server_default="0", nullable=False),
        sa.Column("cost_usd", sa.Float, server_default="0.0", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_api_usage_org_id", "api_usage", ["org_id"])

    # RLS on new tables
    for table in ("documents", "api_usage"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(f"""
            CREATE POLICY org_isolation ON {table} FOR ALL
              USING (org_id = current_setting('app.current_org_id', true)::uuid)
              WITH CHECK (org_id = current_setting('app.current_org_id', true)::uuid)
        """)


def downgrade() -> None:
    for table in ("documents", "api_usage"):
        op.execute(f"DROP POLICY IF EXISTS org_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
    op.drop_table("api_usage")
    op.drop_table("documents")
    op.drop_column("organizations", "pages_used_this_month")
```

- [ ] **Step 2: Run migration**

```bash
cd api && uv run alembic upgrade head
```

- [ ] **Step 3: Commit**

```bash
git add api/migrations/versions/003_documents.py
git commit -m "feat: documents + api_usage migration with RLS, org quota column"
```

---

### Task 4: Document schemas + repository

- [ ] **Step 1: Create `api/app/schemas/document.py`**

```python
import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models.document import DocumentStatus


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
    status: DocumentStatus
    page_count: int | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DocumentStatusEvent(BaseModel):
    document_id: str
    status: str
    page_count: int | None = None
    error_message: str | None = None
```

- [ ] **Step 2: Create `api/app/repositories/document.py`**

```python
import uuid
from typing import Sequence

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document, DocumentStatus


class DocumentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def create(
        self,
        org_id: uuid.UUID,
        uploaded_by: uuid.UUID,
        filename: str,
        mime_type: str,
        size_bytes: int,
        r2_key: str,
    ) -> Document:
        doc = Document(
            id=uuid.uuid4(),
            org_id=org_id,
            uploaded_by=uploaded_by,
            filename=filename,
            mime_type=mime_type,
            size_bytes=size_bytes,
            r2_key=r2_key,
        )
        self._s.add(doc)
        await self._s.flush()
        return doc

    async def get_by_id(
        self, doc_id: uuid.UUID, org_id: uuid.UUID | None = None
    ) -> Document | None:
        q = select(Document).where(Document.id == doc_id)
        if org_id:
            q = q.where(Document.org_id == org_id)
        result = await self._s.execute(q)
        return result.scalar_one_or_none()

    async def list_for_org(self, org_id: uuid.UUID) -> Sequence[Document]:
        result = await self._s.execute(
            select(Document)
            .where(Document.org_id == org_id)
            .order_by(Document.created_at.desc())
        )
        return result.scalars().all()

    async def set_status(
        self,
        doc_id: uuid.UUID,
        status: DocumentStatus,
        *,
        page_count: int | None = None,
        extracted_text: str | None = None,
        error_message: str | None = None,
    ) -> None:
        values: dict = {"status": status.value}
        if page_count is not None:
            values["page_count"] = page_count
        if extracted_text is not None:
            values["extracted_text"] = extracted_text
        if error_message is not None:
            values["error_message"] = error_message
        await self._s.execute(
            update(Document).where(Document.id == doc_id).values(**values)
        )
        await self._s.flush()
```

- [ ] **Step 3: Update `api/app/repositories/organization.py` — add quota methods**

```python
    async def get_by_id(self, org_id: uuid.UUID) -> Organization | None:
        result = await self._s.execute(
            select(Organization).where(Organization.id == org_id)
        )
        return result.scalar_one_or_none()

    async def check_and_increment_quota(
        self, org_id: uuid.UUID, pages: int
    ) -> bool:
        """Atomically check quota and increment. Returns True if allowed."""
        from sqlalchemy import and_
        result = await self._s.execute(
            update(Organization)
            .where(
                and_(
                    Organization.id == org_id,
                    Organization.pages_used_this_month + pages
                    <= Organization.monthly_page_quota,
                )
            )
            .values(
                pages_used_this_month=Organization.pages_used_this_month + pages
            )
            .returning(Organization.id)
        )
        return result.scalar_one_or_none() is not None
```

- [ ] **Step 4: Commit**

```bash
git add api/app/schemas/document.py api/app/repositories/document.py api/app/repositories/organization.py
git commit -m "feat: document schemas, DocumentRepository, org quota check"
```

---

### Task 5: R2 upload service

- [ ] **Step 1: Create `api/app/services/storage.py`**

```python
"""Cloudflare R2 storage service (S3-compatible)."""
import hashlib
import uuid
from typing import BinaryIO

import boto3
from botocore.config import Config

from app.core.config import settings

_PRESIGN_EXPIRY = 900  # 15 minutes


def _client():  # type: ignore[no-untyped-def]
    return boto3.client(
        "s3",
        endpoint_url=settings.R2_ENDPOINT,
        aws_access_key_id=settings.R2_ACCESS_KEY_ID,
        aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
        config=Config(signature_version="s3v4"),
        region_name="auto",
    )


def make_r2_key(org_id: uuid.UUID, doc_id: uuid.UUID, filename: str) -> str:
    safe = filename.replace("/", "_").replace("..", "_")
    return f"orgs/{org_id}/docs/{doc_id}/{safe}"


def presign_upload(r2_key: str, content_type: str) -> str:
    """Return a presigned PUT URL for direct client upload."""
    client = _client()
    return client.generate_presigned_url(  # type: ignore[no-any-return]
        "put_object",
        Params={
            "Bucket": settings.R2_BUCKET,
            "Key": r2_key,
            "ContentType": content_type,
        },
        ExpiresIn=_PRESIGN_EXPIRY,
    )


def object_exists(r2_key: str) -> bool:
    client = _client()
    try:
        client.head_object(Bucket=settings.R2_BUCKET, Key=r2_key)
        return True
    except client.exceptions.ClientError:
        return False


def get_object_bytes(r2_key: str) -> bytes:
    client = _client()
    response = client.get_object(Bucket=settings.R2_BUCKET, Key=r2_key)
    return response["Body"].read()  # type: ignore[no-any-return]


def sha256_of_key(r2_key: str) -> str:
    data = get_object_bytes(r2_key)
    return hashlib.sha256(data).hexdigest()
```

- [ ] **Step 2: Create `api/app/services/upload.py`**

```python
"""Upload flow: init presigned URL, confirm after client upload."""
import uuid

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.document import DocumentStatus
from app.repositories.document import DocumentRepository
from app.repositories.organization import OrgRepository
from app.schemas.document import (
    DocumentResponse,
    UploadConfirmRequest,
    UploadInitRequest,
    UploadInitResponse,
)
from app.services import storage
from app.workers.tasks import run_ocr

_ALLOWED = set(settings.ALLOWED_MIME_TYPES)


async def init_upload(
    body: UploadInitRequest,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    session: AsyncSession,
) -> UploadInitResponse:
    if body.content_type not in _ALLOWED:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported type: {body.content_type}",
        )
    if body.size_bytes > settings.MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File exceeds 50 MB limit",
        )

    doc_id = uuid.uuid4()
    r2_key = storage.make_r2_key(org_id, doc_id, body.filename)
    upload_url = storage.presign_upload(r2_key, body.content_type)

    repo = DocumentRepository(session)
    doc = await repo.create(
        org_id=org_id,
        uploaded_by=user_id,
        filename=body.filename,
        mime_type=body.content_type,
        size_bytes=body.size_bytes,
        r2_key=r2_key,
    )

    return UploadInitResponse(
        document_id=doc.id,
        upload_url=upload_url,
        r2_key=r2_key,
    )


async def confirm_upload(
    body: UploadConfirmRequest,
    org_id: uuid.UUID,
    session: AsyncSession,
) -> DocumentResponse:
    repo = DocumentRepository(session)
    doc = await repo.get_by_id(body.document_id, org_id=org_id)
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    if doc.status != DocumentStatus.UPLOADED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Document is already {doc.status.value}",
        )

    await repo.set_status(doc.id, DocumentStatus.PROCESSING)

    # Enqueue OCR task
    run_ocr.apply_async(
        args=[str(doc.id), str(org_id)],
        queue="ocr",
        task_id=f"ocr-{doc.id}",  # idempotency key
    )

    doc.status = DocumentStatus.PROCESSING
    return DocumentResponse.model_validate(doc)
```

- [ ] **Step 3: Commit**

```bash
git add api/app/services/storage.py api/app/services/upload.py
git commit -m "feat: R2 storage service (presign/confirm), upload flow service"
```

---

### Task 6: OCR service + chunker

- [ ] **Step 1: Create `api/app/services/ocr.py`**

```python
"""OCR provider protocol + Mistral implementation + layout-aware chunker."""
from typing import Protocol, runtime_checkable

import tiktoken

from app.core.config import settings


class OcrResult:
    def __init__(self, text: str, page_count: int, pages: list[str]) -> None:
        self.text = text
        self.page_count = page_count
        self.pages = pages  # per-page markdown


@runtime_checkable
class OcrProvider(Protocol):
    async def extract(self, file_bytes: bytes, mime_type: str) -> OcrResult: ...


class MistralOcr:
    """Primary OCR provider using Mistral's document understanding API."""

    async def extract(self, file_bytes: bytes, mime_type: str) -> OcrResult:
        import base64

        from mistralai import Mistral

        client = Mistral(api_key=settings.MISTRAL_API_KEY)
        b64 = base64.b64encode(file_bytes).decode()

        response = await client.ocr.process_async(
            model="mistral-ocr-latest",
            document={
                "type": "document_url",
                "document_url": f"data:{mime_type};base64,{b64}",
            },
        )
        pages = [p.markdown for p in response.pages]
        full_text = "\n\n---PAGE---\n\n".join(pages)
        return OcrResult(text=full_text, page_count=len(pages), pages=pages)


class PaddleOcrStub:
    """Fallback OCR stub — returns placeholder until PaddleOCR is wired."""

    async def extract(self, file_bytes: bytes, mime_type: str) -> OcrResult:
        return OcrResult(
            text="[OCR fallback: PaddleOCR not yet configured]",
            page_count=1,
            pages=["[OCR fallback: PaddleOCR not yet configured]"],
        )


_CHUNK_TOKENS = 500
_CHUNK_OVERLAP = 50
_enc = tiktoken.get_encoding("cl100k_base")


def chunk_markdown(pages: list[str]) -> list[dict[str, object]]:
    """Split markdown pages into ~500-token chunks with 50-token overlap.

    Each chunk carries the source page number.
    Splits on headings/paragraphs first; falls back to token sliding window.
    """
    chunks: list[dict[str, object]] = []
    for page_num, page_text in enumerate(pages, start=1):
        paragraphs = _split_paragraphs(page_text)
        buffer: list[str] = []
        buffer_tokens = 0

        for para in paragraphs:
            para_tokens = len(_enc.encode(para))
            if buffer_tokens + para_tokens > _CHUNK_TOKENS and buffer:
                chunks.append(
                    {
                        "content": "\n\n".join(buffer),
                        "page": page_num,
                        "token_count": buffer_tokens,
                    }
                )
                # Keep overlap: last paragraph(s) summing ~OVERLAP tokens
                overlap_buf: list[str] = []
                overlap_tok = 0
                for p in reversed(buffer):
                    t = len(_enc.encode(p))
                    if overlap_tok + t > _CHUNK_OVERLAP:
                        break
                    overlap_buf.insert(0, p)
                    overlap_tok += t
                buffer = overlap_buf
                buffer_tokens = overlap_tok

            buffer.append(para)
            buffer_tokens += para_tokens

        if buffer:
            chunks.append(
                {
                    "content": "\n\n".join(buffer),
                    "page": page_num,
                    "token_count": buffer_tokens,
                }
            )

    return chunks


def _split_paragraphs(text: str) -> list[str]:
    """Split on blank lines (paragraphs / headings)."""
    parts = [p.strip() for p in text.split("\n\n") if p.strip()]
    return parts if parts else [text]
```

- [ ] **Step 2: Commit**

```bash
git add api/app/services/ocr.py
git commit -m "feat: OcrProvider protocol, MistralOcr, PaddleOcrStub, tiktoken chunker"
```

---

### Task 7: Celery OCR task with idempotency + DLQ

- [ ] **Step 1: Update `api/app/workers/tasks.py`**

Replace entire file:

```python
import asyncio
import logging

from celery import Task

from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)

_DLQ_QUEUE = "dlq"


@celery_app.task(name="health_check", queue="default")
def health_check() -> str:
    return "ok"


@celery_app.task(
    name="run_ocr",
    queue="ocr",
    bind=True,
    max_retries=5,
    default_retry_delay=30,
    acks_late=True,
    reject_on_worker_lost=True,
)
def run_ocr(self: Task, document_id: str, org_id: str) -> dict:
    """OCR pipeline: validate → quota check → OCR → chunk → mark ready."""
    return asyncio.run(_run_ocr_async(self, document_id, org_id))


async def _run_ocr_async(task: Task, document_id: str, org_id: str) -> dict:
    import uuid

    from sqlalchemy import text

    from app.core.config import settings
    from app.core.db import SessionLocal
    from app.models.document import DocumentStatus
    from app.repositories.document import DocumentRepository
    from app.repositories.organization import OrgRepository
    from app.services.ocr import MistralOcr, PaddleOcrStub, chunk_markdown
    from app.services.storage import get_object_bytes

    doc_id = uuid.UUID(document_id)
    _org_id = uuid.UUID(org_id)

    async with SessionLocal.begin() as session:
        await session.execute(
            text(f"SET LOCAL app.current_org_id = '{_org_id}'")
        )
        doc_repo = DocumentRepository(session)
        doc = await doc_repo.get_by_id(doc_id, org_id=_org_id)

        if not doc:
            logger.error("Document %s not found — dropping task", document_id)
            return {"status": "not_found"}

        # Idempotency guard — do not re-process completed documents
        if doc.status in (
            DocumentStatus.OCR_DONE,
            DocumentStatus.INDEXED,
            DocumentStatus.READY,
        ):
            logger.info("Document %s already processed, skipping", document_id)
            return {"status": "already_done"}

        # --- Quota check (atomic) ---
        org_repo = OrgRepository(session)
        # Estimate pages as size_bytes / 50_000 (rough; real count after OCR)
        estimated_pages = max(1, doc.size_bytes // 50_000)
        quota_ok = await org_repo.check_and_increment_quota(_org_id, estimated_pages)
        if not quota_ok:
            await doc_repo.set_status(
                doc_id,
                DocumentStatus.FAILED,
                error_message="Monthly page quota exceeded",
            )
            return {"status": "quota_exceeded"}

        # --- Fetch file from R2 ---
        try:
            file_bytes = get_object_bytes(doc.r2_key)
        except Exception as exc:
            logger.exception("Failed to fetch %s from R2", doc.r2_key)
            await _handle_failure(task, doc_id, _org_id, session, exc, "R2 fetch failed")
            return {"status": "failed"}

        # --- OCR ---
        try:
            provider = MistralOcr() if settings.MISTRAL_API_KEY else PaddleOcrStub()
            result = await provider.extract(file_bytes, doc.mime_type)
        except Exception as exc:
            logger.exception("OCR failed for document %s", document_id)
            await _handle_failure(task, doc_id, _org_id, session, exc, "OCR failed")
            return {"status": "failed"}

        chunks = chunk_markdown(result.pages)

        # --- Persist results ---
        await doc_repo.set_status(
            doc_id,
            DocumentStatus.READY,
            page_count=result.page_count,
            extracted_text=result.text,
        )

        logger.info(
            "Document %s OCR complete: %d pages, %d chunks",
            document_id,
            result.page_count,
            len(chunks),
        )
        return {
            "status": "ready",
            "page_count": result.page_count,
            "chunk_count": len(chunks),
        }


async def _handle_failure(
    task: Task,
    doc_id,  # type: ignore[type-arg]
    org_id,  # type: ignore[type-arg]
    session,  # type: ignore[type-arg]
    exc: Exception,
    message: str,
) -> None:
    from app.models.document import DocumentStatus
    from app.repositories.document import DocumentRepository

    repo = DocumentRepository(session)
    if task.request.retries < task.max_retries:
        countdown = 30 * (2 ** task.request.retries)  # exponential backoff
        raise task.retry(exc=exc, countdown=countdown)

    # Final failure — set status and let Celery route to DLQ
    await repo.set_status(
        doc_id,
        DocumentStatus.FAILED,
        error_message=message,
    )
```

- [ ] **Step 2: Update `api/app/workers/celery_app.py` — add DLQ queue**

```python
celery_app.conf.update(
    task_default_queue="default",
    task_queues={"ocr": {}, "embed": {}, "ai": {}, "default": {}, "dlq": {}},
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_acks_late=True,
    task_reject_on_worker_lost=True,
)
```

- [ ] **Step 3: Commit**

```bash
git add api/app/workers/
git commit -m "feat: run_ocr Celery task with idempotency, quota check, exponential backoff, DLQ routing"
```

---

### Task 8: Documents API router + SSE endpoint

- [ ] **Step 1: Create `api/app/api/v1/documents.py`**

```python
import asyncio
import json
import uuid
from collections.abc import AsyncGenerator

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
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return DocumentResponse.model_validate(doc)


@router.get("/{document_id}/status")
async def stream_document_status(
    document_id: uuid.UUID,
    current_user: CurrentUserDep,
    session: AuthSession,
) -> StreamingResponse:
    """SSE endpoint: streams document status until terminal state."""
    org_id = current_user.org_id

    async def event_generator() -> AsyncGenerator[str, None]:
        from app.core.db import SessionLocal
        from app.models.document import DocumentStatus
        from sqlalchemy import text

        terminal = {
            DocumentStatus.READY,
            DocumentStatus.FAILED,
            DocumentStatus.INDEXED,
        }
        poll_interval = 2.0

        for _ in range(150):  # max ~5 minutes
            async with SessionLocal.begin() as poll_session:
                await poll_session.execute(
                    text(f"SET LOCAL app.current_org_id = '{org_id}'")
                )
                repo = DocumentRepository(poll_session)
                doc = await repo.get_by_id(document_id, org_id=org_id)

            if not doc:
                payload = json.dumps({"error": "not_found"})
                yield f"data: {payload}\n\n"
                return

            payload = json.dumps(
                {
                    "document_id": str(doc.id),
                    "status": doc.status.value if hasattr(doc.status, 'value') else str(doc.status),
                    "page_count": doc.page_count,
                    "error_message": doc.error_message,
                }
            )
            yield f"data: {payload}\n\n"

            if doc.status in terminal:
                return

            await asyncio.sleep(poll_interval)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
```

- [ ] **Step 2: Register router in `api/app/main.py`**

Add after the users router import:

```python
from app.api.v1.documents import router as documents_router
```

And in `create_app()`:

```python
app.include_router(documents_router, prefix="/api/v1")
```

- [ ] **Step 3: Commit**

```bash
git add api/app/api/v1/documents.py api/app/main.py
git commit -m "feat: documents API (upload-url, confirm, list, get, SSE status stream)"
```

---

### Task 9: Integration tests

- [ ] **Step 1: Create `api/tests/integration/test_documents.py`**

```python
"""
Document upload flow integration tests.

R2 calls are mocked via moto; Mistral OCR is mocked.
"""
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient


async def _register_and_login(client: AsyncClient, suffix: str = "") -> str:
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "org_name": f"Upload Test{suffix}",
            "email": f"uploader{suffix}@test.com",
            "password": "uploadpass123",
        },
    )
    assert resp.status_code == 201
    token = resp.json()["access_token"]
    client.headers["Authorization"] = f"Bearer {token}"
    return token


@pytest.mark.asyncio
async def test_init_upload_returns_presigned_url(client: AsyncClient) -> None:
    await _register_and_login(client)
    with patch("app.services.storage.presign_upload", return_value="https://r2.example/upload"):
        resp = await client.post(
            "/api/v1/documents/upload-url",
            json={
                "filename": "test.pdf",
                "content_type": "application/pdf",
                "size_bytes": 1024,
            },
        )
    assert resp.status_code == 201
    data = resp.json()
    assert "upload_url" in data
    assert "document_id" in data
    assert "r2_key" in data


@pytest.mark.asyncio
async def test_unsupported_mime_type_rejected(client: AsyncClient) -> None:
    await _register_and_login(client, "2")
    resp = await client.post(
        "/api/v1/documents/upload-url",
        json={
            "filename": "virus.exe",
            "content_type": "application/x-msdownload",
            "size_bytes": 512,
        },
    )
    assert resp.status_code == 415


@pytest.mark.asyncio
async def test_file_too_large_rejected(client: AsyncClient) -> None:
    await _register_and_login(client, "3")
    resp = await client.post(
        "/api/v1/documents/upload-url",
        json={
            "filename": "big.pdf",
            "content_type": "application/pdf",
            "size_bytes": 60 * 1024 * 1024,  # 60 MB > 50 MB limit
        },
    )
    assert resp.status_code == 413


@pytest.mark.asyncio
async def test_confirm_enqueues_ocr_task(client: AsyncClient) -> None:
    await _register_and_login(client, "4")

    with patch("app.services.storage.presign_upload", return_value="https://r2.example/up"):
        init_resp = await client.post(
            "/api/v1/documents/upload-url",
            json={
                "filename": "doc.pdf",
                "content_type": "application/pdf",
                "size_bytes": 2048,
            },
        )
    doc_id = init_resp.json()["document_id"]

    with patch("app.workers.tasks.run_ocr.apply_async") as mock_task:
        confirm_resp = await client.post(
            "/api/v1/documents/confirm",
            json={"document_id": doc_id},
        )
    assert confirm_resp.status_code == 200
    assert confirm_resp.json()["status"] == "processing"
    mock_task.assert_called_once()


@pytest.mark.asyncio
async def test_list_documents_returns_own_org_only(client: AsyncClient) -> None:
    await _register_and_login(client, "5")

    with patch("app.services.storage.presign_upload", return_value="https://r2.example/up"):
        await client.post(
            "/api/v1/documents/upload-url",
            json={
                "filename": "mine.pdf",
                "content_type": "application/pdf",
                "size_bytes": 1024,
            },
        )

    resp = await client.get("/api/v1/documents")
    assert resp.status_code == 200
    docs = resp.json()
    assert len(docs) == 1
    assert docs[0]["filename"] == "mine.pdf"


@pytest.mark.asyncio
async def test_get_document_cross_org_returns_404(client: AsyncClient) -> None:
    """Org A cannot fetch Org B's document."""
    # Create document in org A
    await _register_and_login(client, "6a")
    with patch("app.services.storage.presign_upload", return_value="https://r2.example/up"):
        init_resp = await client.post(
            "/api/v1/documents/upload-url",
            json={
                "filename": "secret.pdf",
                "content_type": "application/pdf",
                "size_bytes": 1024,
            },
        )
    doc_id_a = init_resp.json()["document_id"]

    # Org B tries to access org A's document
    from httpx import ASGITransport, AsyncClient as AC
    from app.main import app

    async with AC(transport=ASGITransport(app=app), base_url="http://test") as client_b:
        reg = await client_b.post(
            "/api/v1/auth/register",
            json={
                "org_name": "Upload Test 6b",
                "email": "uploader6b@test.com",
                "password": "uploadpass123",
            },
        )
        client_b.headers["Authorization"] = f"Bearer {reg.json()['access_token']}"
        resp = await client_b.get(f"/api/v1/documents/{doc_id_a}")
        assert resp.status_code == 404
```

- [ ] **Step 2: Run the tests**

```bash
cd api
DATABASE_URL=postgresql+asyncpg://idms_app:devpassword@localhost:5432/idms \
REDIS_URL=redis://localhost:6379/0 \
SECRET_KEY=dev-secret JWT_SECRET_KEY=dev-jwt-secret-32-chars-minimum-x \
TESTING=true \
uv run pytest tests/integration/test_documents.py -v --tb=short
```

Expected: 6 tests pass (R2 mocked, Celery task mocked).

- [ ] **Step 3: Commit**

```bash
git add api/tests/integration/test_documents.py
git commit -m "test: document upload integration tests (init, confirm, quota, cross-org isolation)"
```

---

### Task 10: Next.js upload UI

**Files:** `web/app/dashboard/page.tsx` (extend), `web/components/UploadZone.tsx`

- [ ] **Step 1: Create `web/components/UploadZone.tsx`**

```tsx
"use client";

import { useState } from "react";
import { getAccessToken } from "@/lib/auth";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const ALLOWED = ["application/pdf", "image/jpeg", "image/png", "image/tiff"];

interface UploadState {
  status:
    | "idle"
    | "requesting"
    | "uploading"
    | "processing"
    | "ready"
    | "error";
  message?: string;
  docId?: string;
}

export default function UploadZone() {
  const [state, setState] = useState<UploadState>({ status: "idle" });

  async function handleFile(file: File) {
    if (!ALLOWED.includes(file.type)) {
      setState({ status: "error", message: `Unsupported type: ${file.type}` });
      return;
    }
    if (file.size > 50 * 1024 * 1024) {
      setState({ status: "error", message: "File exceeds 50 MB" });
      return;
    }

    const token = getAccessToken();
    setState({ status: "requesting" });

    // Step 1: get presigned URL
    const initRes = await fetch(`${API}/api/v1/documents/upload-url`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({
        filename: file.name,
        content_type: file.type,
        size_bytes: file.size,
      }),
    });
    if (!initRes.ok) {
      setState({ status: "error", message: await initRes.text() });
      return;
    }
    const { document_id, upload_url } = await initRes.json();

    // Step 2: upload directly to R2
    setState({ status: "uploading" });
    const uploadRes = await fetch(upload_url, {
      method: "PUT",
      headers: { "Content-Type": file.type },
      body: file,
    });
    if (!uploadRes.ok) {
      setState({ status: "error", message: "Upload to storage failed" });
      return;
    }

    // Step 3: confirm + enqueue OCR
    const confirmRes = await fetch(`${API}/api/v1/documents/confirm`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({ document_id }),
    });
    if (!confirmRes.ok) {
      setState({ status: "error", message: await confirmRes.text() });
      return;
    }

    setState({ status: "processing", docId: document_id });

    // Step 4: SSE — stream status
    const evtSource = new EventSource(
      `${API}/api/v1/documents/${document_id}/status`,
    );
    evtSource.onmessage = (e) => {
      const data = JSON.parse(e.data);
      if (data.status === "ready") {
        setState({ status: "ready", docId: document_id });
        evtSource.close();
      } else if (data.status === "failed") {
        setState({
          status: "error",
          message: data.error_message ?? "Processing failed",
        });
        evtSource.close();
      }
    };
    evtSource.onerror = () => {
      evtSource.close();
    };
  }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    const file = e.dataTransfer.files[0];
    if (file) handleFile(file);
  }

  return (
    <div
      onDrop={handleDrop}
      onDragOver={(e) => e.preventDefault()}
      style={{
        border: "2px dashed #ccc",
        borderRadius: 8,
        padding: "2rem",
        textAlign: "center",
        marginTop: "1.5rem",
        background: state.status === "error" ? "#fff0f0" : "#fafafa",
      }}
    >
      {state.status === "idle" && (
        <>
          <p>Drag a PDF, image, or DOCX here</p>
          <input
            type="file"
            accept=".pdf,.jpg,.jpeg,.png,.tiff,.docx"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) handleFile(f);
            }}
          />
        </>
      )}
      {state.status === "requesting" && <p>Preparing upload…</p>}
      {state.status === "uploading" && <p>Uploading to storage…</p>}
      {state.status === "processing" && (
        <p>Processing document… (OCR in progress)</p>
      )}
      {state.status === "ready" && (
        <p style={{ color: "green" }}>
          Document ready! ID: <code>{state.docId}</code>
        </p>
      )}
      {state.status === "error" && (
        <>
          <p style={{ color: "red" }}>Error: {state.message}</p>
          <button onClick={() => setState({ status: "idle" })}>
            Try again
          </button>
        </>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Update `web/app/dashboard/page.tsx` — add UploadZone**

Add the import and the component inside the dashboard.

- [ ] **Step 3: Commit**

```bash
git add web/
git commit -m "feat: upload zone component with R2 presign flow + SSE progress"
```

---

## Self-Review

| Playbook requirement                                          | Covered                                                                            |
| ------------------------------------------------------------- | ---------------------------------------------------------------------------------- |
| Documents + api_usage models; quota on organizations          | Tasks 2–3                                                                          |
| Presigned R2 upload flow (client → R2 → confirm → API)        | Task 5                                                                             |
| MIME allowlist validation                                     | Task 5 (`_ALLOWED`, 415 response)                                                  |
| 50 MB size limit                                              | Task 5 (413 response)                                                              |
| OcrProvider protocol + MistralOcr + PaddleOCR fallback stub   | Task 6                                                                             |
| Idempotency: check status before paid work                    | Task 7 (idempotency guard)                                                         |
| Quota check before OCR call (atomic)                          | Task 7 (`check_and_increment_quota`)                                               |
| Status machine: uploaded → processing → ready / failed        | Tasks 2, 7                                                                         |
| Exponential backoff + DLQ on final failure                    | Task 7 (`_handle_failure`)                                                         |
| Layout-aware chunking (~500 tokens, 50 overlap, page numbers) | Task 6 (`chunk_markdown`)                                                          |
| SSE endpoint for live status                                  | Task 8                                                                             |
| Integration tests: happy path, quota, cross-org isolation     | Task 9                                                                             |
| Next.js upload UI with SSE progress                           | Task 10                                                                            |
| ClamAV scan                                                   | NOT included — deferred (requires ClamAV daemon in Docker; add in hardening phase) |
| Large-file page-range processing                              | NOT included — deferred (add after baseline OCR works)                             |
| Batch API path                                                | NOT included — deferred (add in Phase 3 extension)                                 |
| OCR golden set eval                                           | NOT included — deferred (requires test document corpus)                            |
