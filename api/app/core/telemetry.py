import sentry_sdk
from sentry_sdk.integrations.celery import CeleryIntegration
from sentry_sdk.integrations.fastapi import FastApiIntegration

from app.core.config import settings


def configure_sentry() -> None:
    """Idempotent; called from the API lifespan and Celery worker/beat startup."""
    if not settings.SENTRY_DSN:
        return
    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        integrations=[FastApiIntegration(), CeleryIntegration()],
        traces_sample_rate=0.1,
        environment="development" if settings.DEBUG else "production",
    )
