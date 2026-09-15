import pytest

from app.core.db import SessionLocal
from app.repositories.platform_admin import PlatformAdminRepository
from app.scripts.create_platform_admin import _create


@pytest.mark.asyncio
async def test_create_inserts_a_platform_admin() -> None:
    await _create("script-test@example.com", "password1234")

    async with SessionLocal() as session:
        found = await PlatformAdminRepository(session).get_by_email(
            "script-test@example.com"
        )
        assert found is not None
        assert found.is_active is True


@pytest.mark.asyncio
async def test_create_refuses_duplicate_email() -> None:
    await _create("dup-test@example.com", "password1234")
    with pytest.raises(SystemExit):
        await _create("dup-test@example.com", "password1234")
