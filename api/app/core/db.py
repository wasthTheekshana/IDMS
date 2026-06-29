import os

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

from app.core.config import settings

_pool_kwargs: dict[str, object] = {}
if os.getenv("TESTING") == "true":
    # Each pytest function gets its own event loop; NullPool avoids reusing
    # asyncpg connections that are bound to the previous (closed) loop.
    _pool_kwargs["poolclass"] = NullPool

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    pool_pre_ping=True,
    **_pool_kwargs,  # type: ignore[arg-type]
)

SessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


def worker_session_factory() -> async_sessionmaker[AsyncSession]:
    """Create a fresh engine+session per Celery task to avoid event-loop conflicts."""
    _engine = create_async_engine(
        settings.DATABASE_URL,
        echo=settings.DEBUG,
        pool_pre_ping=True,
        poolclass=NullPool,
    )
    return async_sessionmaker(
        _engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
