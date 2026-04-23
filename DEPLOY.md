# Развёртывание на хосте (Docker)

Руководство по восстановлению и запуску AI-тренажера Hunter888 на сервере с Docker.

## Короткий ответ: что нужно скачать на другой ноутбук

Если задача только запустить проект локально, обычно достаточно:

- `Docker Desktop`
- `Git`
- доступ к репозиторию GitHub

Дальше:

```bash
git clone https://github.com/HunterBillion/Hunter888.git
cd Hunter888
cp .env.example .env
docker compose up -d --build
```

Если репозиторий приватный, нужен доступ к GitHub. Если репозиторий публичный или у вас есть ZIP-архив проекта, отдельный GitHub-аккаунт для простого запуска не обязателен.

## Требования

- Docker и Docker Compose
- Порты: 3000 (web), 8000 (api), 5432 (postgres), 6379 (redis)
- Минимум ~2.5 GB RAM (postgres 1G + redis 512M + api 1G)

## Шаг 1. Подготовка проекта

```bash
cd <каталог с проектом>   # пример: cd ~/projects/Hunter888-main
cp .env.example .env
```

## Шаг 2. Настройка .env для production

Отредактируйте `.env`:

### Обязательно

| Переменная | Описание |
|------------|----------|
| `JWT_SECRET` | Секрет для JWT (32+ символов). Генерация: `openssl rand -hex 32` |
| `GEMINI_API_KEY` | Ключ Gemini API: https://aistudio.google.com/apikey |
| `NEXT_PUBLIC_API_URL` | Публичный URL API (например `https://your-domain.com` или `http://IP:8000`) |
| `NEXT_PUBLIC_WS_URL` | WebSocket URL (`wss://your-domain.com` или `ws://IP:8000`) |

### Для production-сборки web

`NEXT_PUBLIC_*` вшиваются в сборку Next.js при `docker compose build`. Укажите их **до** сборки:

```bash
export NEXT_PUBLIC_API_URL=https://your-domain.com
export NEXT_PUBLIC_WS_URL=wss://your-domain.com
```

Или в `.env`:

```
NEXT_PUBLIC_API_URL=https://your-domain.com
NEXT_PUBLIC_WS_URL=wss://your-domain.com
```

### Рекомендуемо

| Переменная | Для production |
|------------|----------------|
| `APP_ENV` | `production` |
| `APP_DEBUG` | `false` |
| `FRONTEND_URL` | URL вашего фронтенда (например `https://your-domain.com`) |
| `CORS_ORIGINS` | То же, что FRONTEND_URL |

### Redis (для Docker Compose)

Добавьте в `.env`, если хотите свой пароль:

```
REDIS_PASSWORD=redis_secret_pass
```

## Шаг 3. Сборка и запуск

Рекомендуемый production-деплой из актуальной ветки `main`:

```bash
./scripts/deploy-prod.sh
```

Скрипт делает `git pull --ff-only`, проставляет `RELEASE_SHA`, пересобирает `api` и `web`, затем запускает production compose.

Проверка, какой commit реально развернут:

```bash
curl https://x-hunter.expert/api/version
```

`release_sha` должен совпадать с `git rev-parse origin/main`.

Ручной вариант:

```bash
export RELEASE_SHA=$(git rev-parse HEAD)
export BUILD_TIME=$(date -u +%Y-%m-%dT%H:%M:%SZ)
docker compose build --no-cache web api
docker compose up -d postgres redis api web
```

Миграции БД выполняются автоматически при старте API.

## Шаг 4. Проверка

- **Web**: http://localhost:3000 (или ваш домен)
- **API**: http://localhost:8000/docs
- **Логи**: `docker compose logs -f api web`

Проверка health:

```bash
curl http://localhost:8000/api/health
```

Ожидаемый ответ:

```json
{"status":"ok"}
```

## Шаг 5. (Опционально) Тестовые пользователи

Для заполнения БД тестовыми пользователями (после первого запуска):

```bash
docker compose exec api uv run python -m scripts.seed_db
```

После seed доступны пользователи из README (admin@trainer.local / Adm1n!2024 и др.).

## Доменное имя и reverse proxy

При доступе через домен (например `https://app.example.com`) нужен reverse proxy (nginx, Caddy, Traefik):

- Проксировать `/api`, `/ws`, `/docs`, `/openapi.json` → `http://localhost:8000`
- Проксировать `/` → `http://localhost:3000`
- Включить WebSocket upgrade для `/ws/*`

Пример nginx:

```nginx
server {
    listen 80;
    server_name app.example.com;

    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /ws/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
    }

    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
    }
}
```

## Профили (whisper, embeddings)

По умолчанию запускаются: postgres, redis, api, web.

Для полноценного режима с Whisper (STT) и embeddings:

```bash
docker compose --profile full up -d
```

## Частые проблемы

| Проблема | Решение |
|----------|---------|
| API не стартует, ошибка миграций | Postgres ещё не готов. Entrypoint перезапускает миграции через 5 сек. Проверьте `docker compose logs api`. |
| Web подключается к localhost | Убедитесь, что `NEXT_PUBLIC_API_URL` и `NEXT_PUBLIC_WS_URL` заданы **до** `docker compose build web` и соответствуют URL, с которого открывается приложение. |
| 401 / CORS | Проверьте `CORS_ORIGINS` и `FRONTEND_URL` в `.env`. |
| LLM не отвечает | Проверьте `GEMINI_API_KEY` и логи API. |

## Как полностью заменить содержимое GitHub-репозитория локальным проектом

Если вы хотите очистить удалённый репозиторий `Hunter888` и залить туда текущее содержимое локальной папки, делайте это только после бэкапа.

Рекомендуемый сценарий:

```bash
git status
git add .
git commit -m "Sync full local project"
git push --force-with-lease origin main
```

Почему `--force-with-lease`, а не `--force`:

- он безопаснее и не затрёт чужие свежие коммиты молча.

Перед этим желательно:

```bash
git fetch origin
git branch backup-origin-main origin/main
```

## Важно по GitHub-токенам

Не вставляйте PAT в README, docker-compose, `.env`, git remote URL или переписку. Если токен уже был отправлен в открытом виде, его нужно сразу отозвать и создать новый.

Безопасные варианты авторизации:

- `gh auth login`
- `GitHub Desktop`
- системный credential manager
- новый `fine-grained PAT` только для нужного репозитория
