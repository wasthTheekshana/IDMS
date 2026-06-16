import uuid

from sqlalchemy import and_, select, update
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

    async def get_by_id(self, org_id: uuid.UUID) -> Organization | None:
        result = await self._s.execute(
            select(Organization).where(Organization.id == org_id)
        )
        return result.scalar_one_or_none()

    async def check_and_increment_quota(self, org_id: uuid.UUID, pages: int) -> bool:
        """Atomically check quota and increment. Returns True if allowed."""
        result = await self._s.execute(
            update(Organization)
            .where(
                and_(
                    Organization.id == org_id,
                    Organization.pages_used_this_month + pages
                    <= Organization.monthly_page_quota,
                )
            )
            .values(pages_used_this_month=Organization.pages_used_this_month + pages)
            .returning(Organization.id)
        )
        await self._s.flush()
        return result.scalar_one_or_none() is not None
