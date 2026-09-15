import uuid
from datetime import UTC, datetime

import pytest

from app.core.db import SessionLocal
from app.core.security import hash_password
from app.models.platform_admin import PlatformAdmin
from app.repositories.platform_admin import PlatformAdminRepository


@pytest.mark.asyncio
async def test_get_by_email_and_update_last_login() -> None:
    admin_id = uuid.uuid4()
    async with SessionLocal.begin() as session:
        session.add(
            PlatformAdmin(
                id=admin_id,
                email="repo-test@example.com",
                password_hash=hash_password("password1234"),
            )
        )

    async with SessionLocal.begin() as session:
        repo = PlatformAdminRepository(session)

        found = await repo.get_by_email("repo-test@example.com")
        assert found is not None
        assert found.id == admin_id
        assert found.last_login_at is None

        by_id = await repo.get_by_id(admin_id)
        assert by_id is not None

        before = datetime.now(UTC)
        await repo.update_last_login(found)
        assert found.last_login_at is not None
        assert found.last_login_at >= before

    async with SessionLocal() as session:
        assert (
            await PlatformAdminRepository(session).get_by_email("nobody@example.com")
            is None
        )
