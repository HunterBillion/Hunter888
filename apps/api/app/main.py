import logging
import sys

# Configure root logger so app.* loggers (TTS, training WS, etc.) output to stdout
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    stream=sys.stdout,
)

from fastapi import FastAPI, Request, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.middleware.base import BaseHTTPMiddleware

from contextlib import asynccontextmanager

from app.api.router import api_router
from app.config import settings
from app.services.scheduler import reminder_scheduler
from app.ws.game_crm import game_crm_websocket
from app.ws.training import training_websocket
from app.ws.notifications import notification_websocket
from app.ws.pvp import pvp_websocket

logger = logging.getLogger(__name__)

# Rate limiter
limiter = Limiter(key_func=get_remote_address)

# Browsers send Origin with the page URL (e.g. http://192.168.x.x:3000). CORS must allow it
# when the UI is opened via LAN IP, not only localhost — otherwise fetch + WebSocket fail.
_CORS_LAN_ORIGIN_REGEX = (
    r"https?://(localhost|127\.0\.0\.1)(:\d+)?$|"
    r"https?://192\.168\.\d{1,3}\.\d{1,3}(:\d+)?$|"
    r"https?://10\.\d{1,3}\.\d{1,3}\.\d{1,3}(:\d+)?$|"
    r"https?://172\.(1[6-9]|2[0-9]|3[0-1])\.\d{1,3}\.\d{1,3}(:\d+)?$"
)


@asynccontextmanager
async def lifespan(application: FastAPI):
    """Startup / shutdown lifecycle (FastAPI 0.109+)."""
    # ── Startup ──
    reminder_scheduler.start()
    logger.info("Lifespan: startup complete")
    yield
    # ── Shutdown ──
    reminder_scheduler.stop()
    logger.info("Lifespan: shutdown complete")


app = FastAPI(
    title="VibeHunter API",
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
                "script-src 'self' 'unsafe-inline'; "
                "style-src 'self' 'unsafe-inline'; "
                "img-src 'self' data: blob:; "
                "connect-src 'self' wss: ws:; "
                "font-src 'self' https://fonts.gstatic.com; "
                "media-src 'self' blob:;"
            )
        return response


app.add_middleware(SecurityHeadersMiddleware)

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
    await training_websocket(websocket)


@app.websocket("/ws/notifications")
async def ws_notifications(websocket: WebSocket):
    """WebSocket для real-time уведомлений (Agent 7 — Client Communication)."""
    await notification_websocket(websocket)


@app.websocket("/ws/pvp")
async def ws_pvp(websocket: WebSocket):
    """WebSocket для PvP-дуэлей (Agent 8 — PvP Battle)."""
    await pvp_websocket(websocket)


@app.websocket("/ws/game-crm")
async def ws_game_crm(websocket: WebSocket):
    """WebSocket для текстового чата AI-клиента в CRM-панели."""
    await game_crm_websocket(websocket)
