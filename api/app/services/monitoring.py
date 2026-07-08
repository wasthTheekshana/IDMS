"""Aggregation helpers for operational monitoring (cost reports, queue depth)."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import redis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.api_usage import ApiUsage

CELERY_QUEUES: tuple[str, ...] = ("ocr", "embed", "ai", "default", "dlq")


@dataclass(frozen=True)
class CostSummary:
    service: str
    total_cost_usd: float
    total_tokens: int
    total_pages: int


async def summarize_api_costs(
    session: AsyncSession, since_hours: int = 24
) -> list[CostSummary]:
    cutoff = datetime.now(UTC) - timedelta(hours=since_hours)
    stmt = (
        select(
            ApiUsage.service,
            func.coalesce(func.sum(ApiUsage.cost_usd), 0.0),
            func.coalesce(func.sum(ApiUsage.tokens_used), 0),
            func.coalesce(func.sum(ApiUsage.pages_used), 0),
        )
        .where(ApiUsage.created_at >= cutoff)
        .group_by(ApiUsage.service)
    )
    result = await session.execute(stmt)
    return [
        CostSummary(
            service=row[0],
            total_cost_usd=round(float(row[1]), 6),
            total_tokens=int(row[2]),
            total_pages=int(row[3]),
        )
        for row in result.all()
    ]


def check_queue_depths(
    queues: Sequence[str] | None = None,
) -> dict[str, int]:
    """Celery queues are Redis lists named after the queue."""
    client = redis.Redis.from_url(settings.REDIS_URL)
    try:
        return {q: int(client.llen(q)) for q in queues or CELERY_QUEUES}
    finally:
        client.close()
