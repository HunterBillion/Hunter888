import asyncio
import logging

from app.config import settings
from app.core.logging_config import setup_logging

# Centralized logging — uses JSON format in production, text in development
setup_logging(log_level=settings.log_level, log_format=settings.log_format)

import uuid

from fastapi import FastAPI, Request, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.rate_limit import limiter

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


async def _delayed_backfill(coro_func, delay: int = 10):
    """Wait before running backfill to let legal embeddings start first."""
    await asyncio.sleep(delay)
    await coro_func()


@asynccontextmanager
async def lifespan(application: FastAPI):
    """Startup / shutdown lifecycle (FastAPI 0.109+)."""
    import asyncio
    from app.database import async_session
    from app.services.rag_legal import safe_populate_embeddings, close_embedding_client, blitz_pool
    from app.services.embedding_backfill import safe_populate_all_embeddings

    # ── Startup ──
    reminder_scheduler.start()
    wiki_scheduler.start()

    # Phase 2.11 (2026-04-19): register MCP tools. Importing the ``tools``
    # package triggers the ``@tool`` decorators that add entries to
    # ``ToolRegistry``. Kept here (not as a top-of-module import) so that
    # tools can use settings / DB without module-load cycles.
    try:
        from app.mcp import ToolRegistry
        from app.mcp import tools as _mcp_tools  # noqa: F401 — side-effect

        logger.info(
            "MCP: registered tools: %s (mcp_enabled=%s)",
            [t.name for t in ToolRegistry.all()],
            getattr(settings, "mcp_enabled", False),
        )
    except Exception:
        logger.warning("MCP tool registration failed", exc_info=True)

    # Populate legal embeddings in background (non-blocking)
    _embedding_task = asyncio.create_task(safe_populate_embeddings())
    # Populate personality + wiki embeddings (waits 10s for legal to start first)
    _all_embedding_task = asyncio.create_task(_delayed_backfill(safe_populate_all_embeddings, delay=10))

    # Seed data — use Redis lock to prevent concurrent seed from multiple workers
    try:
        from app.core.redis_pool import get_redis
        r = get_redis()
        if r:
            lock_acquired = await r.set("seed:lock", "1", nx=True, ex=120)  # 2 min lock
        else:
            lock_acquired = True  # No Redis = single worker, safe to seed

        if lock_acquired:
            # OPT-2 (2026-04-18): базовый seed блокирующе (создаёт users/
            # teams/scenarios которые нужны всем остальным), остальные 3
            # сида запускаются ПАРАЛЛЕЛЬНО через asyncio.gather — они
            # независимы друг от друга. Startup-time падает с ~15-20s
            # до ~5-8s, уменьшает dead-time при деплое.

            # 1) base seed — блокирующе (всё остальное зависит от него)
            try:
                from scripts.seed_db import seed as seed_base_data
                await seed_base_data()
                logger.info("Lifespan: base seed complete")
            except Exception as e:
                logger.warning("Lifespan: base seed failed (non-blocking): %s", e)

            # 2) параллельный запуск 3 независимых сидеров
            async def _seed_scenarios():
                try:
                    from scripts.seed_scenarios import seed_scenario_templates
                    await seed_scenario_templates()
                    logger.info("Lifespan: scenario templates seed complete")
                except Exception as e:
                    logger.warning("Lifespan: scenario templates seed failed: %s", e)

            async def _seed_legal():
                try:
                    from app.seeds.seed_legal_knowledge import seed_expanded_data
                    await seed_expanded_data()
                    logger.info("Lifespan: expanded legal seed complete")
                except Exception as e:
                    logger.warning("Lifespan: expanded legal seed failed: %s", e)

            async def _seed_lorebook():
                try:
                    from scripts.seed_lorebook import seed_all_archetypes
                    from app.database import async_session as _lb_session
                    async with _lb_session() as _lb_db:
                        lb_results = await seed_all_archetypes(_lb_db)
                        total = sum(r.get("entries_created", 0) + r.get("examples_created", 0) for r in lb_results)
                        if total > 0:
                            logger.info("Lifespan: lorebook seed complete (%d items)", total)
                except Exception as e:
                    logger.warning("Lifespan: lorebook seed failed: %s", e)

            await asyncio.gather(
                _seed_scenarios(),
                _seed_legal(),
                _seed_lorebook(),
                return_exceptions=True,
            )
            logger.info("Lifespan: parallel seeds complete")
        else:
            logger.info("Lifespan: seed skipped (another worker is seeding)")
    except Exception as e:
        logger.warning("Lifespan: seed lock failed: %s", e)

    # ── Ensure PvE bot user exists (FK target for pvp_duels.player2_id) ──
    try:
        _BOT_UUID = "00000000-0000-0000-0000-000000000001"
        async with async_session() as _bot_db:
            from sqlalchemy import text as _text
            _exists = (await _bot_db.execute(
                _text("SELECT 1 FROM users WHERE id = :bid"),
                {"bid": _BOT_UUID},
            )).scalar()
            if not _exists:
                from app.core.security import hash_password as _hp
                from app.models.user import User as _U, UserRole as _UR
                import uuid as _uuid
                _bot = _U(
                    id=_uuid.UUID(_BOT_UUID),
                    email="bot@system.local",
                    hashed_password=_hp("!disabled-bot-account!"),
                    full_name="AI Бот",
                    role=_UR.manager,
                    is_active=False,
                )
                _bot_db.add(_bot)
                await _bot_db.commit()
                logger.info("Lifespan: PvE bot user created")
    except Exception as e:
        logger.warning("Lifespan: PvE bot user check failed (non-blocking): %s", e)

    # Load BlitzQuestionPool for zero-latency blitz mode
    try:
        async with async_session() as db:
            count = await blitz_pool.load(db)
            logger.info("Lifespan: BlitzQuestionPool loaded (%d questions)", count)
    except Exception as e:
        logger.warning("Lifespan: BlitzQuestionPool failed to load: %s", e)

    # Register gamification EventBus handlers + start outbox worker
    from app.services.event_bus import setup_default_handlers, event_bus
    setup_default_handlers()
    event_bus.start_worker(poll_interval=1.0)

    # Auto-seed Season 1 content (idempotent)
    try:
        from app.services.content_season import seed_first_season
        async with async_session() as db:
            await seed_first_season(db)
            await db.commit()
    except Exception as e:
        logger.warning("Lifespan: Season seed failed: %s", e)

    # Start LLM health monitor (checks Mac Mini every 30s, updates Redis, notifies users)
    from app.services.llm_health import start_monitor as start_llm_monitor
    start_llm_monitor()

    # Start weekly league scheduler (form groups Monday, finalize Sunday)
    import asyncio
    async def _league_scheduler():
        """Background task: checks hourly if league actions needed."""
        from datetime import datetime, timezone
        while True:
            try:
                now = datetime.now(timezone.utc)
                # Monday 05:00-06:00 UTC (08:00-09:00 MSK) → form groups
                if now.weekday() == 0 and 5 <= now.hour < 6:
                    from app.services.weekly_league import form_weekly_groups
                    async with async_session() as db:
                        created = await form_weekly_groups(db)
                        await db.commit()
                        if created:
                            logger.info("League scheduler: formed %d groups", created)
                # Sunday 20:00-21:00 UTC (23:00-00:00 MSK) → finalize
                elif now.weekday() == 6 and 20 <= now.hour < 21:
                    from app.services.weekly_league import finalize_week
                    async with async_session() as db:
                        result = await finalize_week(db)
                        await db.commit()
                        if result.get("groups_finalized"):
                            logger.info("League scheduler: finalized %s", result)
            except Exception as e:
                logger.warning("League scheduler error: %s", e)
            await asyncio.sleep(3600)  # Check every hour
    asyncio.create_task(_league_scheduler())

    logger.info("Lifespan: startup complete")
    yield
    # ── Shutdown ──
    # Stop outbox worker first (flush pending events)
    from app.services.event_bus import event_bus as _eb
    await _eb.stop_worker()

    _embedding_task.cancel()
    _all_embedding_task.cancel()
    reminder_scheduler.stop()
    wiki_scheduler.stop()
    # Stop LLM health monitor
    from app.services.llm_health import stop_monitor as stop_llm_monitor
    stop_llm_monitor()
    await close_embedding_client()
    # Close shared LLM + embedding httpx clients
    # FIND-003 fix: log shutdown errors so connection leaks are observable.
    try:
        from app.services.llm import close_llm_clients
        await close_llm_clients()
    except Exception as _e_llm:
        logger.warning("Failed to close LLM clients on shutdown: %s", _e_llm, exc_info=True)
    # Close shared TTS httpx client
    try:
        from app.services.tts import close_tts_client
        await close_tts_client()
    except Exception as _e_tts:
        logger.warning("Failed to close TTS client on shutdown: %s", _e_tts, exc_info=True)
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
    "/api/auth/logout",         # FIND-005 fix: allow logout without CSRF so
                                #   users with lost CSRF cookie can still sign out
    "/api/auth/forgot-password",
    "/api/auth/reset-password",
    "/api/auth/google",
    "/api/auth/yandex",
    "/api/auth/oauth",
    "/api/health",
    "/api/subscription/webhook/",
    "/ws/",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/metrics",
)

