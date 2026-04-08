import logging

from app.config import settings
from app.core.logging_config import setup_logging

# Centralized logging — uses JSON format in production, text in development
setup_logging(log_level=settings.log_level, log_format=settings.log_format)

import uuid

from fastapi import FastAPI, Request, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.middleware.base import BaseHTTPMiddleware

from contextlib import asynccontextmanager

from app.api.router import api_router
from app.core.redis_pool import close_redis_pool
from app.services.scheduler import reminder_scheduler
from app.services.wiki_scheduler import wiki_scheduler
from app.ws.game_crm import game_crm_websocket
from app.ws.training import training_websocket
from app.ws.notifications import notification_websocket
from app.ws.pvp import pvp_websocket
from app.ws.knowledge import knowledge_websocket

logger = logging.getLogger(__name__)

# Rate limiter
limiter = Limiter(key_func=get_remote_address)

# Browsers send Origin with the page URL (e.g. http://192.168.x.x:3000). CORS must allow it
# when the UI is opened via LAN IP, not only localhost — otherwise fetch + WebSocket fail.
# Valid IP octet: 0-255 (no leading zeros abuse)
_O = r"(?:25[0-5]|2[0-4]\d|[01]?\d\d?)"
_CORS_LAN_ORIGIN_REGEX = (
    r"https?://(localhost|127\.0\.0\.1)(:\d+)?$|"
    rf"https?://192\.168\.{_O}\.{_O}(:\d+)?$|"
    rf"https?://10\.{_O}\.{_O}\.{_O}(:\d+)?$|"
    rf"https?://172\.(1[6-9]|2[0-9]|3[0-1])\.{_O}\.{_O}(:\d+)?$"
)


@asynccontextmanager
async def lifespan(application: FastAPI):
    """Startup / shutdown lifecycle (FastAPI 0.109+)."""
    import asyncio
    from app.database import async_session
    from app.services.rag_legal import safe_populate_embeddings, close_embedding_client, blitz_pool

    # ── Startup ──
    reminder_scheduler.start()
    wiki_scheduler.start()

    # Populate legal embeddings in background (non-blocking)
    _embedding_task = asyncio.create_task(safe_populate_embeddings())

    # Seed data — use Redis lock to prevent concurrent seed from multiple workers
    try:
        from app.core.redis_pool import get_redis
        r = get_redis()
        if r:
            lock_acquired = await r.set("seed:lock", "1", nx=True, ex=120)  # 2 min lock
        else:
            lock_acquired = True  # No Redis = single worker, safe to seed

        if lock_acquired:
            # Seed base data (users, teams, scripts, characters, scenarios)
            try:
                from scripts.seed_db import seed as seed_base_data
                await seed_base_data()
                logger.info("Lifespan: base seed complete")
            except Exception as e:
                logger.warning("Lifespan: base seed failed (non-blocking): %s", e)

            # Seed scenario templates (60 templates from DOC_05)
            try:
                from scripts.seed_scenarios import seed_scenario_templates
                await seed_scenario_templates()
                logger.info("Lifespan: scenario templates seed complete")
            except Exception as e:
                logger.warning("Lifespan: scenario templates seed failed (non-blocking): %s", e)

            # Seed expanded legal knowledge
            try:
                from app.seeds.seed_legal_knowledge import seed_expanded_data
                await seed_expanded_data()
            except Exception as e:
                logger.warning("Lifespan: expanded seed failed (non-blocking): %s", e)
        else:
            logger.info("Lifespan: seed skipped (another worker is seeding)")
    except Exception as e:
        logger.warning("Lifespan: seed lock failed: %s", e)

    # Load BlitzQuestionPool for zero-latency blitz mode
    try:
        async with async_session() as db:
            count = await blitz_pool.load(db)
            logger.info("Lifespan: BlitzQuestionPool loaded (%d questions)", count)
    except Exception as e:
        logger.warning("Lifespan: BlitzQuestionPool failed to load: %s", e)

    # Register gamification EventBus handlers
    from app.services.event_bus import setup_default_handlers
    setup_default_handlers()

    # Start LLM health monitor (checks Mac Mini every 30s, updates Redis, notifies users)
    from app.services.llm_health import start_monitor as start_llm_monitor
    start_llm_monitor()

    logger.info("Lifespan: startup complete")
    yield
    # ── Shutdown ──
    _embedding_task.cancel()
    reminder_scheduler.stop()
    wiki_scheduler.stop()
    # Stop LLM health monitor
    from app.services.llm_health import stop_monitor as stop_llm_monitor
    stop_llm_monitor()
    await close_embedding_client()
    # Close shared LLM + embedding httpx clients
    try:
        from app.services.llm import close_llm_clients
        await close_llm_clients()
    except Exception:
        pass
    # Close shared TTS httpx client
    try:
        from app.services.tts import close_tts_client
        await close_tts_client()
    except Exception:
        pass
    await close_redis_pool()
    logger.info("Lifespan: shutdown complete")


