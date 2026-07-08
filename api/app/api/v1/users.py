import uuid

from fastapi import APIRouter, HTTPException, status

from app.core.deps import AuthSession, CurrentUser, CurrentUserDep, require_role
from app.models.user import UserRole
from app.repositories.organization import OrgRepository
from app.repositories.user import UserRepository
from app.schemas.user import (
    UsageResponse,
    UserCreateRequest,
    UserResponse,
    UserUpdateRequest,
)
from app.services import users as users_service

router = APIRouter(prefix="/users", tags=["users"])


@router.post("", response_model=UserResponse, status_code=201)
async def create_user(
    body: UserCreateRequest,
    session: AuthSession,
    current_user: CurrentUser = require_role(UserRole.OWNER, UserRole.ADMIN),
) -> UserResponse:
    user = await users_service.create_org_user(body, current_user, session)
    return UserResponse.model_validate(user)


@router.get("", response_model=list[UserResponse])
async def list_users(
    current_user: CurrentUserDep, session: AuthSession
) -> list[UserResponse]:
    users = await UserRepository(session).list_by_org(current_user.org_id)
    return [UserResponse.model_validate(u) for u in users]


@router.patch("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: uuid.UUID,
    body: UserUpdateRequest,
    session: AuthSession,
    current_user: CurrentUser = require_role(UserRole.OWNER, UserRole.ADMIN),
) -> UserResponse:
    user = await users_service.update_org_user(user_id, body, current_user, session)
    return UserResponse.model_validate(user)


@router.get("/me/usage", response_model=UsageResponse)
async def get_my_usage(
    current_user: CurrentUserDep, session: AuthSession
) -> UsageResponse:
    org = await OrgRepository(session).get_by_id(current_user.org_id)
    if not org:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found"
        )
    return UsageResponse(
        plan=org.plan,
        monthly_page_quota=org.monthly_page_quota,
        pages_used_this_month=org.pages_used_this_month,
        remaining_pages=max(0, org.monthly_page_quota - org.pages_used_this_month),
    )


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: CurrentUserDep, session: AuthSession) -> UserResponse:
    repo = UserRepository(session)
    user = await repo.get_by_id(current_user.user_id, org_id=current_user.org_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )
    return UserResponse.model_validate(user)


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: uuid.UUID,
    current_user: CurrentUserDep,
    session: AuthSession,
) -> UserResponse:
    repo = UserRepository(session)
    # Filter by org_id at application layer (belt-and-suspenders alongside RLS).
    # Returns 404 — never 403 — so callers cannot probe for resource existence.
    user = await repo.get_by_id(user_id, org_id=current_user.org_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )
    return UserResponse.model_validate(user)
