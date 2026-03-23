.PHONY: dev dev-api dev-web test lint migrate seed setup clean prod prod-build prod-logs backup

# ── Development ──────────────────────────────────────────────────────
dev:
	docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build

dev-db:
	docker compose -f docker-compose.pilot.yml up -d

dev-api:
	cd apps/api && uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

dev-web:
	cd apps/web && npm run dev

# ── Production ───────────────────────────────────────────────────────
prod:
	docker compose -f docker-compose.yml -f docker-compose.prod.yml --env-file .env.production up -d

prod-build:
	docker compose -f docker-compose.yml -f docker-compose.prod.yml --env-file .env.production up -d --build

prod-logs:
	docker compose -f docker-compose.yml -f docker-compose.prod.yml logs -f

prod-down:
	docker compose -f docker-compose.yml -f docker-compose.prod.yml down

# ── Database ─────────────────────────────────────────────────────────
migrate:
	cd apps/api && uv run alembic upgrade head

migrate-new:
	cd apps/api && uv run alembic revision --autogenerate -m "$(msg)"

migrate-rollback:
	cd apps/api && uv run alembic downgrade -1

seed:
	cd apps/api && uv run python -m scripts.seed_db

# ── Backups ──────────────────────────────────────────────────────────
backup:
	docker compose -f docker-compose.yml -f docker-compose.prod.yml run --rm backup /backup-db.sh

# ── Testing ──────────────────────────────────────────────────────────
test:
	cd apps/api && uv run pytest -v
	cd apps/web && npm test -- --passWithNoTests

test-api:
	cd apps/api && uv run pytest -v

test-web:
	cd apps/web && npm test -- --passWithNoTests

# ── Linting ──────────────────────────────────────────────────────────
lint:
	cd apps/api && uv run ruff check . && uv run ruff format --check .
	cd apps/web && npm run lint

lint-fix:
	cd apps/api && uv run ruff check --fix . && uv run ruff format .
	cd apps/web && npm run lint -- --fix

# ── Setup ────────────────────────────────────────────────────────────
setup:
	@echo "=== Hunter888 Setup ==="
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
	@echo ""
	@echo "=== Production Deploy ==="
	@echo "1. cp .env.production.example .env.production"
	@echo "2. Fill in all credentials in .env.production"
	@echo "3. Place TLS certs in nginx/certs/"
	@echo "4. make prod-build"

clean:
	docker compose down -v
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	rm -rf apps/web/.next apps/web/node_modules