_CSRF_STATE_CHANGING_METHODS = {"POST", "PUT", "DELETE", "PATCH"}


class CSRFMiddleware(BaseHTTPMiddleware):
    """Validate X-CSRF-Token header against csrf_token cookie on state-changing requests.

    FIND-001 debug aid: when check fails, log WHICH side is missing or
    mismatched so we can diagnose bugs like Starlette cookie parsing
    edge-cases (values containing '.' or ';').
    """

    async def dispatch(self, request: Request, call_next):
        if request.method in _CSRF_STATE_CHANGING_METHODS:
            path = request.url.path
            exempt = any(path.startswith(prefix) for prefix in _CSRF_EXEMPT_PREFIXES)
            # FIND-003 (2026-04-19): requests without ``Authorization`` are
            # skipped — the auth dependency below will return a clean 401
            # (Unauthorized). Without this skip, unauthenticated clients hit
            # a confusing 403 (CSRF missing) before the auth layer even
            # runs, and frontend ``handleUnauthorized()`` refresh-token
            # logic (which is gated on 401) never triggers.
            has_auth = bool(request.headers.get("authorization"))
            if not exempt and has_auth:
                header_token = request.headers.get("X-CSRF-Token", "")
                cookie_token = request.cookies.get("csrf_token", "")
                # Both must be present and equal (constant-time compare to avoid timing attacks)
                import hmac
                ok = bool(
                    header_token
                    and cookie_token
                    and hmac.compare_digest(header_token.encode(), cookie_token.encode())
                )
                if not ok:
                    # Log the exact reason — see FIND-001 in the audit. Values
                    # are logged only as lengths + prefixes to avoid leaking
                    # the actual token into persistent logs.
                    reason = (
                        "both_missing" if not header_token and not cookie_token
                        else "header_missing" if not header_token
                        else "cookie_missing" if not cookie_token
                        else "mismatch"
                    )
                    logger.warning(
                        "CSRF check failed: path=%s method=%s reason=%s "
                        "header_len=%d cookie_len=%d raw_cookie_header_len=%d",
                        path, request.method, reason,
                        len(header_token), len(cookie_token),
                        len(request.headers.get("cookie", "")),
                    )
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

