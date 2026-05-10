"""Scenario catalog endpoints.

2026-05-10 (FIND-006/007/008 audit fixes):
  - Добавлен Redis-кеш на список сценариев (5 минут TTL). Сценарии
    меняются методологами раз в дни — раньше каждый visit
    /home, /center, /clients/[id], /training, /training/[id]
    дёргал 2 SQL-запроса (templates + legacy join). Теперь fast path
    ~5 ms из Redis vs ~700 ms cold.
  - Добавлены реальные ?limit=&offset= параметры (FIND-006). До этого
    фронт мог передать `?limit=5` — параметр молча игнорировался,
    отдавалось всё (72 сценария, 27 KB). Теперь — настоящая пагинация.
  - Сортировка по «sweet spot» (близость difficulty к уровню юзера)
    осталась — она и определяет порядок выдачи; limit/offset режут
    хвост. Total-count в response для фронта.
"""

import json
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core import errors as err
from app.core.deps import get_current_user
from app.database import get_db
from app.models.character import Character
from app.models.scenario import Scenario, ScenarioTemplate
from app.models.script import Script
from app.models.user import User
from app.schemas.training import ScenarioResponse

logger = logging.getLogger(__name__)
router = APIRouter()


# Recommended difficulty range per experience level (used for sorting, NOT filtering)
_DIFFICULTY_SWEET_SPOT = {
    "beginner": 3,
    "intermediate": 5,
    "advanced": 7,
}

_SCENARIOS_CACHE_TTL_SEC = 300  # 5 минут — сценарии редко меняются
_SCENARIOS_CACHE_KEY_PREFIX = "scenarios:list:v1"


async def _scenarios_cache_get(sweet: int) -> list[dict] | None:
    """Try Redis cache. Return parsed list or None on miss/error.
    fail-open: при недоступности Redis возвращаем None, не валим запрос.
    """
    try:
        from app.core.redis_pool import get_redis
        r = get_redis()
        if r is None:
            return None
        cached = await r.get(f"{_SCENARIOS_CACHE_KEY_PREFIX}:sweet={sweet}")
        if not cached:
            return None
        return json.loads(cached)
    except Exception as exc:  # noqa: BLE001
        logger.debug("scenarios cache read failed: %s", exc)
        return None


