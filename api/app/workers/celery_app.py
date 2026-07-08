from celery import Celery  # type: ignore[import-untyped]
from celery.schedules import crontab  # type: ignore[import-untyped]

from app.core.config import settings
from app.core.telemetry import configure_sentry

# Worker/beat processes don't run the FastAPI lifespan; init Sentry here so
# capture_message from monitoring tasks and task crashes actually report.
configure_sentry()

celery_app = Celery(
    "idms",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.workers.tasks"],
)

celery_app.conf.update(
    task_default_queue="default",
    task_queues={
        "ocr": {},
        "embed": {},
        "ai": {},
        "default": {},
        "dlq": {},
    },
    task_routes={
        "app.workers.tasks.ocr_*": {"queue": "ocr"},
        "app.workers.tasks.embed_*": {"queue": "embed"},
        "app.workers.tasks.ai_*": {"queue": "ai"},
    },
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    # Beat schedule: self-healing task runs every 2 minutes
    beat_schedule={
        "heal-stuck-documents": {
            "task": "app.workers.tasks.heal_stuck_documents",
            "schedule": 120.0,
        },
        "daily-cost-report": {
            "task": "app.workers.tasks.report_api_costs",
            "schedule": crontab(hour=1, minute=0),
        },
        "queue-depth-monitor": {
            "task": "app.workers.tasks.monitor_queue_depths",
            "schedule": 300.0,
        },
    },
)
