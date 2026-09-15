from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient


async def _disable(admin_client: AsyncClient, org_id: str, **flags: bool) -> None:
    resp = await admin_client.patch(
        f"/api/v1/platform-admin/organizations/{org_id}", json=flags
    )
    assert resp.status_code == 200, resp.text


@pytest.mark.asyncio
async def test_qa_disabled_short_circuits_without_calling_llm(
    platform_admin_client: tuple[AsyncClient, dict],  # type: ignore[type-arg]
    auth_client: tuple[AsyncClient, dict],  # type: ignore[type-arg]
) -> None:
    """The org's real GROQ_API_KEY is configured in api/.env, so this must
    mock _call_llm directly (the top-level dispatcher, provider-agnostic) —
    otherwise this test would make a real network call, same trap that
    tests/integration/test_ai.py works around by mocking the LLM call."""
    admin_client, _ = platform_admin_client
    client_a, _ = auth_client

    me = await client_a.get("/api/v1/users/me")
    org_id = me.json()["org_id"]
    await _disable(admin_client, org_id, ai_qa_enabled=False)

    with patch("app.services.ai._call_llm", new_callable=AsyncMock) as mock_call_llm:
        resp = await client_a.post(
            "/api/v1/ai/chat", json={"question": "What is in my documents?"}
        )

    assert resp.status_code == 200
    assert "disabled" in resp.json()["answer"].lower()
    mock_call_llm.assert_not_called()


@pytest.mark.asyncio
async def test_extraction_disabled_by_default_returns_403(
    auth_client: tuple[AsyncClient, dict],  # type: ignore[type-arg]
) -> None:
    """ai_extraction_enabled defaults to False for every new org."""
    client_a, _ = auth_client

    tmpl = await client_a.post(
        "/api/v1/templates",
        json={
            "name": "Invoice",
            "fields": [{"key": "total", "label": "Total", "type": "text"}],
        },
    )
    assert tmpl.status_code == 201, tmpl.text

    import uuid

    resp = await client_a.post(
        "/api/v1/templates/extract",
        json={
            "document_id": str(uuid.uuid4()),
            "template_id": tmpl.json()["id"],
        },
    )
    assert resp.status_code == 403
    assert "disabled" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_extraction_enabled_reaches_not_found_instead_of_disabled(
    platform_admin_client: tuple[AsyncClient, dict],  # type: ignore[type-arg]
    auth_client: tuple[AsyncClient, dict],  # type: ignore[type-arg]
) -> None:
    """Once enabled, a bad document_id now fails for the ORIGINAL reason
    (not found) rather than being blocked by the toggle — proves the toggle
    check runs, and runs before the not-found check would otherwise hide it."""
    admin_client, _ = platform_admin_client
    client_a, _ = auth_client

    me = await client_a.get("/api/v1/users/me")
    org_id = me.json()["org_id"]
    await _disable(admin_client, org_id, ai_extraction_enabled=True)

    tmpl = await client_a.post(
        "/api/v1/templates",
        json={
            "name": "Invoice",
            "fields": [{"key": "total", "label": "Total", "type": "text"}],
        },
    )

    import uuid

    resp = await client_a.post(
        "/api/v1/templates/extract",
        json={
            "document_id": str(uuid.uuid4()),
            "template_id": tmpl.json()["id"],
        },
    )
    assert resp.status_code == 404