# P0-5 fix (2026-04-18): в production разрешаем ТОЛЬКО явный список
# cors_origins (production домены), LAN-regex отключаем — иначе любой в
# той же локалке (VPN, внутренняя сеть) мог бы дергать API. В dev keep
# LAN-regex чтобы тестировать с телефона в той же сети.
_cors_kwargs: dict = {
    "allow_origins": [o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    "allow_credentials": True,
    "allow_methods": ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    "allow_headers": ["Content-Type", "Authorization", "X-CSRF-Token"],
    "expose_headers": ["X-CSRF-Token"],
}
if settings.app_env != "production":
    _cors_kwargs["allow_origin_regex"] = _CORS_LAN_ORIGIN_REGEX
app.add_middleware(CORSMiddleware, **_cors_kwargs)

app.include_router(api_router, prefix="/api")

# Sprint 4 (2026-04-20) — Arena lifelines (hint / skip / 50-50) REST API.
# Mounted separately because the router already declares its own /api prefix.
from app.api.arena_lifelines import router as _arena_lifelines_router  # noqa: E402
app.include_router(_arena_lifelines_router)

# Phase C (2026-04-20): Arena first-match tutorial gate.
from app.api.tutorial import router as _tutorial_router  # noqa: E402
app.include_router(_tutorial_router)

# Phase C (2026-04-20): Arena power-ups (×2 XP, future: shield, etc.)
from app.api.arena_powerups import router as _arena_powerups_router  # noqa: E402
app.include_router(_arena_powerups_router)


# ── WebSocket origin validation ──────────────────────────────────────────────
import re as _re

_WS_ALLOWED_ORIGIN_RE = _re.compile(
    r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$|"
    r"^https?://192\.168\.\d{1,3}\.\d{1,3}(:\d+)?$|"
    r"^https?://10\.\d{1,3}\.\d{1,3}\.\d{1,3}(:\d+)?$|"
    r"^https?://172\.(1[6-9]|2[0-9]|3[0-1])\.\d{1,3}\.\d{1,3}(:\d+)?$"
)


def _validate_ws_origin(websocket: WebSocket) -> bool:
    """Validate WebSocket Origin header to prevent cross-site WebSocket hijacking.

    P0-5 fix (2026-04-18): в production разрешаем только явные origin'ы
    из settings.cors_origins. LAN-regex применяется только в dev/staging.
    """
    origin = websocket.headers.get("origin", "")
    if not origin:
        # Require Origin header. Non-browser clients (curl, etc.) must authenticate
        # via JWT — Origin-less connections are rejected to prevent CSWSH attacks.
        return False
    # Check explicit CORS origins
    allowed_origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
    if origin in allowed_origins:
        return True
    # Check LAN pattern — ONLY outside production
    if settings.app_env != "production" and _WS_ALLOWED_ORIGIN_RE.match(origin):
        return True
    return False

# Serve uploaded avatars
from fastapi.staticfiles import StaticFiles
from pathlib import Path as _Path

_avatars_dir = _Path(__file__).resolve().parent.parent / "uploads" / "avatars"
_avatars_dir.mkdir(parents=True, exist_ok=True)
app.mount("/api/uploads/avatars", StaticFiles(directory=str(_avatars_dir)), name="avatars")

_attachments_dir = _Path(__file__).resolve().parent.parent / "uploads" / "attachments"
_attachments_dir.mkdir(parents=True, exist_ok=True)
app.mount(
    "/api/uploads/attachments",
    StaticFiles(directory=str(_attachments_dir)),
    name="attachments",
)


# T1 fix: top-level /health alias for external LB/healthcheck probes that
# hit /health rather than /api/health. Mirrors the canonical endpoint.
@app.get("/health", include_in_schema=False)
async def _health_alias():
    return {"status": "ok"}

# Prometheus metrics.
# 2026-04-18 (FIND-012): /metrics exposed without auth leaks request latency,
# session counts, and error rates. In production it must be fronted by nginx
# with an IP-allowlist (internal VPN only). Here we gate exposure behind
# METRICS_ENABLED so local dev and non-metrics deploys don't leak by default.
if settings.metrics_enabled:
    try:
        from prometheus_fastapi_instrumentator import Instrumentator
        Instrumentator().instrument(app).expose(app)
    except ImportError:
        logger.warning("prometheus-fastapi-instrumentator not installed, metrics disabled")
else:
    logger.info("Metrics disabled (METRICS_ENABLED=false) — set true and put /metrics behind nginx IP allowlist to enable")


# FIND-002 fix: attach a request_id to each WebSocket so logs from WS
# handlers can be correlated across services and grouped with HTTP requests.
# The id flows to the client too — it goes in the `X-Request-ID` response
# header on the handshake upgrade AND is exposed via websocket.state so
# handler code can include it in every log line via logger extra=.
def _attach_ws_request_id(websocket: WebSocket) -> str:
    """Generate a short request_id and attach to websocket.state. Also emit
    as X-Request-ID response header on the handshake so browser/devtools
    can correlate with HTTP traffic."""
    rid = websocket.headers.get("x-request-id") or uuid.uuid4().hex[:16]
    websocket.state.request_id = rid
    return rid


@app.websocket("/ws/training")
async def ws_training(websocket: WebSocket):
    _attach_ws_request_id(websocket)
    if not _validate_ws_origin(websocket):
        await websocket.close(code=4003)
        return
    await training_websocket(websocket)


@app.websocket("/ws/notifications")
async def ws_notifications(websocket: WebSocket):
    """WebSocket для real-time уведомлений (Agent 7 — Client Communication)."""
    _attach_ws_request_id(websocket)
    if not _validate_ws_origin(websocket):
        await websocket.close(code=4003)
        return
    await notification_websocket(websocket)


@app.websocket("/ws/pvp")
async def ws_pvp(websocket: WebSocket):
    """WebSocket для PvP-дуэлей (Agent 8 — PvP Battle)."""
    _attach_ws_request_id(websocket)
    if not _validate_ws_origin(websocket):
        await websocket.close(code=4003)
        return
    await pvp_websocket(websocket)


@app.websocket("/ws/knowledge")
async def ws_knowledge(websocket: WebSocket):
    """WebSocket for Knowledge Quiz (127-FZ knowledge testing)."""
    _attach_ws_request_id(websocket)
    if not _validate_ws_origin(websocket):
        await websocket.close(code=4003)
        return
    await knowledge_websocket(websocket)


@app.websocket("/ws/game-crm")
async def ws_game_crm(websocket: WebSocket):
    """WebSocket для текстового чата AI-клиента в CRM-панели."""
    _attach_ws_request_id(websocket)
    if not _validate_ws_origin(websocket):
        await websocket.close(code=4003)
        return
    await game_crm_websocket(websocket)
