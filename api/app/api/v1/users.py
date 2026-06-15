import uuid

from fastapi import APIRouter, HTTPException, status

from app.core.deps import AuthSession, CurrentUserDep
from app.repositories.user import UserRepository
from app.schemas.user import UserResponse

router = APIRouter(prefix="/users", tags=["users"])


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
