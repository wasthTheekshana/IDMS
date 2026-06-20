# Bulk Upload + Bulk Actions + Excel Export — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add multi-file parallel upload, bulk document actions (delete, download ZIP, export Excel), and selection UI to the IDMS.

**Architecture:** Three layers of changes — (1) backend bulk endpoints in FastAPI with openpyxl for Excel, (2) repository methods for batch operations, (3) frontend components for multi-file upload, document selection with action toolbar, and a delete confirmation modal. No new DB models; everything builds on the existing Document/DocumentChunk tables.

**Tech Stack:** FastAPI, SQLAlchemy async, openpyxl, boto3, React/TypeScript (Next.js)

## Global Constraints

- Python 3.11+, FastAPI ≥0.115, SQLAlchemy ≥2.0, Pydantic ≥2.0
- All endpoints enforce org-scoping via `SET LOCAL app.current_org_id` (RLS)
- Tests mock R2 via `patch("app.services.storage.*")` and Celery via `patch("app.workers.tasks.*")`
- Frontend uses `getAccessToken()` from `@/lib/auth` for JWT
- API base URL: `process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"`
- No new database migrations required

---

### Task 1: Add `openpyxl` dependency

**Files:**

- Modify: `api/pyproject.toml`

**Interfaces:**

- Consumes: nothing
- Produces: `openpyxl` available for import in backend code

- [ ] **Step 1: Add openpyxl to project dependencies**

In `api/pyproject.toml`, add `openpyxl` to the `dependencies` list:

```toml
"openpyxl>=3.1.0",
```

Add it after the existing `boto3` line in the dependencies array.

- [ ] **Step 2: Install and lock**

Run:

```bash
cd api && uv lock && uv sync
```

Expected: lockfile updated, openpyxl installed.

- [ ] **Step 3: Verify import**

Run:

```bash
cd api && uv run python -c "import openpyxl; print(openpyxl.__version__)"
```

Expected: prints version like `3.1.x`

- [ ] **Step 4: Commit**

```bash
git add api/pyproject.toml api/uv.lock
git commit -m "chore: add openpyxl dependency for Excel export"
```

---

### Task 2: Add bulk repository methods

**Files:**

- Modify: `api/app/repositories/document.py`
- Modify: `api/app/repositories/chunk.py`
- Modify: `api/app/services/storage.py`

**Interfaces:**

- Consumes: `DocumentRepository`, `ChunkRepository`, storage functions
- Produces:
  - `DocumentRepository.get_by_ids(doc_ids: list[uuid.UUID], org_id: uuid.UUID) -> Sequence[Document]`
  - `DocumentRepository.delete_by_ids(doc_ids: list[uuid.UUID], org_id: uuid.UUID) -> int`
  - `ChunkRepository.delete_for_documents(doc_ids: list[uuid.UUID]) -> None`
  - `storage.delete_objects(r2_keys: list[str]) -> None`
  - `storage.presign_download(r2_key: str) -> str`

- [ ] **Step 1: Write failing tests for bulk repository methods**

Create `api/tests/unit/test_bulk_repository.py`:

```python
"""Unit tests for bulk document repository methods.

These test the SQL logic with a real async DB session.
"""

import uuid

import pytest
from sqlalchemy import text

from app.core.db import SessionLocal
from app.models.document import Document
from app.repositories.chunk import ChunkRepository
from app.repositories.document import DocumentRepository


async def _seed_doc(session, org_id: uuid.UUID, filename: str) -> Document:
    repo = DocumentRepository(session)
    return await repo.create(
        org_id=org_id,
        uploaded_by=uuid.uuid4(),
        filename=filename,
        mime_type="application/pdf",
        size_bytes=1024,
        r2_key=f"orgs/{org_id}/docs/{uuid.uuid4()}/{filename}",
    )


@pytest.mark.asyncio
async def test_get_by_ids_returns_matching_docs() -> None:
    async with SessionLocal.begin() as s:
        await s.execute(
            text(
                "TRUNCATE TABLE document_chunks, documents,"
                " users, organizations RESTART IDENTITY CASCADE"
            )
        )
        org_id = uuid.uuid4()
        await s.execute(
            text(
                "INSERT INTO organizations (id, name, slug) VALUES (:id, :n, :s)"
            ),
            {"id": str(org_id), "n": "Test Org", "s": "test-org-bulk"},
        )
        await s.execute(
            text(
                "INSERT INTO users (id, org_id, email, password_hash, role)"
                " VALUES (:id, :org, :email, :pw, :role)"
            ),
            {
                "id": str(uuid.uuid4()),
                "org": str(org_id),
                "email": "bulk@test.com",
                "pw": "x",
                "role": "owner",
            },
        )
        doc1 = await _seed_doc(s, org_id, "a.pdf")
        doc2 = await _seed_doc(s, org_id, "b.pdf")
        await _seed_doc(s, org_id, "c.pdf")

        repo = DocumentRepository(s)
        result = await repo.get_by_ids([doc1.id, doc2.id], org_id)
        assert len(result) == 2
        assert {d.id for d in result} == {doc1.id, doc2.id}


@pytest.mark.asyncio
async def test_get_by_ids_filters_by_org() -> None:
    async with SessionLocal.begin() as s:
        await s.execute(
            text(
                "TRUNCATE TABLE document_chunks, documents,"
                " users, organizations RESTART IDENTITY CASCADE"
            )
        )
        org_a = uuid.uuid4()
        org_b = uuid.uuid4()
        for oid, name, slug, email in [
            (org_a, "Org A", "org-a-bulk", "a-bulk@test.com"),
            (org_b, "Org B", "org-b-bulk", "b-bulk@test.com"),
        ]:
            await s.execute(
                text(
                    "INSERT INTO organizations (id, name, slug)"
                    " VALUES (:id, :n, :s)"
                ),
                {"id": str(oid), "n": name, "s": slug},
            )
            await s.execute(
                text(
                    "INSERT INTO users (id, org_id, email, password_hash, role)"
                    " VALUES (:id, :org, :email, :pw, :role)"
                ),
                {
                    "id": str(uuid.uuid4()),
                    "org": str(oid),
                    "email": email,
                    "pw": "x",
                    "role": "owner",
                },
            )
        doc_b = await _seed_doc(s, org_b, "secret.pdf")

        repo = DocumentRepository(s)
        result = await repo.get_by_ids([doc_b.id], org_a)
        assert len(result) == 0


@pytest.mark.asyncio
async def test_delete_by_ids_removes_docs_and_returns_count() -> None:
    async with SessionLocal.begin() as s:
        await s.execute(
            text(
                "TRUNCATE TABLE document_chunks, documents,"
                " users, organizations RESTART IDENTITY CASCADE"
            )
        )
        org_id = uuid.uuid4()
        await s.execute(
            text(
                "INSERT INTO organizations (id, name, slug) VALUES (:id, :n, :s)"
            ),
            {"id": str(org_id), "n": "Del Org", "s": "del-org-bulk"},
        )
        await s.execute(
            text(
                "INSERT INTO users (id, org_id, email, password_hash, role)"
                " VALUES (:id, :org, :email, :pw, :role)"
            ),
            {
                "id": str(uuid.uuid4()),
                "org": str(org_id),
                "email": "del-bulk@test.com",
                "pw": "x",
                "role": "owner",
            },
        )
        doc1 = await _seed_doc(s, org_id, "d1.pdf")
        doc2 = await _seed_doc(s, org_id, "d2.pdf")

        repo = DocumentRepository(s)
        count = await repo.delete_by_ids([doc1.id, doc2.id], org_id)
        assert count == 2

        remaining = await repo.list_for_org(org_id)
        assert len(remaining) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
cd api && uv run pytest tests/unit/test_bulk_repository.py -v
```

