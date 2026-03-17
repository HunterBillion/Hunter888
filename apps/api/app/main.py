import logging

from fastapi import FastAPI, Request, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.router import api_router
from app.config import settings
from app.ws.training import training_websocket

logger = logging.getLogger(__name__)

# Rate limiter
limiter = Limiter(key_func=get_remote_address)

app = FastAPI(
    title="VibeHunter API",
    description="AI-платформа обучения менеджеров через диалоговые симуляции",
    version="0.2.0",
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
                "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
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
    allow_origins=settings.cors_origins.split(","),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-CSRF-Token"],
    expose_headers=["X-CSRF-Token"],
)

app.include_router(api_router)

# Prometheus metrics
try:
    from prometheus_fastapi_instrumentator import Instrumentator
    Instrumentator().instrument(app).expose(app)
except ImportError:
    logger.warning("prometheus-fastapi-instrumentator not installed, metrics disabled")


@app.websocket("/ws/training")
async def ws_training(websocket: WebSocket):
    await training_websocket(websocket)
