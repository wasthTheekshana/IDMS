import asyncio
import uuid

from app.core.db import SessionLocal
from app.models.api_usage import ApiUsage
from app.models.organization import Organization
from app.workers.tasks import monitor_queue_depths, report_api_costs


async def test_report_api_costs_flags_overspend() -> None:
    async with SessionLocal.begin() as session:
        org = Organization(name="Spend Org", slug=f"spend-{uuid.uuid4().hex[:8]}")
        session.add(org)
        await session.flush()
        # 9.99 USD in the last 24h — above the 5.00 default threshold.
        session.add(ApiUsage(org_id=org.id, service="gemini", cost_usd=9.99))

    # The task wraps its coroutine in asyncio.run(); execute it off-loop.
    result = await asyncio.to_thread(report_api_costs.run)
    assert result["total_cost_usd"] >= 9.99
    assert result["alert"] is True
    assert any(s["service"] == "gemini" for s in result["services"])


def test_monitor_queue_depths_reports_all_queues() -> None:
    result = monitor_queue_depths.run()
    assert set(result["depths"]) == {"ocr", "embed", "ai", "default", "dlq"}
    assert result["alert"] is False  # local queues are empty
