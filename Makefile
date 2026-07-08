.PHONY: up down test test-unit test-integration test-security test-db \
        migrate migrate-down seed lint format logs shell-api \
        backup restore-drill load-test

up:
	docker compose -f infra/docker-compose.yml up -d --build

down:
	docker compose -f infra/docker-compose.yml down

# Tests TRUNCATE all tables — always run them against idms_test, never idms.
TEST_ENV = TESTING=true DATABASE_URL=postgresql+asyncpg://idms_app:devpassword@127.0.0.1:5432/idms_test

test:
	cd api && $(TEST_ENV) uv run pytest tests/ -v --tb=short

test-unit:
	cd api && $(TEST_ENV) uv run pytest tests/unit/ -v

test-integration:
	cd api && $(TEST_ENV) uv run pytest tests/integration/ -v

test-security:
	cd api && $(TEST_ENV) uv run pytest tests/security/ -v

test-db:
	docker compose -f infra/docker-compose.yml exec -T postgres \
		psql -U idms_app -d postgres -c "SELECT 1 FROM pg_database WHERE datname='idms_test'" | grep -q "1 row" || \
		docker compose -f infra/docker-compose.yml exec -T postgres psql -U idms_app -d postgres -c "CREATE DATABASE idms_test;"
	cd api && DATABASE_URL=postgresql+asyncpg://idms_app:devpassword@127.0.0.1:5432/idms_test uv run alembic upgrade head

migrate:
	cd api && uv run alembic upgrade head

migrate-down:
	cd api && uv run alembic downgrade -1

seed:
	cd api && uv run python ../infra/scripts/seed.py

lint:
	cd api && uv run ruff check . && uv run ruff format --check . && uv run mypy app/
	cd web && npm run lint && npm run type-check

format:
	cd api && uv run ruff format . && uv run ruff check --fix .

load-test:
	cd api && uv run locust -f ../infra/load/locustfile.py \
		--host http://localhost:8000 -u 50 -r 5 --run-time 3m --headless

backup:
	bash infra/scripts/backup.sh

restore-drill:
	bash infra/scripts/restore.sh $(FILE) idms_restore_drill

logs:
	docker compose -f infra/docker-compose.yml logs -f

shell-api:
	docker compose -f infra/docker-compose.yml exec api bash
