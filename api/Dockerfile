FROM python:3.12-slim

RUN adduser --disabled-password --gecos "" appuser

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY . .
RUN chown -R appuser:appuser /app/app /app/scripts /app/migrations /app/alembic.ini 2>/dev/null || true

USER appuser

CMD ["uv", "run", "--no-sync", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
