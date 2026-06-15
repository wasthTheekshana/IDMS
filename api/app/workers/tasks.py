from app.workers.celery_app import celery_app


@celery_app.task(queue="default", name="app.workers.tasks.health_check")
def health_check() -> dict[str, str]:
    """Smoke-test task — verifies the worker is alive and processing."""
    return {"status": "ok"}