app = FastAPI(
    title="Hunter888 API",
    description="AI-платформа обучения менеджеров через диалоговые симуляции",
    version="0.2.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.app_debug else None,
    redoc_url="/redoc" if settings.app_debug else None,
)

app.state.limiter = limiter


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={"detail": "Too many requests. Please try again later."},
    )


# Catch unhandled database IntegrityErrors (FK violations, unique constraints)
# and return a proper 409 Conflict instead of 500 Internal Server Error.
from sqlalchemy.exc import IntegrityError as _SQLAlchemyIntegrityError


@app.exception_handler(_SQLAlchemyIntegrityError)
async def integrity_error_handler(request: Request, exc: _SQLAlchemyIntegrityError):
    logger.warning("Database IntegrityError on %s: %s", request.url.path, exc.orig)
    return JSONResponse(
        status_code=409,
        content={"detail": "Конфликт данных. Возможно, запись уже существует или ссылка недействительна."},
    )


# Catch all unhandled exceptions and return a proper 500 error with Russian message
# instead of FastAPI's default English "Internal Server Error"
@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception on %s: %s", request.url.path, exc)
    return JSONResponse(
        status_code=500,
        content={"detail": "Внутренняя ошибка сервера. Попробуйте позже."},
    )


# CSRF protection middleware — Double Submit Cookie pattern.
#
# How it works:
#   1. On login/register the backend sets a `csrf_token` cookie (non-httpOnly,
#      readable by JS) containing HMAC-SHA256(user_id, csrf_secret).
#   2. The frontend reads this cookie and sends the value in the
#      `X-CSRF-Token` header on every state-changing request.
#   3. This middleware validates the header value against the cookie value.
#
# Why this is safe: an attacker's site can trigger a cross-origin POST via a
# form or fetch, but cannot READ the `csrf_token` cookie (SameSite=Lax +
# same-origin cookie policy).  Without the cookie value, the attacker cannot
# set the matching `X-CSRF-Token` header.
#
# Exempted routes: /api/auth/login, /api/auth/register, /api/auth/refresh,
# OAuth callbacks, health checks — these either don't use cookies yet or are
# protected by other means.

_CSRF_EXEMPT_PREFIXES = (
    "/api/auth/login",
    "/api/auth/register",
    "/api/auth/refresh",
    "/api/auth/forgot-password",
    "/api/auth/reset-password",
    "/api/auth/google",
    "/api/auth/yandex",
    "/api/auth/oauth",
    "/api/health",
    "/ws/",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/metrics",
    "/api/uploads",
)

_CSRF_STATE_CHANGING_METHODS = {"POST", "PUT", "DELETE", "PATCH"}


class CSRFMiddleware(BaseHTTPMiddleware):
    """Validate X-CSRF-Token header against csrf_token cookie on state-changing requests."""

    async def dispatch(self, request: Request, call_next):
        if request.method in _CSRF_STATE_CHANGING_METHODS:
            path = request.url.path
            exempt = any(path.startswith(prefix) for prefix in _CSRF_EXEMPT_PREFIXES)
            if not exempt:
                header_token = request.headers.get("X-CSRF-Token", "")
                cookie_token = request.cookies.get("csrf_token", "")
                # Both must be present and equal (constant-time compare to avoid timing attacks)
                import hmac
                if not header_token or not cookie_token or not hmac.compare_digest(
                    header_token.encode(), cookie_token.encode()
                ):
                    return JSONResponse(
                        status_code=403,
                        content={"detail": "CSRF token missing or invalid"},
                    )
        return await call_next(request)


