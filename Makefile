.PHONY: up down test test-unit test-integration test-security \
        migrate migrate-down seed lint format logs shell-api

up:
	docker compose -f infra/docker-compose.yml up -d --build

down:
	docker compose -f infra/docker-compose.yml down

test:
	cd api && uv run pytest tests/ -v --tb=short

test-unit:
	cd api && uv run pytest tests/unit/ -v

test-integration:
	cd api && uv run pytest tests/integration/ -v

test-security:
	cd api && uv run pytest tests/security/ -v

migrate:
	cd api && uv run alembic upgrade head

migrate-down:
	cd api && uv run alembic downgrade -1

seed:
	cd api && uv run python infra/scripts/seed.py

lint:
	cd api && uv run ruff check . && uv run ruff format --check . && uv run mypy app/
	cd web && npm run lint && npm run type-check

format:
	cd api && uv run ruff format . && uv run ruff check --fix .

logs:
	docker compose -f infra/docker-compose.yml logs -f

shell-api:
	docker compose -f infra/docker-compose.yml exec api bash
