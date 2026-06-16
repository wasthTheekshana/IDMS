"""Document upload flow integration tests.

R2 presign and Celery task dispatch are mocked.
"""

from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


async def _register(client: AsyncClient, suffix: str = "") -> str:
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "org_name": f"Upload Org {suffix}",
            "email": f"uploader{suffix}@test.com",
            "password": "uploadpass123",
        },
    )
    assert resp.status_code == 201, resp.text
    token = resp.json()["access_token"]
    client.headers["Authorization"] = f"Bearer {token}"
    return token


@pytest.mark.asyncio
async def test_init_upload_returns_presigned_url(client: AsyncClient) -> None:
    await _register(client, "a")
    with patch(
        "app.services.storage.presign_upload",
        return_value="https://r2.example/upload",
    ):
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
    assert data["upload_url"] == "https://r2.example/upload"


@pytest.mark.asyncio
async def test_unsupported_mime_type_rejected(client: AsyncClient) -> None:
    await _register(client, "b")
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
    await _register(client, "c")
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
    await _register(client, "d")

    with patch(
        "app.services.storage.presign_upload",
        return_value="https://r2.example/up",
    ):
        init_resp = await client.post(
            "/api/v1/documents/upload-url",
            json={
                "filename": "doc.pdf",
                "content_type": "application/pdf",
                "size_bytes": 2048,
            },
        )
    assert init_resp.status_code == 201
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
    await _register(client, "e")

    with patch(
        "app.services.storage.presign_upload",
        return_value="https://r2.example/up",
    ):
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
    """Org A cannot fetch Org B's document — must return 404."""
    await _register(client, "f1")

    with patch(
        "app.services.storage.presign_upload",
        return_value="https://r2.example/up",
    ):
        init_resp = await client.post(
            "/api/v1/documents/upload-url",
            json={
                "filename": "secret.pdf",
                "content_type": "application/pdf",
                "size_bytes": 1024,
            },
        )
    doc_id_a = init_resp.json()["document_id"]

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client_b:
        reg = await client_b.post(
            "/api/v1/auth/register",
            json={
                "org_name": "Upload Org f2",
                "email": "uploaderf2@test.com",
                "password": "uploadpass123",
            },
        )
        client_b.headers["Authorization"] = f"Bearer {reg.json()['access_token']}"
        resp = await client_b.get(f"/api/v1/documents/{doc_id_a}")
        assert (
            resp.status_code == 404
        ), f"Expected 404 but got {resp.status_code} — cross-tenant document leak"