# Security headers middleware
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "microphone=(self), camera=()"
        if settings.app_env == "production":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                "script-src 'self'; "
                "style-src 'self' https://fonts.googleapis.com; "
                "img-src 'self' data: blob:; "
                "connect-src 'self' wss: ws:; "
                "font-src 'self' https://fonts.gstatic.com; "
                "media-src 'self' blob:;"
            )
        return response


# Request ID middleware — attaches unique ID to every request for distributed tracing.
# Reads X-Request-ID from reverse proxy (nginx/LB) or generates a new one.
# The ID is available in log records via logging_config.py extra fields.
class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:16]
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


app.add_middleware(CSRFMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestIDMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=_CORS_LAN_ORIGIN_REGEX,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-CSRF-Token"],
    expose_headers=["X-CSRF-Token"],
)

app.include_router(api_router, prefix="/api")


# ── WebSocket origin validation ──────────────────────────────────────────────
import re as _re

_WS_ALLOWED_ORIGIN_RE = _re.compile(
    r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$|"
    r"^https?://192\.168\.\d{1,3}\.\d{1,3}(:\d+)?$|"
    r"^https?://10\.\d{1,3}\.\d{1,3}\.\d{1,3}(:\d+)?$|"
    r"^https?://172\.(1[6-9]|2[0-9]|3[0-1])\.\d{1,3}\.\d{1,3}(:\d+)?$"
)


def _validate_ws_origin(websocket: WebSocket) -> bool:
    """Validate WebSocket Origin header to prevent cross-site WebSocket hijacking."""
    origin = websocket.headers.get("origin", "")
    if not origin:
        # Require Origin header. Non-browser clients (curl, etc.) must authenticate
        # via JWT — Origin-less connections are rejected to prevent CSWSH attacks.
        return False
    # Check explicit CORS origins
    allowed_origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
    if origin in allowed_origins:
        return True
    # Check LAN pattern
    if _WS_ALLOWED_ORIGIN_RE.match(origin):
        return True
    return False

# Serve uploaded avatars
from fastapi.staticfiles import StaticFiles
from pathlib import Path as _Path

_avatars_dir = _Path(__file__).resolve().parent.parent / "uploads" / "avatars"
_avatars_dir.mkdir(parents=True, exist_ok=True)
app.mount("/api/uploads/avatars", StaticFiles(directory=str(_avatars_dir)), name="avatars")

# Prometheus metrics
try:
    from prometheus_fastapi_instrumentator import Instrumentator
    Instrumentator().instrument(app).expose(app)
except ImportError:
    logger.warning("prometheus-fastapi-instrumentator not installed, metrics disabled")


@app.websocket("/ws/training")
async def ws_training(websocket: WebSocket):
    if not _validate_ws_origin(websocket):
        await websocket.close(code=4003)
        return
    await training_websocket(websocket)


@app.websocket("/ws/notifications")
async def ws_notifications(websocket: WebSocket):
    """WebSocket для real-time уведомлений (Agent 7 — Client Communication)."""
    if not _validate_ws_origin(websocket):
        await websocket.close(code=4003)
        return
    await notification_websocket(websocket)


@app.websocket("/ws/pvp")
async def ws_pvp(websocket: WebSocket):
    """WebSocket для PvP-дуэлей (Agent 8 — PvP Battle)."""
    if not _validate_ws_origin(websocket):
        await websocket.close(code=4003)
        return
    await pvp_websocket(websocket)


@app.websocket("/ws/knowledge")
async def ws_knowledge(websocket: WebSocket):
    """WebSocket for Knowledge Quiz (127-FZ knowledge testing)."""
    if not _validate_ws_origin(websocket):
        await websocket.close(code=4003)
        return
    await knowledge_websocket(websocket)


@app.websocket("/ws/game-crm")
async def ws_game_crm(websocket: WebSocket):
    """WebSocket для текстового чата AI-клиента в CRM-панели."""
    if not _validate_ws_origin(websocket):
        await websocket.close(code=4003)
        return
    await game_crm_websocket(websocket)
