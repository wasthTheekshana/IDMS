import uuid

import pytest
from sqlalchemy import select

from app.core.db import SessionLocal
from app.core.security import hash_password
from app.models.platform_admin import PlatformAdmin


@pytest.mark.asyncio
async def test_platform_admin_round_trips_through_db() -> None:
    admin_id = uuid.uuid4()
    async with SessionLocal.begin() as session:
        session.add(
            PlatformAdmin(
                id=admin_id,
                email="round-trip@example.com",
                password_hash=hash_password("password1234"),
            )
        )

    async with SessionLocal() as session:
        result = await session.execute(
            select(PlatformAdmin).where(PlatformAdmin.id == admin_id)
        )
        admin = result.scalar_one()
        assert admin.email == "round-trip@example.com"
        assert admin.is_active is True
        assert admin.last_login_at is None


@pytest.mark.asyncio
async def test_organization_has_ai_toggle_defaults(auth_client: tuple) -> None:  # type: ignore[type-arg]
    from app.repositories.organization import OrgRepository

    client, tokens = auth_client
    me = await client.get("/api/v1/users/me")
    org_id = uuid.UUID(me.json()["org_id"])

    async with SessionLocal() as session:
        org = await OrgRepository(session).get_by_id(org_id)
        assert org is not None
        assert org.is_suspended is False
        assert org.ai_qa_enabled is True
        assert org.ai_summarization_enabled is True
        assert org.ai_search_answer_enabled is True
        assert org.ai_extraction_enabled is False
