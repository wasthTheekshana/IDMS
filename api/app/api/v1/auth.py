from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_public_db
from app.core.ratelimit import limiter
from app.schemas.auth import (
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
)
from app.services import auth as auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse, status_code=201)
@limiter.limit("5/minute")
async def register(
    request: Request,
    body: RegisterRequest,
    session: AsyncSession = Depends(get_public_db),
) -> TokenResponse:
    return await auth_service.register(body, session)


@router.post("/login", response_model=TokenResponse)
@limiter.limit("10/minute")
async def login(
    request: Request,
    body: LoginRequest,
    session: AsyncSession = Depends(get_public_db),
) -> TokenResponse:
    return await auth_service.login(body, session)


@router.post("/refresh", response_model=TokenResponse)
@limiter.limit("30/minute")
async def refresh(request: Request, body: RefreshRequest) -> TokenResponse:
    return await auth_service.refresh_tokens(body.refresh_token)


@router.post("/logout", status_code=204)
async def logout(body: LogoutRequest) -> None:
    await auth_service.logout(body.refresh_token)