Expected: FAIL — `AttributeError: 'DocumentRepository' has no attribute 'get_by_ids'`

- [ ] **Step 3: Implement `get_by_ids` and `delete_by_ids` in DocumentRepository**

Add to `api/app/repositories/document.py` after the existing `list_for_org` method:

```python
    async def get_by_ids(
        self, doc_ids: list[uuid.UUID], org_id: uuid.UUID
    ) -> Sequence[Document]:
        result = await self._s.execute(
            select(Document)
            .where(Document.id.in_(doc_ids))
            .where(Document.org_id == org_id)
        )
        return result.scalars().all()

    async def delete_by_ids(
        self, doc_ids: list[uuid.UUID], org_id: uuid.UUID
    ) -> int:
        result = await self._s.execute(
            delete(Document)
            .where(Document.id.in_(doc_ids))
            .where(Document.org_id == org_id)
        )
        await self._s.flush()
        return result.rowcount  # type: ignore[return-value]
```

Also add `delete` to the imports at the top of the file:

```python
from sqlalchemy import delete, select, update
```

- [ ] **Step 4: Add `delete_for_documents` to ChunkRepository**

Add to `api/app/repositories/chunk.py` after the existing `delete_for_document` method:

```python
    async def delete_for_documents(self, doc_ids: list[uuid.UUID]) -> None:
        await self._s.execute(
            delete(DocumentChunk).where(DocumentChunk.document_id.in_(doc_ids))
        )
        await self._s.flush()
```

- [ ] **Step 5: Add `delete_objects` and `presign_download` to storage service**

Add to `api/app/services/storage.py` after the existing `sha256_of_bytes` function:

```python
def delete_objects(r2_keys: list[str]) -> None:
    if not r2_keys:
        return
    client = _client()
    objects = [{"Key": k} for k in r2_keys]
    client.delete_objects(
        Bucket=settings.R2_BUCKET, Delete={"Objects": objects, "Quiet": True}
    )


def presign_download(r2_key: str) -> str:
    client = _client()
    return client.generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.R2_BUCKET, "Key": r2_key},
        ExpiresIn=_PRESIGN_EXPIRY,
    )
```

- [ ] **Step 6: Run tests to verify they pass**

Run:

```bash
cd api && uv run pytest tests/unit/test_bulk_repository.py -v
```

Expected: all 3 tests PASS.

- [ ] **Step 7: Commit**

```bash
git add api/app/repositories/document.py api/app/repositories/chunk.py api/app/services/storage.py api/tests/unit/test_bulk_repository.py
git commit -m "feat(api): add bulk repository methods for get/delete by IDs"
```

---

### Task 3: Add bulk schemas

**Files:**

- Modify: `api/app/schemas/document.py`

**Interfaces:**

- Consumes: nothing
- Produces:
  - `BulkDocumentRequest` — `document_ids: list[uuid.UUID]`, validated 1–100 items
  - `BulkDeleteResponse` — `deleted: int`

- [ ] **Step 1: Add bulk schemas to document schemas**

Add at the end of `api/app/schemas/document.py`:

```python
from pydantic import field_validator


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
```

Note: the `field_validator` import should be added alongside the existing `BaseModel` import from pydantic. Restructure the import block to:

```python
from pydantic import BaseModel, field_validator
```

- [ ] **Step 2: Verify import works**

Run:

```bash
cd api && uv run python -c "from app.schemas.document import BulkDocumentRequest, BulkDeleteResponse; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add api/app/schemas/document.py
git commit -m "feat(api): add BulkDocumentRequest and BulkDeleteResponse schemas"
```

---

### Task 4: Bulk delete endpoint

**Files:**

- Modify: `api/app/api/v1/documents.py`
- Create: `api/tests/integration/test_bulk_actions.py`

**Interfaces:**

- Consumes: `BulkDocumentRequest`, `BulkDeleteResponse`, `DocumentRepository.get_by_ids`, `DocumentRepository.delete_by_ids`, `ChunkRepository.delete_for_documents`, `storage.delete_objects`
- Produces: `POST /api/v1/documents/bulk/delete` endpoint

- [ ] **Step 1: Write failing integration test for bulk delete**

Create `api/tests/integration/test_bulk_actions.py`:

