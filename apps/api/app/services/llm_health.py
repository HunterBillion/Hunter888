"""LLM health monitoring service.

Periodically checks Mac Mini (Local LLM) availability and maintains
Redis flags for frontend degradation banners. Sends WS notifications
when AI server goes up/down.

Designed for graceful degradation:
- Mac Mini offline → circuit breaker in llm.py auto-fallbacks to Gemini
- This service additionally notifies users via WebSocket
- Frontend reads Redis flag to show/hide degradation banner
"""

import asyncio
import logging
import time

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# Redis keys
REDIS_KEY_LLM_STATUS = "llm:local:available"  # "1" = online, "0" = offline
REDIS_KEY_LLM_LAST_CHECK = "llm:local:last_check"
REDIS_KEY_LLM_MODEL = "llm:local:model"

# Check interval (seconds)
CHECK_INTERVAL = 30

# State tracking (in-memory)
_last_known_status: bool | None = None  # None = not checked yet
_monitor_task: asyncio.Task | None = None


async def check_local_llm() -> dict:
    """Ping Mac Mini's LM Studio /v1/models endpoint.

    Returns dict with:
      status: "ok" | "offline" | "disabled"
      model: model name (if available)
      latency_ms: response time
    """
    if not settings.local_llm_enabled:
        return {"status": "disabled", "model": None, "latency_ms": 0}

    url = f"{settings.local_llm_url.rstrip('/')}/models"
    start = time.monotonic()

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(5.0, connect=3.0)) as client:
            resp = await client.get(
                url,
                headers={"Authorization": f"Bearer {settings.local_llm_api_key}"},
            )
        latency_ms = int((time.monotonic() - start) * 1000)

        if resp.status_code == 200:
            data = resp.json()
            models = data.get("data", [])
            model_name = models[0].get("id", "unknown") if models else "unknown"
            return {"status": "ok", "model": model_name, "latency_ms": latency_ms}
        else:
            return {"status": "offline", "model": None, "latency_ms": latency_ms}
    except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPError) as e:
        latency_ms = int((time.monotonic() - start) * 1000)
        logger.debug("Local LLM health check failed: %s", e)
        return {"status": "offline", "model": None, "latency_ms": latency_ms}


async def get_llm_status() -> dict:
    """Get current LLM status (calls check_local_llm)."""
    return await check_local_llm()


async def _update_redis_status(is_online: bool, model: str | None = None) -> None:
    """Update Redis flags for frontend consumption."""
    try:
        from app.core.redis_pool import get_redis
        r = get_redis()
        if r is None:
            return

        await r.set(REDIS_KEY_LLM_STATUS, "1" if is_online else "0", ex=90)
        await r.set(REDIS_KEY_LLM_LAST_CHECK, str(int(time.time())), ex=90)
        if model:
            await r.set(REDIS_KEY_LLM_MODEL, model, ex=90)
    except Exception as e:
        logger.debug("Failed to update LLM Redis status: %s", e)


async def _broadcast_status_change(is_online: bool) -> None:
    """Send WS notification to all connected users about LLM status change."""
    try:
        from app.ws.notifications import broadcast_system_message
        if is_online:
            await broadcast_system_message({
                "type": "system.llm_restored",
                "message": "AI-сервер восстановлен. Все функции доступны.",
            })
            logger.info("LLM status: Mac Mini ONLINE — notified users")
        else:
            await broadcast_system_message({
                "type": "system.llm_degraded",
                "message": "AI-сервер временно недоступен. Работаем в облачном режиме.",
                "affected": ["training", "pvp", "knowledge", "game_crm"],
            })
            logger.warning("LLM status: Mac Mini OFFLINE — notified users, falling back to cloud")
    except Exception as e:
        logger.debug("Failed to broadcast LLM status change: %s", e)


async def warm_up_model() -> None:
    """Pre-warm the chat model so it stays in Ollama's RAM.

    On M2 8GB, Ollama can only hold one model at a time.
    This dummy request ensures gemma4 is loaded BEFORE any user session.
    Also serves as keep-alive to prevent Ollama from unloading (default: 5min idle).
    """
    if not settings.local_llm_enabled or not settings.local_llm_url:
        return

    url = f"{settings.local_llm_url.rstrip('/')}/chat/completions"
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=5.0)) as client:
            resp = await client.post(
                url,
                headers={"Authorization": f"Bearer {settings.local_llm_api_key}"},
                json={
                    "model": settings.local_llm_model,
                    "messages": [{"role": "user", "content": "ping"}],
                    "max_tokens": 5,
                },
            )
            if resp.status_code == 200:
                logger.info("LLM warm-up: %s loaded and ready", settings.local_llm_model)
            else:
                logger.warning("LLM warm-up: status %d", resp.status_code)
    except Exception as e:
        logger.warning("LLM warm-up failed (model may cold-start on first request): %s", e)


# Keep-alive interval: ping chat model every 4 min to prevent Ollama unloading (default 5min idle)
_KEEP_ALIVE_INTERVAL = 240  # seconds


async def _monitor_loop() -> None:
    """Background loop: check Mac Mini every CHECK_INTERVAL seconds + keep-alive ping."""
    global _last_known_status
    logger.info("LLM health monitor started (interval=%ds, keep-alive=%ds)", CHECK_INTERVAL, _KEEP_ALIVE_INTERVAL)

    # Initial warm-up
    await warm_up_model()

    _ticks_since_keepalive = 0

    while True:
        try:
            result = await check_local_llm()
            is_online = result["status"] == "ok"

            # Update Redis
            await _update_redis_status(is_online, result.get("model"))

            # Detect status change → notify users
            if _last_known_status is not None and is_online != _last_known_status:
                await _broadcast_status_change(is_online)

            _last_known_status = is_online

            # Keep-alive: ping chat model periodically to prevent Ollama unloading
            _ticks_since_keepalive += CHECK_INTERVAL
            if _ticks_since_keepalive >= _KEEP_ALIVE_INTERVAL and is_online:
                _ticks_since_keepalive = 0
                await warm_up_model()

        except asyncio.CancelledError:
            logger.info("LLM health monitor stopped")
            return
        except Exception as e:
            logger.warning("LLM health monitor error: %s", e)

        await asyncio.sleep(CHECK_INTERVAL)


def start_monitor() -> None:
    """Start the background LLM health monitor task."""
    global _monitor_task
    if _monitor_task is not None:
        return  # Already running
    _monitor_task = asyncio.create_task(_monitor_loop())


def stop_monitor() -> None:
    """Stop the background LLM health monitor task."""
    global _monitor_task
    if _monitor_task is not None:
        _monitor_task.cancel()
        _monitor_task = None
