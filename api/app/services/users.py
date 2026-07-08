"""Org user management: admin/owner create teammates directly (no invites)."""

import uuid

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import CurrentUser
from app.core.security import hash_password
from app.models.user import User, UserRole
from app.repositories.user import UserRepository
from app.schemas.user import UserCreateRequest, UserUpdateRequest

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


async def update_org_user(
    user_id: uuid.UUID,
    body: UserUpdateRequest,
    current_user: CurrentUser,
    session: AsyncSession,
) -> User:
    repo = UserRepository(session)
    target = await repo.get_by_id(user_id, org_id=current_user.org_id)
    if not target:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    if target.id == current_user.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Use account settings to modify your own account",
        )
    if target.role == UserRole.OWNER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The organization owner cannot be modified",
        )
    # Actor may only manage users whose current role they could assign
    # (e.g. an admin cannot touch another admin), and may only grant
    # roles from their own assignable set.
    assignable = _assignable_by(current_user.role)
    if target.role not in assignable:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Your role cannot manage '{target.role.value}' accounts",
        )
    if body.role is not None and body.role not in assignable:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Your role cannot grant '{body.role.value}'",
        )

    return await repo.update_user(target, role=body.role, is_active=body.is_active)
