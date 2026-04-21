"""Health check and monitoring endpoints.

/monitoring/health — public (for Docker/LB healthchecks), returns only status
/monitoring/health/detail — auth required, returns service details
/monitoring/metrics — auth required, Prometheus format
"""

import time

from fastapi import APIRouter, Depends

from app.config import settings
from app.core.deps import get_current_user, require_role
from app.core.redis_pool import get_redis, redis_health_check
from app.database import async_session

from sqlalchemy import text

router = APIRouter()


@router.get("/monitoring/health")
async def health_check_public():
    """Public health check — returns only status (for Docker/LB).

    Does NOT expose service internals.
    """
    try:
        async with async_session() as db:
            await db.execute(text("SELECT 1"))
    except Exception:
        return {"status": "degraded"}

    try:
        if not await redis_health_check():
            return {"status": "degraded"}
    except Exception:
        return {"status": "degraded"}

    return {"status": "ok"}


@router.get("/health")
async def health_check_alias():
    """Shallow alias for /monitoring/health used by local dev and reverse proxies."""
    return await health_check_public()


@router.get("/monitoring/health/detail")
async def health_check_detail(_user=Depends(require_role("admin"))):
    """Detailed health check — admin only. Returns DB/Redis status."""
    checks = {}
    overall = "ok"

    # Check PostgreSQL
    try:
        async with async_session() as db:
            result = await db.execute(text("SELECT 1"))
            result.scalar()
        checks["postgres"] = "ok"
    except Exception as e:
        checks["postgres"] = f"error: {type(e).__name__}"
        overall = "degraded"

    # Check Redis (uses shared pool)
    try:
        r = get_redis()
        await r.ping()
        checks["redis"] = "ok"
    except Exception as e:
        checks["redis"] = f"error: {type(e).__name__}"
        overall = "degraded"

    # Check Local LLM (Mac Mini / Gemma)
    try:
        from app.services.llm_health import get_llm_status
        llm_status = await get_llm_status()
        checks["local_llm"] = llm_status["status"]
        checks["local_llm_model"] = llm_status.get("model", "unknown")
        if llm_status["status"] != "ok":
            overall = "degraded"
    except Exception as e:
        checks["local_llm"] = f"error: {type(e).__name__}"
        overall = "degraded"

    return {
        "status": overall,
        "service": "ai-trainer-api",
        "version": "0.2.0",
        "checks": checks,
        "timestamp": time.time(),
    }


@router.get("/monitoring/llm-status")
async def llm_status():
    """Public LLM status endpoint — used by frontend for degradation banner.

    Returns:
        status: "ok" | "offline" | "disabled" | "fallback"
        model: model name if online
        fallback: True if using cloud fallback
    """
    try:
        from app.core.redis_pool import get_redis
        r = get_redis()
        if r:
            status = await r.get(REDIS_KEY_LLM_STATUS)
            model = await r.get(REDIS_KEY_LLM_MODEL)
            if status is not None:
                is_online = status == "1" or status == b"1"
                model_str = model.decode() if isinstance(model, bytes) else (model or "unknown")
                return {
                    "status": "ok" if is_online else "fallback",
                    "model": model_str if is_online else None,
                    "fallback": not is_online,
                    "message": None if is_online else "AI-сервер недоступен. Работаем в облачном режиме.",
                }
    except Exception:
        pass

    # No Redis data — check directly
    from app.services.llm_health import check_local_llm
    result = await check_local_llm()
    is_online = result["status"] == "ok"
    return {
        "status": result["status"],
        "model": result.get("model"),
        "fallback": not is_online,
        "message": None if is_online else "AI-сервер недоступен. Работаем в облачном режиме.",
    }


# Redis key imports for llm-status endpoint
REDIS_KEY_LLM_STATUS = "llm:local:available"
REDIS_KEY_LLM_MODEL = "llm:local:model"


@router.get("/monitoring/metrics")
async def prometheus_metrics(_user=Depends(require_role("admin"))):
    """Prometheus metrics — admin only."""
    from app.database import engine

    pool = engine.pool
    lines = [
        "# HELP db_pool_size Current database connection pool size",
        "# TYPE db_pool_size gauge",
        f"db_pool_size {pool.size()}",
        "# HELP db_pool_checked_in Number of idle connections in pool",
        "# TYPE db_pool_checked_in gauge",
        f"db_pool_checked_in {pool.checkedin()}",
        "# HELP db_pool_checked_out Number of active connections from pool",
        "# TYPE db_pool_checked_out gauge",
        f"db_pool_checked_out {pool.checkedout()}",
        "# HELP db_pool_overflow Number of overflow connections",
        "# TYPE db_pool_overflow gauge",
        f"db_pool_overflow {pool.overflow()}",
        "# HELP app_info Application version info",
        "# TYPE app_info gauge",
        'app_info{version="0.1.0",env="' + settings.app_env + '"} 1',
    ]

    from fastapi.responses import PlainTextResponse

    return PlainTextResponse("\n".join(lines) + "\n", media_type="text/plain")


