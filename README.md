# AI Тренажер Продаж

Платформа для обучения менеджеров по продажам через голосовые диалоги с AI-аватарами.

## Stack

- **Backend**: FastAPI, SQLAlchemy, PostgreSQL + pgvector, Redis
- **Frontend**: Next.js 15, React 19, TypeScript, Tailwind CSS
- **AI**: Claude API (primary), GPT-4o-mini (fallback), faster-whisper (STT)
- **Infrastructure**: Docker Compose, GitHub Actions CI

## Quick Start

### Prerequisites

```bash
brew install node@20 python@3.12 uv
brew install --cask docker
```

### Setup

```bash
# Clone and enter project
cp .env.example .env

# Start infrastructure
docker compose up postgres redis -d

# Backend
cd apps/api
uv sync
uv run alembic upgrade head
uv run python -m scripts.seed_db
uv run uvicorn app.main:app --reload

# Frontend (new terminal)
cd apps/web
npm install
npm run dev
```

### Docker (full stack)

```bash
cp .env.example .env
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```

## Project Structure

```
├── apps/
│   ├── api/          # FastAPI backend (port 8000)
│   └── web/          # Next.js frontend (port 3000)
├── prompts/          # Versioned AI character prompts
├── scripts/          # Dev utilities (seed, etc.)
├── docker-compose.yml
└── Makefile
```

## Development

```bash
make dev        # Start all services via Docker
make test       # Run all tests
make lint       # Lint backend + frontend
make migrate    # Run DB migrations
make seed       # Seed development data
```

## Test Users (after seed)

| Role   | Email                | Password   |
|--------|----------------------|------------|
| Admin  | admin@trainer.local  | admin123   |
| Manager| manager@trainer.local| manager123 |
| ROP    | rop@trainer.local    | rop12345   |
