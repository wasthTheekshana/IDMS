from collections.abc import AsyncGenerator, Generator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.core.config import settings
from app.core.db import SessionLocal
from app.main import app


def pytest_configure(config: pytest.Config) -> None:
    """The clean_db fixture TRUNCATEs every table — refuse to aim it at a
    real database. Run tests with DATABASE_URL pointing at *_test only
    (make test does this automatically)."""
    db_name = settings.DATABASE_URL.rsplit("/", 1)[-1]
    if not db_name.endswith("_test"):
        pytest.exit(
            f"Refusing to run tests against non-test database '{db_name}'. "
            "Set DATABASE_URL to an *_test database (see 'make test').",
            returncode=1,
        )


@pytest.fixture(autouse=True)
async def clean_db() -> None:
    """Truncate all tenant tables before each test so tests are independent."""
    _sql = (
        "TRUNCATE TABLE document_chunks, api_usage, documents,"
        " audit_logs, users, organizations RESTART IDENTITY CASCADE"
    )
    async with SessionLocal.begin() as session:
        await session.execute(text(_sql))


@pytest.fixture(autouse=True)
def _disable_rate_limits() -> Generator[None, None, None]:
    """Rate limits key on client IP; all test traffic shares one IP."""
    from app.core.ratelimit import limiter

    limiter.enabled = False
    yield
    limiter.enabled = False


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


@pytest.fixture
async def auth_client(client: AsyncClient) -> tuple[AsyncClient, dict]:  # type: ignore[type-arg]
    """Returns (client, tokens) for a freshly registered org."""
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "org_name": "Test Org A",
            "email": "owner-a@example.com",
            "password": "password1234",
        },
    )
    assert resp.status_code == 201, resp.text
    tokens = resp.json()
    client.headers["Authorization"] = f"Bearer {tokens['access_token']}"
    return client, tokens


@pytest.fixture
async def second_auth_client() -> AsyncGenerator[tuple[AsyncClient, dict], None]:  # type: ignore[type-arg]
    """Separate client for a second org."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client_b:
        resp = await client_b.post(
            "/api/v1/auth/register",
            json={
                "org_name": "Test Org B",
                "email": "owner-b@example.com",
                "password": "password1234",
            },
        )
        assert resp.status_code == 201, resp.text
        tokens = resp.json()
        client_b.headers["Authorization"] = f"Bearer {tokens['access_token']}"
        yield client_b, tokens
