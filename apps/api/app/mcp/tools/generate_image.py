"""MCP tool ``generate_image`` — AI client sends a photo/document via navy.api.

Phase 2 (2026-04-18). This is the headline Phase 2 feature: the in-character
AI can spontaneously "show" the manager their house, car, demand letter,
bank statement, etc. via a model-generated image (``nano-banana-2`` by
default, configurable via ``settings.navy_image_model``).

The tool:
  1. POSTs to ``{navy_base_url}/images/generations`` with an OpenAI-compatible
     schema. Navy returns either a ``url`` or a base64-encoded ``b64_json``.
  2. Downloads the image (when only a URL is returned), writes it to
     ``apps/api/uploads/ai/<uuid>.png``, returns an internal path.
  3. Internal path is later rendered by the frontend ``ChatMessage`` as
     ``<img src="/uploads/ai/...">``.

Guards:
  - 60-second handler timeout — image gen is slow.
  - Max 10 calls/min per user.
  - 2 MB result cap (we return an internal URL, not the base64 blob, so
    even generous images fit).
  - auth_required=True — attached to an authenticated session.

The tool never leaks the external navy URL: we always materialize the image
locally so rotation / revocation of navy URLs can't break history.
"""

from __future__ import annotations

import base64
import logging
import re
import uuid
from pathlib import Path

import httpx

from app.config import settings
from app.mcp import ToolContext, tool
from app.mcp.schemas import enum_property, object_schema, string_property

logger = logging.getLogger(__name__)

# ── Storage ──────────────────────────────────────────────────────────
# Lives alongside other uploads; parents[2] = apps/api.
_UPLOADS_AI_DIR = Path(__file__).resolve().parents[3] / "uploads" / "ai"


def _ensure_dir() -> Path:
    _UPLOADS_AI_DIR.mkdir(parents=True, exist_ok=True)
    return _UPLOADS_AI_DIR


# Prompt templates — kept tight and in Russian so nano-banana-2 produces
# culturally appropriate imagery for Russian customers (Cyrillic signage,
# typical Russian interiors, etc.).
_CONTEXT_STYLES: dict[str, str] = {
    "document": (
        "Официальный документ на русском языке, A4, качественный скан, "
        "без цветных деталей, современная бумага. "
    ),
    "photo": (
        "Обычная фотография с мобильного телефона, естественное освещение, "
        "реалистичный стиль, без Instagram-фильтров. "
    ),
    "screenshot": (
        "Скриншот экрана смартфона или компьютера, UI на русском языке, "
        "реалистичный рендер интерфейса. "
    ),
    "receipt": (
        "Чек/квитанция на термобумаге, слегка помятая, с штампом, "
        "русский язык. "
    ),
}

# Prompt sanitation — strip anything that could be an injection attempt
# before we ship to navy.
_FORBIDDEN_PATTERN = re.compile(
    r"(ignore|disregard|system prompt|api[_\s-]*key|navy_api_key)", re.IGNORECASE
)


def _sanitize_prompt(user_prompt: str, context: str) -> str:
    """Clip, trim, prepend style hint, and scrub obvious injection markers."""

    cleaned = _FORBIDDEN_PATTERN.sub("", user_prompt).strip()
    cleaned = " ".join(cleaned.split())  # collapse whitespace
    cleaned = cleaned[:500]  # hard cap
    style = _CONTEXT_STYLES.get(context, "")
    return f"{style}{cleaned}".strip()


