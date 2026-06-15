import json
import re
from datetime import UTC, datetime, timedelta

import redis.asyncio as aioredis
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.db import SessionLocal
from app.core.security import (
    create_access_token,
    hash_password,
    make_refresh_token_id,
    refresh_token_redis_key,
    verify_password,
)
from app.models.user import UserRole
from app.repositories.organization import OrgRepository
from app.repositories.user import UserRepository
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse


def _slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


async def _store_refresh_token(
    redis_client: aioredis.Redis,  # type: ignore[type-arg]
    token_id: str,
    user_id: str,
    org_id: str,
    role: str,
) -> None:
    key = refresh_token_redis_key(token_id)
    value = json.dumps({"user_id": user_id, "org_id": org_id, "role": role})
    expire = int(timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS).total_seconds())
    await redis_client.set(key, value, ex=expire)


async def register(body: RegisterRequest, session: AsyncSession) -> TokenResponse:
    org_repo = OrgRepository(session)
    user_repo = UserRepository(session)

    slug = _slugify(body.org_name)
    base_slug = slug
    suffix = 0
    while await org_repo.get_by_slug(slug):
        suffix += 1
        slug = f"{base_slug}-{suffix}"

    org = await org_repo.create(name=body.org_name, slug=slug)
    user = await user_repo.create(
        org_id=org.id,
        email=body.email,
        password_hash=hash_password(body.password),
        role=UserRole.OWNER,
    )

    access_token = create_access_token(str(user.id), str(org.id), user.role.value)
    refresh_id = make_refresh_token_id()

    redis_client = aioredis.from_url(settings.REDIS_URL)
    try:
        await _store_refresh_token(
            redis_client, refresh_id, str(user.id), str(org.id), user.role.value
        )
    finally:
        await redis_client.aclose()

    return TokenResponse(access_token=access_token, refresh_token=refresh_id)


async def login(body: LoginRequest, session: AsyncSession) -> TokenResponse:
    user_repo = UserRepository(session)
    user = await user_repo.get_by_email(body.email)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials"
        )

    if user.locked_until and user.locked_until > datetime.now(UTC):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account temporarily locked",
        )

    if not verify_password(body.password, user.password_hash):
        # Use a separate transaction so the failed-login count is committed
        # even though the outer transaction will rollback on HTTPException.
        async with SessionLocal.begin() as fail_session:
            fail_repo = UserRepository(fail_session)
            fail_user = await fail_repo.get_by_email(body.email)
            if fail_user:
                await fail_repo.increment_failed_login(fail_user)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials"
        )

    await user_repo.reset_failed_login(user)

    access_token = create_access_token(str(user.id), str(user.org_id), user.role.value)
    refresh_id = make_refresh_token_id()

    redis_client = aioredis.from_url(settings.REDIS_URL)
    try:
        await _store_refresh_token(
            redis_client,
            refresh_id,
            str(user.id),
            str(user.org_id),
            user.role.value,
        )
    finally:
        await redis_client.aclose()

    return TokenResponse(access_token=access_token, refresh_token=refresh_id)


async def refresh_tokens(refresh_token_id: str) -> TokenResponse:
    redis_client = aioredis.from_url(settings.REDIS_URL)
    try:
        key = refresh_token_redis_key(refresh_token_id)
        raw = await redis_client.get(key)
        if not raw:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token"
            )

        await redis_client.delete(key)
        data = json.loads(raw)

        new_access = create_access_token(data["user_id"], data["org_id"], data["role"])
        new_refresh_id = make_refresh_token_id()
        await _store_refresh_token(
            redis_client,
            new_refresh_id,
            data["user_id"],
            data["org_id"],
            data["role"],
        )
        return TokenResponse(access_token=new_access, refresh_token=new_refresh_id)
    finally:
        await redis_client.aclose()


async def logout(refresh_token_id: str) -> None:
    redis_client = aioredis.from_url(settings.REDIS_URL)
    try:
        await redis_client.delete(refresh_token_redis_key(refresh_token_id))
    finally:
        await redis_client.aclose()