async def _scenarios_cache_set(sweet: int, data: list[dict]) -> None:
    """Write to cache. fail-open."""
    try:
        from app.core.redis_pool import get_redis
        r = get_redis()
        if r is None:
            return
        await r.setex(
            f"{_SCENARIOS_CACHE_KEY_PREFIX}:sweet={sweet}",
            _SCENARIOS_CACHE_TTL_SEC,
            json.dumps(data),
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("scenarios cache write failed: %s", exc)


@router.get("", response_model=list[ScenarioResponse])
@router.get("/", response_model=list[ScenarioResponse], include_in_schema=False)
async def list_scenarios(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int | None = Query(None, ge=1, le=200, description="Сколько сценариев вернуть (default: все)"),
    offset: int = Query(0, ge=0, description="Сколько пропустить (для пагинации)"),
):
    """List active scenarios from `scenario_templates` (60 records, DOC_05 8 groups).

    Falls back to legacy `scenarios` table for any rows not linked to
    a template. Sorted by closeness to user's experience-level sweet spot.

    2026-05-10:
      - Redis cache 5 min на полный список per-user-sweet-spot.
      - ?limit=&offset= — реальная пагинация. До фикса `limit` молча
        игнорировался (FIND-006).
    """
    prefs = user.preferences or {}
    exp_level = prefs.get("experience_level")
    sweet = _DIFFICULTY_SWEET_SPOT.get(exp_level, 5) if exp_level else 5  # type: ignore[arg-type]

    # ── Fast path: cache hit ──
    cached = await _scenarios_cache_get(sweet)
    if cached is not None:
        items = [ScenarioResponse(**row) for row in cached]
    else:
        items = await _build_scenarios_list(db, sweet)
        # Cache stores serialised dicts (Pydantic → dict for json.dumps)
        try:
            await _scenarios_cache_set(sweet, [s.model_dump(mode="json") for s in items])
        except AttributeError:
            # Pydantic v1 fallback
            await _scenarios_cache_set(sweet, [s.dict() for s in items])

    # Apply pagination AFTER sorting (sort is cached; pagination is per-request)
    if offset:
        items = items[offset:]
    if limit is not None:
        items = items[:limit]
    return items


async def _build_scenarios_list(db: AsyncSession, sweet: int) -> list[ScenarioResponse]:
    """Cold-path scenario builder — runs when Redis cache misses.
    Two queries: scenario_templates + legacy scenarios fallback.
    Sort: closest to sweet-spot first.
    """
    items: list[ScenarioResponse] = []
    seen_ids: set[uuid.UUID] = set()

    # ── Primary: scenario_templates ──
    tpl_result = await db.execute(
        select(ScenarioTemplate).where(ScenarioTemplate.is_active.is_(True))
    )
    templates = tpl_result.scalars().all()
    for tpl in templates:
        items.append(ScenarioResponse(
            id=tpl.id,
            title=tpl.name,
            description=tpl.description,
            scenario_type=tpl.code,
            difficulty=tpl.difficulty,
            estimated_duration_minutes=tpl.typical_duration_minutes,
            character_name=None,
        ))
        seen_ids.add(tpl.id)

    # ── Fallback: legacy scenarios not linked to templates ──
    legacy_query = (
        select(Scenario, Character.name.label("character_name"))
        .outerjoin(Character, Scenario.character_id == Character.id)
        .where(Scenario.is_active.is_(True))
    )
    legacy_result = await db.execute(legacy_query)
    legacy_rows = legacy_result.all()
    for row in legacy_rows:
        if row.Scenario.id in seen_ids:
            continue
        if row.Scenario.template_id and row.Scenario.template_id in seen_ids:
            continue
        items.append(ScenarioResponse(
            id=row.Scenario.id,
            title=row.Scenario.title,
            description=row.Scenario.description,
            scenario_type=row.Scenario.scenario_type.value,
            difficulty=row.Scenario.difficulty,
            estimated_duration_minutes=row.Scenario.estimated_duration_minutes,
            character_name=row.character_name,
        ))

    items.sort(key=lambda s: (abs(s.difficulty - sweet), s.difficulty))
    return items


@router.get("/{scenario_id}")
async def get_scenario(
    scenario_id: uuid.UUID,
    _user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get scenario with character and script details.

    Checks legacy scenarios table first, then scenario_templates as fallback.
    """
    result = await db.execute(
        select(Scenario).where(Scenario.id == scenario_id, Scenario.is_active.is_(True))
    )
    scenario = result.scalar_one_or_none()
    if not scenario:
        # Fallback: check scenario_templates
        tpl_result = await db.execute(
            select(ScenarioTemplate).where(
                ScenarioTemplate.id == scenario_id, ScenarioTemplate.is_active.is_(True)
            )
        )
        tpl = tpl_result.scalar_one_or_none()
        if tpl is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=err.SCENARIO_NOT_FOUND)
        # Return template data in scenario-compatible format
        return {
            "id": str(tpl.id),
            "title": tpl.name,
            "description": tpl.description,
            "scenario_type": tpl.code,
            "difficulty": tpl.difficulty,
            "estimated_duration_minutes": tpl.typical_duration_minutes,
            "character": None,
            "script": None,
        }

    # Get character
    char_result = await db.execute(select(Character).where(Character.id == scenario.character_id))
    character = char_result.scalar_one_or_none()

    # Get script with checkpoints
    script_data = None
    if scenario.script_id:
        script_result = await db.execute(
            select(Script).options(selectinload(Script.checkpoints)).where(Script.id == scenario.script_id)
        )
        script = script_result.scalar_one_or_none()
        if script:
            script_data = {
                "id": str(script.id),
                "title": script.title,
                "checkpoints": [
                    {
                        "title": cp.title,
                        "description": cp.description,
                        "order_index": cp.order_index,
                        "weight": cp.weight,
                    }
                    for cp in sorted(script.checkpoints, key=lambda c: c.order_index)
                ],
            }

    return {
        "id": str(scenario.id),
        "title": scenario.title,
        "description": scenario.description,
        "scenario_type": scenario.scenario_type.value,
        "difficulty": scenario.difficulty,
        "estimated_duration_minutes": scenario.estimated_duration_minutes,
        "character": {
            "id": str(character.id),
            "name": character.name,
            "slug": character.slug,
            "description": character.description,
            "difficulty": character.difficulty,
            "initial_emotion": character.initial_emotion.value,
        } if character else None,
        "script": script_data,
    }
