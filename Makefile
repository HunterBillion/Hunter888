.PHONY: dev dev-api dev-web test lint migrate seed setup clean

# Development
dev:
	docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build

dev-db:
	docker compose -f docker-compose.pilot.yml up -d

dev-api:
	cd apps/api && uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

dev-web:
	cd apps/web && npm run dev

# Database
migrate:
	cd apps/api && uv run alembic upgrade head

migrate-new:
	cd apps/api && uv run alembic revision --autogenerate -m "$(msg)"

seed:
	cd apps/api && uv run python -m scripts.seed_db

# Testing
test:
	cd apps/api && uv run pytest -v
	cd apps/web && npm test -- --passWithNoTests

test-api:
	cd apps/api && uv run pytest -v

test-web:
	cd apps/web && npm test -- --passWithNoTests

# Linting
lint:
	cd apps/api && uv run ruff check . && uv run ruff format --check .
	cd apps/web && npm run lint

lint-fix:
	cd apps/api && uv run ruff check --fix . && uv run ruff format .
	cd apps/web && npm run lint -- --fix

# Setup
setup:
	@echo "=== Installing dependencies ==="
	@echo "1. Install Homebrew (if not installed):"
	@echo "   /bin/bash -c \"\$$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\""
	@echo "2. Install tools:"
	@echo "   brew install node@20 python@3.12 uv"
	@echo "   brew install --cask docker"
	@echo "3. Setup backend:"
	@echo "   cd apps/api && uv sync"
	@echo "4. Setup frontend:"
	@echo "   cd apps/web && npm install"
	@echo "5. Copy env file:"
	@echo "   cp .env.example .env"
	@echo "6. Start services:"
	@echo "   make dev"

clean:
	docker compose down -v
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	rm -rf apps/web/.next apps/web/node_modules