@router.get("/tts/debug")
async def tts_debug(_user=Depends(require_role("admin"))):
    """TTS diagnostic — admin only. Check if ElevenLabs is configured and working.

    Returns detailed status of each TTS component.
    """
    import os
    from app.services.tts import (
        is_tts_available,
        get_tts_stats,
        synthesize_speech,
        pick_voice_for_session,
        TTSError,
        TTSQuotaExhausted,
    )

    result = {
        "step_1_env_vars": {},
        "step_2_settings": {},
        "step_3_is_configured": False,
        "step_4_voice_assignment": {},
        "step_5_api_call": {},
        "step_6_stats": {},
    }

    # Step 1: Raw env vars
    result["step_1_env_vars"] = {
        "ELEVENLABS_API_KEY": ("set (%d chars)" % len(os.environ.get("ELEVENLABS_API_KEY", "")))
            if os.environ.get("ELEVENLABS_API_KEY") else "NOT SET",
        "ELEVENLABS_VOICE_IDS": os.environ.get("ELEVENLABS_VOICE_IDS", "NOT SET")[:80],
        "ELEVENLABS_ENABLED": os.environ.get("ELEVENLABS_ENABLED", "NOT SET"),
        "ELEVENLABS_MODEL": os.environ.get("ELEVENLABS_MODEL", "NOT SET"),
    }

    # Step 2: Parsed settings
    result["step_2_settings"] = {
        "api_key_present": bool(settings.elevenlabs_api_key),
        "api_key_length": len(settings.elevenlabs_api_key),
        "voice_ids_raw": settings.elevenlabs_voice_ids[:80] if settings.elevenlabs_voice_ids else "",
        "voice_list": settings.elevenlabs_voice_list,
        "voice_count": len(settings.elevenlabs_voice_list),
        "enabled": settings.elevenlabs_enabled,
        "model": settings.elevenlabs_model,
        "timeout": settings.elevenlabs_timeout_seconds,
    }

    # Step 3: is_configured check
    result["step_3_is_configured"] = is_tts_available()

    # Step 4: Voice assignment test
    test_session_id = "tts-debug-test"
    try:
        voice = pick_voice_for_session(test_session_id)
        result["step_4_voice_assignment"] = {"status": "ok", "voice_id": voice}
    except TTSError as e:
        result["step_4_voice_assignment"] = {"status": "error", "error": str(e)}

    # Step 5: Actual API call
    if result["step_3_is_configured"] and result["step_4_voice_assignment"].get("voice_id"):
        try:
            tts_result = await synthesize_speech(
                text="Здравствуйте, это тестовое сообщение.",
                voice_id=result["step_4_voice_assignment"]["voice_id"],
                use_cache=False,
            )
            result["step_5_api_call"] = {
                "status": "ok",
                "audio_bytes": len(tts_result.audio_bytes),
                "format": tts_result.format,
                "latency_ms": tts_result.latency_ms,
                "duration_estimate_ms": tts_result.duration_estimate_ms,
            }
        except TTSQuotaExhausted as e:
            result["step_5_api_call"] = {"status": "quota_exhausted", "error": str(e)}
        except TTSError as e:
            result["step_5_api_call"] = {"status": "error", "error": str(e)}
        except Exception as e:
            result["step_5_api_call"] = {"status": "unexpected_error", "error": f"{type(e).__name__}: {e}"}
    else:
        result["step_5_api_call"] = {"status": "skipped", "reason": "TTS not configured"}

    # Step 6: Full stats
    result["step_6_stats"] = get_tts_stats()

    # Release test voice
    from app.services.tts import release_session_voice
    release_session_voice(test_session_id)

    # Overall verdict
    all_ok = (
        result["step_3_is_configured"]
        and result["step_4_voice_assignment"].get("status") == "ok"
        and result["step_5_api_call"].get("status") == "ok"
    )
    result["verdict"] = "TTS WORKING" if all_ok else "TTS BROKEN — check steps above"

    return result