async def _call_navy(prompt: str) -> tuple[bytes, str]:
    """Call navy.api images/generations endpoint; return (image_bytes, mime).

    API key resolution:
      1. ``settings.navy_api_key`` — explicit override when we want a
         separate quota for image generation.
      2. ``settings.local_llm_api_key`` — fallback. navy.api is already
         the primary LLM provider for most deployments, so reusing the
         existing key avoids provisioning a second one just for images.
    """

    api_key = (
        settings.navy_api_key
        or getattr(settings, "local_llm_api_key", "")
        or ""
    )
    if not api_key:
        raise RuntimeError(
            "Neither navy_api_key nor local_llm_api_key configured"
        )

    url = f"{settings.navy_base_url.rstrip('/')}/images/generations"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": settings.navy_image_model,
        "prompt": prompt,
        "n": 1,
        "size": "1024x1024",
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.post(url, json=payload, headers=headers)
    if r.status_code != 200:
        raise RuntimeError(
            f"navy.api image gen failed: HTTP {r.status_code}: {r.text[:200]}"
        )
    body = r.json()
    datum = body.get("data", [{}])[0]

    # OpenAI-compat: either ``url`` or ``b64_json``.
    if b64 := datum.get("b64_json"):
        return base64.b64decode(b64), "image/png"

    if remote := datum.get("url"):
        async with httpx.AsyncClient(timeout=30.0) as client:
            img_r = await client.get(remote)
        if img_r.status_code != 200:
            raise RuntimeError(f"navy image fetch failed: HTTP {img_r.status_code}")
        mime = img_r.headers.get("content-type", "image/png").split(";")[0]
        return img_r.content, mime

    raise RuntimeError("navy.api response contained neither b64_json nor url")


def _save_image(data: bytes, mime: str) -> str:
    """Write bytes to ``uploads/ai/<uuid>.<ext>``, return internal path."""

    ext = "png"
    if mime.endswith("jpeg") or mime.endswith("jpg"):
        ext = "jpg"
    elif mime.endswith("webp"):
        ext = "webp"
    file_id = uuid.uuid4().hex
    out_path = _ensure_dir() / f"{file_id}.{ext}"
    out_path.write_bytes(data)
    return f"/uploads/ai/{file_id}.{ext}"


@tool(
    name="generate_image",
    description=(
        "Сгенерировать изображение, которое клиент 'отправляет' менеджеру: "
        "фото дома/машины, скан документа, скриншот, чек. Использовать "
        "экономно — максимум 1 раз за звонок, и только если без картинки "
        "ответ будет хуже. Верни короткое описание того, что изображено — "
        "оно сопроводит картинку в чате."
    ),
    parameters_schema=object_schema(
        required=["prompt", "context"],
        properties={
            "prompt": string_property(
                "1-2 предложения на русском — что именно изобразить.",
                min_length=4,
                max_length=500,
            ),
            "context": enum_property(
                "Тип контента (влияет на стиль изображения).",
                choices=["document", "photo", "screenshot", "receipt"],
            ),
            "caption": string_property(
                "Короткая подпись (до 160 символов) — появится рядом с "
                "изображением в чате.",
                max_length=160,
            ),
        },
    ),
    scope="session",
    auth_required=True,
    rate_limit_per_min=10,
    max_result_size_kb=2048,
    timeout_s=60,
    tags=("image", "write"),
)
async def generate_image(args: dict, ctx: ToolContext) -> dict:
    prompt_in = args.get("prompt") or ""
    context = args.get("context") or "photo"
    caption = (args.get("caption") or "").strip()[:160]

    if not prompt_in or len(prompt_in.strip()) < 4:
        return {
            "error": "prompt_too_short",
            "message": "Аргумент 'prompt' должен содержать хотя бы несколько слов.",
        }

    prompt = _sanitize_prompt(prompt_in, context)

    try:
        data, mime = await _call_navy(prompt)
    except Exception as exc:  # noqa: BLE001
        logger.warning("generate_image: navy call failed: %s", exc)
        # Non-fatal from the LLM's perspective — it will get the error in
        # the tool result and can fall back to describing the image in text.
        return {
            "error": "generation_failed",
            "message": str(exc)[:200],
        }

    try:
        internal_url = _save_image(data, mime)
    except Exception as exc:  # noqa: BLE001
        logger.error("generate_image: save failed: %s", exc)
        return {"error": "save_failed", "message": str(exc)[:200]}

    logger.info(
        "generate_image: ok session=%s user=%s path=%s prompt=%r",
        ctx.session_id, ctx.user_id, internal_url, prompt[:80],
    )

    return {
        "media_url": internal_url,
        "mime": mime,
        "caption": caption,
        "context": context,
    }
