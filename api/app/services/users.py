"""Org user management: admin/owner create teammates directly (no invites)."""

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import CurrentUser
from app.core.security import hash_password
from app.models.user import User, UserRole
from app.repositories.user import UserRepository
from app.schemas.user import UserCreateRequest

# Roles each actor is allowed to assign to others.
ASSIGNABLE_ROLES: dict[UserRole, set[UserRole]] = {
    UserRole.OWNER: {UserRole.ADMIN, UserRole.MEMBER, UserRole.VIEWER},
    UserRole.ADMIN: {UserRole.MEMBER, UserRole.VIEWER},
}


def _assignable_by(actor_role: UserRole) -> set[UserRole]:
    return ASSIGNABLE_ROLES.get(actor_role, set())


async def create_org_user(
    body: UserCreateRequest,
    current_user: CurrentUser,
    session: AsyncSession,
) -> User:
    if body.role not in _assignable_by(current_user.role):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Your role cannot create '{body.role.value}' accounts",
        )

    repo = UserRepository(session)
    if await repo.get_by_email(body.email):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this email already exists",
        )

    return await repo.create(
        org_id=current_user.org_id,
        email=body.email,
        password_hash=hash_password(body.password),
        role=body.role,
    )
