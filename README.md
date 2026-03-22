# AI Тренажер Продаж

Платформа для обучения менеджеров по продажам через голосовые диалоги с AI-аватарами.

## Что нужно для запуска на другом компьютере

Минимальный набор:

- `Docker Desktop` или `Docker Engine + Docker Compose`
- `Git` для клонирования репозитория
- доступ к GitHub-репозиторию `https://github.com/HunterBillion/Hunter888`

Если нужно только запустить проект, а не разрабатывать его, то `Python`, `Node.js` и `uv` на хост-машину ставить не обязательно. Достаточно Docker.

Нужно ли иметь права на GitHub:

- для простого запуска проекта на другом ноутбуке: нет, если вы скачали ZIP-архив или уже получили копию репозитория;
- для `git clone` из приватного репозитория: да, нужен доступ к репозиторию;
- для `git push`: да, нужен доступ на запись.

## Stack

- **Backend**: FastAPI, SQLAlchemy, PostgreSQL + pgvector, Redis
- **Frontend**: Next.js 15, React 19, TypeScript, Tailwind CSS
- **AI**: LLM (тестируется Gemini 2.5 Flash, выбор модели в процессе), GPT-4o-mini (fallback), Web Speech API (STT в браузере)
- **Infrastructure**: Docker Compose, GitHub Actions CI

## Quick Start

> **Развёртывание на хосте:** см. [DEPLOY.md](DEPLOY.md) — полная инструкция для production (Docker).

### Самый простой запуск на другом ноутбуке

```bash
git clone https://github.com/HunterBillion/Hunter888.git
cd Hunter888
cp .env.example .env
docker compose up -d --build
```

После запуска:

- web: [http://localhost:3000](http://localhost:3000)
- api: [http://localhost:8000/docs](http://localhost:8000/docs)

Если нужны тестовые пользователи:

```bash
docker compose exec api uv run python -m scripts.seed_db
```

Если репозиторий недоступен через `git clone`, можно скачать ZIP с GitHub, распаковать и выполнить те же команды, начиная с `cp .env.example .env`.

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

### Docker-only режим для большинства пользователей

Это рекомендуемый путь для новой машины:

```bash
cp .env.example .env
docker compose up -d --build
```

Остановка:

```bash
docker compose down
```

Полная очистка контейнеров и volumes:

```bash
docker compose down -v
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

| Role         | Email                  | Password     |
|--------------|------------------------|--------------|
| Admin        | admin@trainer.local    | Adm1n!2024   |
| ROP          | rop1@trainer.local     | Rop1!pass    |
| ROP          | rop2@trainer.local     | Rop2!pass    |
| Methodologist| method@trainer.local   | Method!1     |
| Manager      | manager1@trainer.local | Mgr1!pass    |
| Manager      | manager2@trainer.local | Mgr2!pass    |
| Manager      | manager3@trainer.local | Mgr3!pass    |
| Manager      | manager4@trainer.local | Mgr4!pass    |

## Публикация текущего проекта в GitHub

Если вы хотите, чтобы удалённый репозиторий полностью совпал с локальной папкой `/Hunter888-main`, то технически это делается force-push в `main`.

Безопасный порядок:

1. Убедиться, что локальный проект действительно финальный.
2. Сделать резервную копию удалённого репозитория или отдельную ветку.
3. Выполнить push с `--force-with-lease`, а не просто `--force`.

Пример:

```bash
git add .
git commit -m "Sync local Hunter888-main"
git push --force-with-lease origin main
```

Важно:

- это заменит содержимое удалённой ветки `main` текущим локальным состоянием;
- если в GitHub уже есть полезная история, лучше сначала сохранить её в отдельную ветку или tag;
- для авторизации лучше использовать `GitHub CLI`, `GitHub Desktop` или новый fine-grained PAT.

## Безопасность GitHub-токена

Токен нельзя хранить в README, переписке, shell history или коммитах. Если токен уже был отправлен в чат в открытом виде, его нужно считать скомпрометированным и перевыпустить.

Рекомендуемый вариант:

1. Отозвать старый token в GitHub Settings.
2. Создать новый `fine-grained token` только для этого репозитория.
3. Использовать его через `gh auth login`, GitHub Desktop или системный credential manager, а не вставлять в URL репозитория.
