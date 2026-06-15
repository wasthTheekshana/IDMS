import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User, UserRole

_MAX_FAILED = 5
_LOCKOUT_MINUTES = 15


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def create(
        self,
        org_id: uuid.UUID,
        email: str,
        password_hash: str,
        role: UserRole = UserRole.MEMBER,
    ) -> User:
        user = User(
            id=uuid.uuid4(),
            org_id=org_id,
            email=email,
            password_hash=password_hash,
            role=role,
        )
        self._s.add(user)
        await self._s.flush()
        return user

    async def get_by_email(self, email: str) -> User | None:
        result = await self._s.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def get_by_id(
        self, user_id: uuid.UUID, org_id: uuid.UUID | None = None
    ) -> User | None:
        q = select(User).where(User.id == user_id)
        if org_id is not None:
            q = q.where(User.org_id == org_id)
        result = await self._s.execute(q)
        return result.scalar_one_or_none()

    async def increment_failed_login(self, user: User) -> None:
        user.failed_login_count += 1
        if user.failed_login_count >= _MAX_FAILED:
            user.locked_until = datetime.now(UTC) + timedelta(minutes=_LOCKOUT_MINUTES)
        await self._s.flush()

    async def reset_failed_login(self, user: User) -> None:
        user.failed_login_count = 0
        user.locked_until = None
        await self._s.flush()
