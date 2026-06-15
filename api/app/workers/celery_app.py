from celery import Celery

from app.core.config import settings

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
)
