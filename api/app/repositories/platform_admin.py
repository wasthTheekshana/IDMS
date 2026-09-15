import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.platform_admin import PlatformAdmin


class PlatformAdminRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def get_by_email(self, email: str) -> PlatformAdmin | None:
        result = await self._s.execute(
            select(PlatformAdmin).where(PlatformAdmin.email == email)
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, admin_id: uuid.UUID) -> PlatformAdmin | None:
        result = await self._s.execute(
            select(PlatformAdmin).where(PlatformAdmin.id == admin_id)
        )
        return result.scalar_one_or_none()

    async def update_last_login(self, admin: PlatformAdmin) -> None:
        admin.last_login_at = datetime.now(UTC)
        await self._s.flush()
