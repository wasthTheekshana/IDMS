import uuid
from datetime import UTC, datetime, timedelta

from app.core.db import SessionLocal
from app.models.api_usage import ApiUsage
from app.models.organization import Organization
from app.services.monitoring import check_queue_depths, summarize_api_costs


async def _seed_usage() -> None:
    async with SessionLocal.begin() as session:
        org = Organization(name="Cost Org", slug=f"cost-{uuid.uuid4().hex[:8]}")
        session.add(org)
        await session.flush()
        session.add_all(
            [
                ApiUsage(org_id=org.id, service="ocr", pages_used=10, cost_usd=0.10),
                ApiUsage(org_id=org.id, service="ocr", pages_used=5, cost_usd=0.05),
                ApiUsage(
                    org_id=org.id,
                    service="gemini",
                    tokens_used=2000,
                    cost_usd=0.02,
                ),
                # Older than the 24h window — must be excluded.
                ApiUsage(
                    org_id=org.id,
                    service="ocr",
                    pages_used=999,
                    cost_usd=9.99,
                    created_at=datetime.now(UTC) - timedelta(hours=48),
                ),
            ]
        )


async def test_summarize_api_costs_groups_by_service_within_window() -> None:
    await _seed_usage()
    async with SessionLocal() as session:
        rows = await summarize_api_costs(session, since_hours=24)
    by_service = {r.service: r for r in rows}
    assert by_service["ocr"].total_cost_usd == 0.15
    assert by_service["ocr"].total_pages == 15  # 48h-old row excluded
    assert by_service["gemini"].total_tokens == 2000


def test_check_queue_depths_returns_all_default_queues() -> None:
    depths = check_queue_depths()
    assert set(depths) == {"ocr", "embed", "ai", "default", "dlq"}
    assert all(isinstance(v, int) and v >= 0 for v in depths.values())