```python
"""Bulk actions integration tests.

R2 storage operations are mocked.
"""

import uuid
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


async def _register(client: AsyncClient, suffix: str = "") -> str:
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "org_name": f"Bulk Org {suffix}",
            "email": f"bulk{suffix}@test.com",
            "password": "bulkpass12345",
        },
    )
    assert resp.status_code == 201, resp.text
    token = resp.json()["access_token"]
    client.headers["Authorization"] = f"Bearer {token}"
    return token


async def _create_doc(client: AsyncClient, filename: str) -> str:
    with patch(
        "app.services.storage.presign_upload",
        return_value="https://r2.example/up",
    ):
        resp = await client.post(
            "/api/v1/documents/upload-url",
            json={
                "filename": filename,
                "content_type": "application/pdf",
                "size_bytes": 1024,
            },
        )
    assert resp.status_code == 201
    return resp.json()["document_id"]


@pytest.mark.asyncio
async def test_bulk_delete_removes_documents(client: AsyncClient) -> None:
    await _register(client, "del1")
    doc1 = await _create_doc(client, "file1.pdf")
    doc2 = await _create_doc(client, "file2.pdf")

    with patch("app.services.storage.delete_objects"):
        resp = await client.post(
            "/api/v1/documents/bulk/delete",
            json={"document_ids": [doc1, doc2]},
        )
    assert resp.status_code == 200
    assert resp.json()["deleted"] == 2

    list_resp = await client.get("/api/v1/documents")
    assert len(list_resp.json()) == 0


@pytest.mark.asyncio
async def test_bulk_delete_empty_list_returns_400(client: AsyncClient) -> None:
    await _register(client, "del2")
    resp = await client.post(
        "/api/v1/documents/bulk/delete",
        json={"document_ids": []},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_bulk_delete_cross_org_returns_404(
    client: AsyncClient,
) -> None:
    await _register(client, "del3a")
    doc_a = await _create_doc(client, "secret.pdf")

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client_b:
        await _register(client_b, "del3b")
        with patch("app.services.storage.delete_objects"):
            resp = await client_b.post(
                "/api/v1/documents/bulk/delete",
                json={"document_ids": [doc_a]},
            )
        assert resp.status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd api && uv run pytest tests/integration/test_bulk_actions.py::test_bulk_delete_removes_documents -v
```

