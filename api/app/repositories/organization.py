import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.organization import Organization


class OrgRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def create(self, name: str, slug: str) -> Organization:
        org = Organization(id=uuid.uuid4(), name=name, slug=slug)
        self._s.add(org)
        await self._s.flush()
        return org

    async def get_by_slug(self, slug: str) -> Organization | None:
        result = await self._s.execute(
            select(Organization).where(Organization.slug == slug)
        )
        return result.scalar_one_or_none()
