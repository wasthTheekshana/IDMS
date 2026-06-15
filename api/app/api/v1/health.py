from fastapi import APIRouter
from sqlalchemy import text

import redis.asyncio as aioredis

from app.core.config import settings
from app.core.db import SessionLocal

router = APIRouter(tags=["health"])


@router.get("/healthz", summary="Liveness probe")
async def liveness() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz", summary="Readiness probe")
async def readiness() -> dict[str, str]:
    async with SessionLocal() as session:
        await session.execute(text("SELECT 1"))

    client = aioredis.from_url(settings.REDIS_URL, socket_connect_timeout=2)
    try:
        await client.ping()
    finally:
        await client.aclose()

    return {"status": "ready", "db": "ok", "redis": "ok"}