Expected: FAIL — 404 or 405 (route doesn't exist yet).

- [ ] **Step 3: Implement the bulk delete endpoint**

Add to `api/app/api/v1/documents.py`. First update the imports at the top:

```python
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
    DocumentDetailResponse,
    DocumentResponse,
    UploadConfirmRequest,
    UploadInitRequest,
    UploadInitResponse,
)
from app.services import storage, upload as upload_service

logger = logging.getLogger(__name__)
```

Then add the endpoint after the existing `stream_document_status` function:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
cd api && uv run pytest tests/integration/test_bulk_actions.py -v
```

Expected: all 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add api/app/api/v1/documents.py api/tests/integration/test_bulk_actions.py
git commit -m "feat(api): bulk delete endpoint with org isolation"
```

---

### Task 5: Bulk download (ZIP) endpoint

**Files:**

- Modify: `api/app/api/v1/documents.py`
- Modify: `api/tests/integration/test_bulk_actions.py`

**Interfaces:**

- Consumes: `BulkDocumentRequest`, `DocumentRepository.get_by_ids`, `storage.get_object_bytes`
- Produces: `POST /api/v1/documents/bulk/download` — streams ZIP file

- [ ] **Step 1: Write failing test for bulk download**

Add to `api/tests/integration/test_bulk_actions.py`:

```python
@pytest.mark.asyncio
async def test_bulk_download_returns_zip(client: AsyncClient) -> None:
    await _register(client, "dl1")
    doc1 = await _create_doc(client, "report.pdf")

    with patch(
        "app.services.storage.get_object_bytes",
        return_value=b"%PDF-1.4 fake content",
    ):
        resp = await client.post(
            "/api/v1/documents/bulk/download",
            json={"document_ids": [doc1]},
        )
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/zip"
    assert "documents-" in resp.headers["content-disposition"]
    assert len(resp.content) > 0


@pytest.mark.asyncio
async def test_bulk_download_exceeds_limit_returns_400(
    client: AsyncClient,
) -> None:
    await _register(client, "dl2")
    ids = []
    for i in range(21):
        ids.append(await _create_doc(client, f"file{i}.pdf"))

    resp = await client.post(
        "/api/v1/documents/bulk/download",
        json={"document_ids": ids},
    )
    assert resp.status_code == 400
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd api && uv run pytest tests/integration/test_bulk_actions.py::test_bulk_download_returns_zip -v
```

Expected: FAIL — route doesn't exist.

- [ ] **Step 3: Implement the bulk download endpoint**

Add to `api/app/api/v1/documents.py` after the `bulk_delete` function:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
cd api && uv run pytest tests/integration/test_bulk_actions.py -v -k "download"
```

Expected: both download tests PASS.

- [ ] **Step 5: Commit**

```bash
git add api/app/api/v1/documents.py api/tests/integration/test_bulk_actions.py
git commit -m "feat(api): bulk download endpoint — streams ZIP of selected documents"
```

---

### Task 6: Excel export endpoint

**Files:**

- Modify: `api/app/api/v1/documents.py`
- Modify: `api/tests/integration/test_bulk_actions.py`

**Interfaces:**

- Consumes: `BulkDocumentRequest`, `DocumentRepository.get_by_ids`, `openpyxl`
- Produces: `POST /api/v1/documents/bulk/export` — streams .xlsx file

- [ ] **Step 1: Write failing test for Excel export**

Add to `api/tests/integration/test_bulk_actions.py`:

```python
@pytest.mark.asyncio
async def test_bulk_export_returns_xlsx(client: AsyncClient) -> None:
    await _register(client, "exp1")
    doc1 = await _create_doc(client, "invoice.pdf")

    resp = await client.post(
        "/api/v1/documents/bulk/export",
        json={"document_ids": [doc1]},
    )
    assert resp.status_code == 200
    assert (
        "spreadsheetml" in resp.headers["content-type"]
        or "application/vnd" in resp.headers["content-type"]
    )
    assert "documents-export-" in resp.headers["content-disposition"]

    import io
    import openpyxl

    wb = openpyxl.load_workbook(io.BytesIO(resp.content))
    ws = wb.active
    headers = [cell.value for cell in ws[1]]
    assert "Filename" in headers
    assert "Type" in headers
    assert "Status" in headers
    assert ws.cell(row=2, column=1).value == "invoice.pdf"


@pytest.mark.asyncio
async def test_bulk_export_cross_org_returns_404(client: AsyncClient) -> None:
    await _register(client, "exp2a")
    doc_a = await _create_doc(client, "secret.pdf")

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client_b:
        await _register(client_b, "exp2b")
        resp = await client_b.post(
            "/api/v1/documents/bulk/export",
            json={"document_ids": [doc_a]},
        )
        assert resp.status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd api && uv run pytest tests/integration/test_bulk_actions.py::test_bulk_export_returns_xlsx -v
```

Expected: FAIL — route doesn't exist.

- [ ] **Step 3: Implement the Excel export endpoint**

Add to `api/app/api/v1/documents.py` after the `bulk_download` function:

```python
_EXCEL_TEXT_LIMIT = 32000  # Excel cell character limit


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
        ws.append([
            doc.filename,
            doc.mime_type,
            round(doc.size_bytes / 1024, 1),
            doc.page_count,
            doc.status,
            doc.created_at.isoformat() if doc.created_at else "",
            text,
        ])

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
```

- [ ] **Step 4: Run all bulk action tests**

Run:

```bash
cd api && uv run pytest tests/integration/test_bulk_actions.py -v
```

Expected: all tests PASS (delete, download, export).

- [ ] **Step 5: Run linter**

Run:

```bash
cd api && uv run ruff check app/api/v1/documents.py && uv run ruff format app/api/v1/documents.py
```

Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add api/app/api/v1/documents.py api/tests/integration/test_bulk_actions.py
git commit -m "feat(api): Excel export endpoint with metadata + extracted text"
```

---

### Task 7: Multi-file UploadZone component

**Files:**

- Modify: `web/components/UploadZone.tsx`

**Interfaces:**

- Consumes: existing `getAccessToken()`, existing upload API endpoints
- Produces: `UploadZone` component that accepts multiple files, shows per-file progress, limits concurrency to 3

- [ ] **Step 1: Rewrite UploadZone with multi-file support**

Replace the entire content of `web/components/UploadZone.tsx`:

```tsx
"use client";

import { useState, useRef, useCallback } from "react";
import { getAccessToken } from "@/lib/auth";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const ALLOWED_TYPES = [
  "application/pdf",
  "image/jpeg",
  "image/png",
  "image/tiff",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
];
const MAX_CONCURRENT = 3;

type FileStatus =
  | "pending"
  | "requesting"
  | "uploading"
  | "processing"
  | "done"
  | "error";

interface UploadItem {
  id: string;
  file: File;
  status: FileStatus;
  progress: number;
  error?: string;
  docId?: string;
}

export default function UploadZone({
  onUploadComplete,
}: {
  onUploadComplete?: () => void;
}) {
  const [items, setItems] = useState<UploadItem[]>([]);
  const [dragOver, setDragOver] = useState(false);
  const activeRef = useRef(0);
  const queueRef = useRef<UploadItem[]>([]);

  const updateItem = useCallback((id: string, patch: Partial<UploadItem>) => {
    setItems((prev) =>
      prev.map((it) => (it.id === id ? { ...it, ...patch } : it)),
    );
  }, []);

  const processNext = useCallback(() => {
    if (activeRef.current >= MAX_CONCURRENT) return;
    const next = queueRef.current.shift();
    if (!next) return;
    activeRef.current++;
    uploadFile(next).finally(() => {
      activeRef.current--;
      processNext();
    });
  }, []);

  async function uploadFile(item: UploadItem) {
    const token = getAccessToken();
    try {
      updateItem(item.id, { status: "requesting", progress: 10 });
      const initRes = await fetch(`${API}/api/v1/documents/upload-url`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          filename: item.file.name,
          content_type: item.file.type,
          size_bytes: item.file.size,
        }),
      });
      if (!initRes.ok) {
        updateItem(item.id, { status: "error", error: await initRes.text() });
        return;
      }
      const { document_id, upload_url } = await initRes.json();
      updateItem(item.id, {
        status: "uploading",
        progress: 30,
        docId: document_id,
      });

      const uploadRes = await fetch(upload_url, {
        method: "PUT",
        headers: { "Content-Type": item.file.type },
        body: item.file,
      });
      if (!uploadRes.ok) {
        updateItem(item.id, {
          status: "error",
          error: "Upload to storage failed",
        });
        return;
      }
      updateItem(item.id, { progress: 60 });

      const confirmRes = await fetch(`${API}/api/v1/documents/confirm`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ document_id }),
      });
      if (!confirmRes.ok) {
        updateItem(item.id, {
          status: "error",
          error: await confirmRes.text(),
        });
        return;
      }

      updateItem(item.id, { status: "processing", progress: 80 });

      for (let i = 0; i < 150; i++) {
        await new Promise((r) => setTimeout(r, 2000));
        try {
          const res = await fetch(`${API}/api/v1/documents/${document_id}`, {
            headers: { Authorization: `Bearer ${token}` },
          });
          if (!res.ok) continue;
          const doc = await res.json();
          if (doc.status === "ready" || doc.status === "indexed") {
            updateItem(item.id, { status: "done", progress: 100 });
            onUploadComplete?.();
            return;
          }
          if (doc.status === "failed") {
            updateItem(item.id, {
              status: "error",
              error: doc.error_message ?? "Processing failed",
            });
            return;
          }
        } catch {
          continue;
        }
      }
    } catch (err) {
      updateItem(item.id, {
        status: "error",
        error: err instanceof Error ? err.message : "Unknown error",
      });
    }
  }

  function handleFiles(files: FileList) {
    const newItems: UploadItem[] = [];
    for (let i = 0; i < files.length; i++) {
      const file = files[i];
      if (!ALLOWED_TYPES.includes(file.type)) continue;
      if (file.size > 50 * 1024 * 1024) continue;
      newItems.push({
        id: crypto.randomUUID(),
        file,
        status: "pending",
        progress: 0,
      });
    }
    setItems((prev) => [...prev, ...newItems]);
    queueRef.current.push(...newItems);
    for (let i = 0; i < MAX_CONCURRENT; i++) processNext();
  }

  function cancelPending() {
    queueRef.current = [];
    setItems((prev) => prev.filter((it) => it.status !== "pending"));
  }

  function clearCompleted() {
    setItems((prev) =>
      prev.filter((it) => it.status !== "done" && it.status !== "error"),
    );
  }

  const doneCount = items.filter((it) => it.status === "done").length;
  const totalCount = items.length;
  const hasItems = totalCount > 0;

  const statusIcon: Record<FileStatus, { color: string; symbol: string }> = {
    pending: { color: "var(--gray-400)", symbol: "⏳" },
    requesting: { color: "var(--brand-500)", symbol: "⟳" },
    uploading: { color: "var(--brand-600)", symbol: "↑" },
    processing: { color: "var(--amber-600)", symbol: "⟳" },
    done: { color: "var(--green-600)", symbol: "✓" },
    error: { color: "var(--red-600)", symbol: "✕" },
  };

  return (
    <div>
      <div
        onDrop={(e) => {
          e.preventDefault();
          setDragOver(false);
          if (e.dataTransfer.files.length) handleFiles(e.dataTransfer.files);
        }}
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        style={{
          border: `2px dashed ${dragOver ? "var(--brand-400)" : "var(--gray-300)"}`,
          borderRadius: "var(--radius-md)",
          padding: "2rem 1.5rem",
          textAlign: "center",
          background: dragOver ? "var(--brand-50)" : "#fff",
          transition: "all 0.15s",
          cursor: "pointer",
        }}
      >
        <svg
          width="40"
          height="40"
          fill="none"
          stroke="var(--gray-400)"
          strokeWidth="1.5"
          viewBox="0 0 24 24"
          style={{ margin: "0 auto 0.75rem" }}
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"
          />
        </svg>
        <p
          style={{
            fontWeight: 500,
            color: "var(--gray-700)",
            marginBottom: "0.35rem",
          }}
        >
          Drop files here, or{" "}
          <label
            style={{
              color: "var(--brand-600)",
              cursor: "pointer",
              fontWeight: 600,
            }}
          >
            browse
            <input
              type="file"
              multiple
              accept=".pdf,.jpg,.jpeg,.png,.tiff,.docx"
              onChange={(e) => {
                if (e.target.files?.length) handleFiles(e.target.files);
                e.target.value = "";
              }}
              style={{ display: "none" }}
            />
          </label>
        </p>
        <p style={{ fontSize: "0.8rem", color: "var(--gray-400)" }}>
          PDF, JPG, PNG, TIFF, or DOCX up to 50 MB each
        </p>
      </div>

      {hasItems && (
        <div style={{ marginTop: "1rem" }}>
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              marginBottom: "0.5rem",
            }}
          >
            <span
              style={{
                fontSize: "0.85rem",
                color: "var(--gray-600)",
                fontWeight: 500,
              }}
            >
              {doneCount} of {totalCount} uploaded
            </span>
            <div style={{ display: "flex", gap: "0.5rem" }}>
              {queueRef.current.length > 0 && (
                <button
                  onClick={cancelPending}
                  className="btn-ghost"
                  style={{ fontSize: "0.78rem", color: "var(--red-600)" }}
                >
                  Cancel pending
                </button>
              )}
              {(doneCount > 0 || items.some((it) => it.status === "error")) && (
                <button
                  onClick={clearCompleted}
                  className="btn-ghost"
                  style={{ fontSize: "0.78rem" }}
                >
                  Clear finished
                </button>
              )}
            </div>
          </div>

          <div
            style={{ display: "flex", flexDirection: "column", gap: "0.35rem" }}
          >
            {items.map((item) => (
              <div
                key={item.id}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "0.75rem",
                  padding: "0.5rem 0.75rem",
                  background: "var(--gray-50)",
                  borderRadius: "var(--radius-sm)",
                  border: "1px solid var(--gray-100)",
                }}
              >
                <span
                  style={{
                    color: statusIcon[item.status].color,
                    fontWeight: 700,
                    fontSize: "0.9rem",
                    width: 20,
                    textAlign: "center",
                  }}
                >
                  {statusIcon[item.status].symbol}
                </span>
                <span
                  style={{
                    flex: 1,
                    fontSize: "0.85rem",
                    color: "var(--gray-700)",
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                  }}
                >
                  {item.file.name}
                </span>
                <div
                  style={{
                    width: 100,
                    height: 6,
                    background: "var(--gray-200)",
                    borderRadius: 3,
                    overflow: "hidden",
                  }}
                >
                  <div
                    style={{
                      width: `${item.progress}%`,
                      height: "100%",
                      background:
                        item.status === "error"
                          ? "var(--red-500)"
                          : item.status === "done"
                            ? "var(--green-500)"
                            : "var(--brand-500)",
                      transition: "width 0.3s",
                    }}
                  />
                </div>
                {item.error && (
                  <span
                    style={{
                      fontSize: "0.75rem",
                      color: "var(--red-600)",
                      maxWidth: 150,
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      whiteSpace: "nowrap",
                    }}
                    title={item.error}
                  >
                    {item.error}
                  </span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Update dashboard to pass onUploadComplete**

In `web/app/dashboard/page.tsx`, the `<UploadZone />` call doesn't pass `onUploadComplete` yet. This is fine — the prop is optional. No changes needed for this task.

- [ ] **Step 3: Test in browser**

Run the dev server:

```bash
cd web && npm run dev
```

Verify:

1. Drop multiple files — each shows its own progress row
2. Only 3 upload simultaneously, rest queue as "pending"
3. "Cancel pending" button appears and clears the queue
4. "Clear finished" removes completed/errored items
5. Single file upload still works as before

- [ ] **Step 4: Commit**

```bash
git add web/components/UploadZone.tsx
git commit -m "feat(web): multi-file upload with per-file progress and concurrency limit"
```

---

### Task 8: Document selection and bulk action toolbar

**Files:**

- Modify: `web/components/DocumentList.tsx`
- Create: `web/components/ConfirmDeleteModal.tsx`

**Interfaces:**

- Consumes: existing `Document` interface, `getAccessToken()`, bulk API endpoints
- Produces: `DocumentList` with checkboxes, select-all, shift+click, floating action toolbar, `ConfirmDeleteModal`

- [ ] **Step 1: Create the ConfirmDeleteModal component**

Create `web/components/ConfirmDeleteModal.tsx`:

```tsx
"use client";

import { useState } from "react";

interface Props {
  documentNames: string[];
  onConfirm: () => Promise<void>;
  onCancel: () => void;
}

export default function ConfirmDeleteModal({
  documentNames,
  onConfirm,
  onCancel,
}: Props) {
  const [loading, setLoading] = useState(false);

  async function handleConfirm() {
    setLoading(true);
    try {
      await onConfirm();
    } finally {
      setLoading(false);
    }
  }

  const displayNames = documentNames.slice(0, 10);
  const remaining = documentNames.length - displayNames.length;

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 100,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: "rgba(0,0,0,0.4)",
        backdropFilter: "blur(2px)",
      }}
      onClick={onCancel}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: "#fff",
          borderRadius: "var(--radius-lg)",
          padding: "1.5rem",
          width: "100%",
          maxWidth: 440,
          boxShadow: "0 20px 60px rgba(0,0,0,0.15)",
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "0.75rem",
            marginBottom: "1rem",
          }}
        >
          <div
            style={{
              width: 40,
              height: 40,
              borderRadius: "50%",
              background: "var(--red-50)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            <svg
              width="20"
              height="20"
              fill="none"
              stroke="var(--red-600)"
              strokeWidth="2"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
              />
            </svg>
          </div>
          <div>
            <h3
              style={{
                fontWeight: 600,
                color: "var(--gray-900)",
                fontSize: "1.05rem",
              }}
            >
              Delete {documentNames.length} document
              {documentNames.length !== 1 ? "s" : ""}?
            </h3>
            <p style={{ fontSize: "0.85rem", color: "var(--gray-500)" }}>
              This action cannot be undone.
            </p>
          </div>
        </div>

        <div
          style={{
            maxHeight: 200,
            overflowY: "auto",
            marginBottom: "1.25rem",
            padding: "0.75rem",
            background: "var(--gray-50)",
            borderRadius: "var(--radius-sm)",
            border: "1px solid var(--gray-100)",
          }}
        >
          {displayNames.map((name, i) => (
            <div
              key={i}
              style={{
                fontSize: "0.85rem",
                color: "var(--gray-700)",
                padding: "0.25rem 0",
                borderBottom:
                  i < displayNames.length - 1
                    ? "1px solid var(--gray-100)"
                    : "none",
              }}
            >
              {name}
            </div>
          ))}
          {remaining > 0 && (
            <div
              style={{
                fontSize: "0.82rem",
                color: "var(--gray-400)",
                padding: "0.35rem 0",
                fontStyle: "italic",
              }}
            >
              +{remaining} more
            </div>
          )}
        </div>

        <div
          style={{
            display: "flex",
            gap: "0.75rem",
            justifyContent: "flex-end",
          }}
        >
          <button
            onClick={onCancel}
            disabled={loading}
            className="btn-secondary"
            style={{ padding: "0.5rem 1.25rem" }}
          >
            Cancel
          </button>
          <button
            onClick={handleConfirm}
            disabled={loading}
            style={{
              padding: "0.5rem 1.25rem",
              borderRadius: "var(--radius-md)",
              border: "none",
              background: "var(--red-600)",
              color: "#fff",
              fontWeight: 600,
              cursor: loading ? "not-allowed" : "pointer",
              opacity: loading ? 0.6 : 1,
            }}
          >
            {loading ? "Deleting..." : "Delete permanently"}
          </button>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Rewrite DocumentList with selection and bulk actions**

Replace the entire content of `web/components/DocumentList.tsx`:

```tsx
"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import { getAccessToken } from "@/lib/auth";
import ConfirmDeleteModal from "./ConfirmDeleteModal";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface Document {
  id: string;
  filename: string;
  mime_type: string;
  size_bytes: number;
  status: string;
  page_count: number | null;
  error_message: string | null;
  created_at: string;
  extracted_text?: string | null;
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

const BADGE_CLASS: Record<string, string> = {
  ready: "badge-ready",
  indexed: "badge-indexed",
  processing: "badge-processing",
  uploaded: "badge-uploaded",
  failed: "badge-failed",
};

interface Props {
  onSelectDocument?: (doc: Document | null) => void;
  selectedId?: string | null;
  refreshKey?: number;
}

export default function DocumentList({
  onSelectDocument,
  selectedId,
  refreshKey,
}: Props) {
  const [docs, setDocs] = useState<Document[]>([]);
  const [loading, setLoading] = useState(true);
  const [detail, setDetail] = useState<Document | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  // Selection state
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const lastClickedRef = useRef<string | null>(null);
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [actionLoading, setActionLoading] = useState<string | null>(null);

  const fetchDocs = useCallback(async () => {
    const token = getAccessToken();
    if (!token) return;
    try {
      const res = await fetch(`${API}/api/v1/documents`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) setDocs(await res.json());
    } catch {
      /* ignore */
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchDocs();
  }, [fetchDocs, refreshKey]);

  function handleCheckbox(docId: string, e: React.MouseEvent) {
    e.stopPropagation();
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (e.shiftKey && lastClickedRef.current) {
        const ids = docs.map((d) => d.id);
        const start = ids.indexOf(lastClickedRef.current);
        const end = ids.indexOf(docId);
        const [lo, hi] = start < end ? [start, end] : [end, start];
        for (let i = lo; i <= hi; i++) next.add(ids[i]);
      } else if (next.has(docId)) {
        next.delete(docId);
      } else {
        next.add(docId);
      }
      return next;
    });
    lastClickedRef.current = docId;
  }

  function handleSelectAll() {
    if (selectedIds.size === docs.length) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(docs.map((d) => d.id)));
    }
  }

  async function handleSelect(doc: Document) {
    if (detail?.id === doc.id) {
      setDetail(null);
      onSelectDocument?.(null);
      return;
    }
    setDetailLoading(true);
    const token = getAccessToken();
    try {
      const res = await fetch(`${API}/api/v1/documents/${doc.id}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const full = await res.json();
        setDetail(full);
        onSelectDocument?.(full);
      }
    } catch {
      /* ignore */
    } finally {
      setDetailLoading(false);
    }
  }

  async function handleBulkDelete() {
    const token = getAccessToken();
    const ids = Array.from(selectedIds);
    try {
      const res = await fetch(`${API}/api/v1/documents/bulk/delete`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ document_ids: ids }),
      });
      if (res.ok) {
        setSelectedIds(new Set());
        setShowDeleteModal(false);
        setDetail(null);
        await fetchDocs();
      }
    } catch {
      /* ignore */
    }
  }

  async function handleBulkDownload() {
    const token = getAccessToken();
    const ids = Array.from(selectedIds);
    setActionLoading("download");
    try {
      const res = await fetch(`${API}/api/v1/documents/bulk/download`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ document_ids: ids }),
      });
      if (res.ok) {
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download =
          res.headers
            .get("content-disposition")
            ?.split("filename=")[1]
            ?.replace(/"/g, "") || "documents.zip";
        a.click();
        URL.revokeObjectURL(url);
      }
    } catch {
      /* ignore */
    } finally {
      setActionLoading(null);
    }
  }

  async function handleBulkExport() {
    const token = getAccessToken();
    const ids = Array.from(selectedIds);
    setActionLoading("export");
    try {
      const res = await fetch(`${API}/api/v1/documents/bulk/export`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ document_ids: ids }),
      });
      if (res.ok) {
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download =
          res.headers
            .get("content-disposition")
            ?.split("filename=")[1]
            ?.replace(/"/g, "") || "documents.xlsx";
        a.click();
        URL.revokeObjectURL(url);
      }
    } catch {
      /* ignore */
    } finally {
      setActionLoading(null);
    }
  }

  if (loading)
    return (
      <div
        style={{
          padding: "2rem",
          textAlign: "center",
          color: "var(--gray-400)",
        }}
      >
        Loading documents...
      </div>
    );

  if (docs.length === 0) {
    return (
      <div style={{ padding: "2.5rem", textAlign: "center" }}>
        <svg
          width="48"
          height="48"
          fill="none"
          stroke="var(--gray-300)"
          strokeWidth="1.5"
          viewBox="0 0 24 24"
          style={{ margin: "0 auto 0.75rem" }}
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
          />
        </svg>
        <p style={{ color: "var(--gray-500)", fontWeight: 500 }}>
          No documents yet
        </p>
        <p style={{ color: "var(--gray-400)", fontSize: "0.85rem" }}>
          Upload your first document to get started
        </p>
      </div>
    );
  }

  const selectAllState =
    selectedIds.size === 0
      ? "none"
      : selectedIds.size === docs.length
        ? "all"
        : "some";

  return (
    <div>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: "0.75rem",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
          <input
            type="checkbox"
            checked={selectAllState === "all"}
            ref={(el) => {
              if (el) el.indeterminate = selectAllState === "some";
            }}
            onChange={handleSelectAll}
            style={{
              width: 16,
              height: 16,
              cursor: "pointer",
              accentColor: "var(--brand-500)",
            }}
          />
          <span style={{ color: "var(--gray-500)", fontSize: "0.85rem" }}>
            {selectedIds.size > 0
              ? `${selectedIds.size} selected`
              : `${docs.length} document${docs.length !== 1 ? "s" : ""}`}
          </span>
        </div>
        <button
          onClick={fetchDocs}
          className="btn-ghost"
          style={{ fontSize: "0.8rem" }}
        >
          Refresh
        </button>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
        {docs.map((doc) => {
          const isExpanded = detail?.id === doc.id || selectedId === doc.id;
          const isChecked = selectedIds.has(doc.id);
          return (
            <div key={doc.id}>
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  padding: "0.75rem 1rem",
                  background: isChecked
                    ? "var(--brand-50)"
                    : isExpanded
                      ? "var(--brand-50)"
                      : "var(--gray-50)",
                  borderRadius: "var(--radius-md)",
                  border: isChecked
                    ? "1.5px solid var(--brand-300)"
                    : isExpanded
                      ? "1.5px solid var(--brand-300)"
                      : "1px solid var(--gray-100)",
                  cursor: "pointer",
                  transition: "all 0.15s",
                }}
              >
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "0.75rem",
                    flex: 1,
                    minWidth: 0,
                  }}
                >
                  <input
                    type="checkbox"
                    checked={isChecked}
                    onClick={(e) => handleCheckbox(doc.id, e)}
                    onChange={() => {}}
                    style={{
                      width: 16,
                      height: 16,
                      cursor: "pointer",
                      accentColor: "var(--brand-500)",
                      flexShrink: 0,
                    }}
                  />
                  <div
                    onClick={() => handleSelect(doc)}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: "0.75rem",
                      flex: 1,
                      minWidth: 0,
                    }}
                  >
                    <div
                      style={{
                        width: 36,
                        height: 36,
                        borderRadius: "var(--radius-sm)",
                        background: isChecked
                          ? "var(--brand-100)"
                          : "var(--brand-50)",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        flexShrink: 0,
                      }}
                    >
                      <svg
                        width="18"
                        height="18"
                        fill="none"
                        stroke="var(--brand-500)"
                        strokeWidth="2"
                        viewBox="0 0 24 24"
                      >
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
                        />
                      </svg>
                    </div>
                    <div style={{ minWidth: 0 }}>
                      <p
                        style={{
                          fontWeight: 500,
                          fontSize: "0.9rem",
                          color: "var(--gray-800)",
                          whiteSpace: "nowrap",
                          overflow: "hidden",
                          textOverflow: "ellipsis",
                        }}
                      >
                        {doc.filename}
                      </p>
                      <p
                        style={{
                          fontSize: "0.78rem",
                          color: "var(--gray-400)",
                        }}
                      >
                        {formatBytes(doc.size_bytes)}
                        {doc.page_count
                          ? ` · ${doc.page_count} pages`
                          : ""} ·{" "}
                        {new Date(doc.created_at).toLocaleDateString()}
                      </p>
                    </div>
                  </div>
                </div>
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "0.5rem",
                  }}
                  onClick={() => handleSelect(doc)}
                >
                  <span
                    className={`badge ${BADGE_CLASS[doc.status] ?? "badge-uploaded"}`}
                  >
                    {doc.status}
                  </span>
                  <svg
                    width="16"
                    height="16"
                    fill="none"
                    stroke="var(--gray-400)"
                    strokeWidth="2"
                    viewBox="0 0 24 24"
                    style={{
                      transform: isExpanded ? "rotate(180deg)" : "rotate(0)",
                      transition: "transform 0.2s",
                    }}
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      d="M19 9l-7 7-7-7"
                    />
                  </svg>
                </div>
              </div>

              {isExpanded && detail && detail.id === doc.id && (
                <div
                  style={{
                    margin: "0.25rem 0 0.5rem",
                    padding: "1rem 1.25rem",
                    background: "#fff",
                    border: "1px solid var(--gray-200)",
                    borderRadius: "var(--radius-md)",
                    fontSize: "0.88rem",
                  }}
                >
                  <div
                    style={{
                      display: "flex",
                      gap: "2rem",
                      marginBottom: "1rem",
                      flexWrap: "wrap",
                    }}
                  >
                    <div>
                      <span
                        style={{
                          color: "var(--gray-400)",
                          fontSize: "0.78rem",
                        }}
                      >
                        Type
                      </span>
                      <p style={{ fontWeight: 500, color: "var(--gray-700)" }}>
                        {detail.mime_type}
                      </p>
                    </div>
                    <div>
                      <span
                        style={{
                          color: "var(--gray-400)",
                          fontSize: "0.78rem",
                        }}
                      >
                        Pages
                      </span>
                      <p style={{ fontWeight: 500, color: "var(--gray-700)" }}>
                        {detail.page_count ?? "—"}
                      </p>
                    </div>
                    <div>
                      <span
                        style={{
                          color: "var(--gray-400)",
                          fontSize: "0.78rem",
                        }}
                      >
                        Status
                      </span>
                      <p style={{ fontWeight: 500, color: "var(--gray-700)" }}>
                        {detail.status}
                      </p>
                    </div>
                  </div>
                  {detail.extracted_text ? (
                    <div>
                      <p
                        style={{
                          fontWeight: 600,
                          color: "var(--gray-700)",
                          marginBottom: "0.5rem",
                          fontSize: "0.85rem",
                        }}
                      >
                        Extracted Content
                      </p>
                      <div
                        style={{
                          maxHeight: 300,
                          overflowY: "auto",
                          padding: "0.75rem",
                          background: "var(--gray-50)",
                          borderRadius: "var(--radius-sm)",
                          border: "1px solid var(--gray-100)",
                          whiteSpace: "pre-wrap",
                          fontSize: "0.82rem",
                          lineHeight: 1.7,
                          color: "var(--gray-600)",
                        }}
                      >
                        {detail.extracted_text}
                      </div>
                    </div>
                  ) : (
                    <p
                      style={{ color: "var(--gray-400)", fontSize: "0.85rem" }}
                    >
                      {detail.status === "processing"
                        ? "Document is still being processed..."
                        : "No extracted text available."}
                    </p>
                  )}
                </div>
              )}

              {isExpanded && detailLoading && (
                <div
                  style={{
                    padding: "1rem",
                    textAlign: "center",
                    color: "var(--gray-400)",
                    fontSize: "0.85rem",
                  }}
                >
                  Loading details...
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Bulk Action Toolbar */}
      {selectedIds.size > 0 && (
        <div
          style={{
            position: "sticky",
            bottom: 0,
            marginTop: "1rem",
            padding: "0.75rem 1rem",
            background: "#fff",
            borderRadius: "var(--radius-lg)",
            border: "1px solid var(--gray-200)",
            boxShadow: "0 -4px 20px rgba(0,0,0,0.08)",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
          }}
        >
          <span
            style={{
              fontSize: "0.85rem",
              fontWeight: 600,
              color: "var(--gray-700)",
            }}
          >
            {selectedIds.size} selected
          </span>
          <div style={{ display: "flex", gap: "0.5rem" }}>
            <button
              onClick={() => setShowDeleteModal(true)}
              style={{
                padding: "0.45rem 1rem",
                borderRadius: "var(--radius-md)",
                border: "1px solid var(--red-200)",
                background: "var(--red-50)",
                color: "var(--red-700)",
                fontWeight: 500,
                fontSize: "0.82rem",
                cursor: "pointer",
              }}
            >
              Delete
            </button>
            <button
              onClick={handleBulkDownload}
              disabled={actionLoading === "download"}
              className="btn-secondary"
              style={{ padding: "0.45rem 1rem", fontSize: "0.82rem" }}
            >
              {actionLoading === "download" ? "Zipping..." : "Download ZIP"}
            </button>
            <button
              onClick={handleBulkExport}
              disabled={actionLoading === "export"}
              className="btn-primary"
              style={{ padding: "0.45rem 1rem", fontSize: "0.82rem" }}
            >
              {actionLoading === "export" ? "Exporting..." : "Export Excel"}
            </button>
          </div>
        </div>
      )}

      {showDeleteModal && (
        <ConfirmDeleteModal
          documentNames={docs
            .filter((d) => selectedIds.has(d.id))
            .map((d) => d.filename)}
          onConfirm={handleBulkDelete}
          onCancel={() => setShowDeleteModal(false)}
        />
      )}
    </div>
  );
}
```

- [ ] **Step 3: Test in browser**

Run:

```bash
cd web && npm run dev
```

Verify:

1. Checkboxes appear next to each document
2. "Select all" checkbox in header works (tri-state: none, some, all)
3. Shift+click selects a range of documents
4. Floating toolbar appears when ≥1 document selected
5. Delete button opens confirmation modal with document names
6. Confirming delete removes documents and clears selection
7. Download ZIP triggers file download
8. Export Excel triggers .xlsx download
9. Selection clears after successful action

- [ ] **Step 4: Commit**

```bash
git add web/components/DocumentList.tsx web/components/ConfirmDeleteModal.tsx
git commit -m "feat(web): document selection, bulk action toolbar, and delete confirmation modal"
```

---

### Task 9: Wire UploadZone refresh into dashboard

**Files:**

- Modify: `web/app/dashboard/page.tsx`

**Interfaces:**

- Consumes: `UploadZone` `onUploadComplete` prop, `DocumentList` `refreshKey` prop
- Produces: document list auto-refreshes after uploads complete

- [ ] **Step 1: Add refresh state to dashboard**

In `web/app/dashboard/page.tsx`, add a `refreshKey` state and wire the components together. Replace the Documents tab section (lines 157-171):

```tsx
{
  /* Documents Tab */
}
{
  activeTab === "documents" && <DocumentsTab />;
}
```

And add a `DocumentsTab` component inside the same file, before `DashboardPage`:

```tsx
function DocumentsTab() {
  const [refreshKey, setRefreshKey] = useState(0);
  return (
    <div>
      <div
        className="card"
        style={{ padding: "1.5rem", marginBottom: "1.5rem" }}
      >
        <h2
          style={{
            fontSize: "1.1rem",
            fontWeight: 600,
            color: "var(--gray-900)",
            marginBottom: "1rem",
          }}
        >
          Upload Documents
        </h2>
        <UploadZone onUploadComplete={() => setRefreshKey((k) => k + 1)} />
      </div>
      <div className="card" style={{ padding: "1.5rem" }}>
        <h2
          style={{
            fontSize: "1.1rem",
            fontWeight: 600,
            color: "var(--gray-900)",
            marginBottom: "1rem",
          }}
        >
          Your Documents
        </h2>
        <DocumentList refreshKey={refreshKey} />
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Test in browser**

Verify: after uploading a file and it reaches "done", the document list auto-refreshes to show the new document.

- [ ] **Step 3: Commit**

```bash
git add web/app/dashboard/page.tsx
git commit -m "feat(web): auto-refresh document list after uploads complete"
```

---

### Task 10: End-to-end verification and lint

**Files:**

- All modified files

**Interfaces:**

- Consumes: all previous tasks
- Produces: verified, linted, passing codebase

- [ ] **Step 1: Run backend tests**

```bash
cd api && uv run pytest tests/ -v --tb=short
```

Expected: all tests pass, including new bulk action tests.

- [ ] **Step 2: Run backend linter**

```bash
cd api && uv run ruff check . && uv run ruff format --check .
```

Expected: no lint errors.

- [ ] **Step 3: Run frontend lint**

```bash
cd web && npx eslint . --ext .ts,.tsx
```

Expected: no errors.

- [ ] **Step 4: Run frontend type check**

```bash
cd web && npx tsc --noEmit
```

Expected: no type errors.

- [ ] **Step 5: Manual browser test**

Run both servers and verify the full flow:

1. Login
2. Upload 3+ files at once — all show per-file progress
3. Select all documents → Delete → confirm modal → documents removed
4. Re-upload documents → select some → Download ZIP → verify .zip opens
5. Select documents → Export Excel → open .xlsx in Excel, verify columns and data
6. Verify search and AI tabs still work

- [ ] **Step 6: Final commit if any lint fixes were needed**

```bash
git add -A && git commit -m "chore: lint fixes for bulk upload + actions feature"
```
