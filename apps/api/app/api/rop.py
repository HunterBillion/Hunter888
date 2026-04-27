"""REST API for ROP tools (formerly Methodologist).

Access: role == rop | admin only.

The methodologist role was retired 2026-04-26 — ROPs inherited all
former methodologist permissions (scenario CRUD, scoring config, arena
knowledge chunks, sessions overview). The router is mounted at TWO
prefixes during the migration window:

  * `/rop/*`           — canonical, new clients should use this.
  * `/methodologist/*` — backward-compat alias kept until the FE pages
    under `apps/web/src/app/methodologist/` are migrated to the
    dashboard MethodologyPanel (PR B2). After B2 lands and old URLs
    are no longer requested, the alias is dropped in PR B3.

Endpoints (paths shown without prefix — both `/rop/*` and
`/methodologist/*` resolve here):
  GET    /sessions                  -- browse all training sessions
  GET    /sessions/{id}/details     -- full session details
  GET    /scenarios                  -- list scenario templates
  POST   /scenarios                  -- create scenario
  PUT    /scenarios/{id}             -- update scenario
  GET    /scoring-config             -- get scoring weights
  PUT    /scoring-config             -- update scoring weights
  GET    /arena/chunks               -- list legal knowledge chunks
  POST   /arena/chunks               -- create chunk
  PUT    /arena/chunks/{id}          -- update chunk
  DELETE /arena/chunks/{id}          -- delete chunk
"""

import logging
import uuid
from datetime import datetime, timezone

from app.core.rate_limit import limiter
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, require_role
from app.database import get_db
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter()

# All endpoints require rop or admin role. The dependency name is kept
# as `_require_methodologist` ONLY because every endpoint already binds
# to it via Depends — renaming would touch ~16 sites in this file with
# zero behaviour change. The functional check is rop+admin from this
# point on; ex-methodologist users were migrated to rop in alembic
# revision 20260426_002.
_require_methodologist = require_role("rop", "admin")


def _scenario_template_fields_from_payload(data: dict, *, for_update: bool = False) -> dict:
    """Map incoming methodologist payload to actual ScenarioTemplate ORM fields.

    Keeps backward compatibility with legacy keys (`title`, `scenario_code`,
    `scenario_type`, `archetype`, `client_brief`, `emotional_profile`, `traps`)
    while writing only real columns of `scenario_templates`.
    """
    payload = data or {}

    code = payload.get("code") or payload.get("scenario_code") or payload.get("scenario_type")
    name = payload.get("name") or payload.get("title")
    description = payload.get("description") or payload.get("client_brief")

    fields: dict = {}
    if code is not None:
        normalized_code = str(code).strip().lower().replace(" ", "_")
        if normalized_code:
            fields["code"] = normalized_code
    if name is not None:
        fields["name"] = name
    if description is not None:
        fields["description"] = description

    passthrough = (
        "group_name",
        "who_calls",
        "funnel_stage",
        "prior_contact",
        "initial_emotion",
        "initial_emotion_variants",
        "client_awareness",
        "client_motivation",
        "typical_duration_minutes",
        "max_duration_minutes",
        "typical_reply_count_min",
        "typical_reply_count_max",
        "target_outcome",
        "difficulty",
        "archetype_weights",
        "lead_sources",
        "stages",
        "recommended_chains",
        "trap_pool_categories",
        "traps_count_min",
        "traps_count_max",
        "cascades_count",
        "scoring_modifiers",
        "awareness_prompt",
        "stage_skip_reactions",
        "client_prompt_template",
        "is_active",
    )
    for key in passthrough:
        if key in payload:
            fields[key] = payload[key]

    # Legacy aliases
    if "group" in payload and "group_name" not in fields:
        fields["group_name"] = payload["group"]
    if "emotional_profile" in payload and "initial_emotion_variants" not in fields:
        fields["initial_emotion_variants"] = payload["emotional_profile"]
    if "traps" in payload and "trap_pool_categories" not in fields:
        fields["trap_pool_categories"] = payload["traps"]
    if "archetype" in payload and "archetype_weights" not in fields:
        fields["archetype_weights"] = {str(payload["archetype"]): 100.0}

    if not for_update:
        fields.setdefault("code", f"custom_{uuid.uuid4().hex[:8]}")
        fields.setdefault("name", "New Scenario")
        fields.setdefault("description", "")
    return fields


def _scenario_template_snapshot(scenario) -> dict:
    return {
        "code": scenario.code,
        "name": scenario.name,
        "description": scenario.description,
        "group_name": scenario.group_name,
        "who_calls": scenario.who_calls,
        "funnel_stage": scenario.funnel_stage,
        "prior_contact": scenario.prior_contact,
        "initial_emotion": scenario.initial_emotion,
        "initial_emotion_variants": scenario.initial_emotion_variants,
        "client_awareness": scenario.client_awareness,
        "client_motivation": scenario.client_motivation,
        "typical_duration_minutes": scenario.typical_duration_minutes,
        "max_duration_minutes": scenario.max_duration_minutes,
        "typical_reply_count_min": scenario.typical_reply_count_min,
        "typical_reply_count_max": scenario.typical_reply_count_max,
        "target_outcome": scenario.target_outcome,
        "difficulty": scenario.difficulty,
        "archetype_weights": scenario.archetype_weights,
        "lead_sources": scenario.lead_sources,
        "stages": scenario.stages,
        "recommended_chains": scenario.recommended_chains,
        "trap_pool_categories": scenario.trap_pool_categories,
        "traps_count_min": scenario.traps_count_min,
        "traps_count_max": scenario.traps_count_max,
        "cascades_count": scenario.cascades_count,
        "scoring_modifiers": scenario.scoring_modifiers,
        "awareness_prompt": scenario.awareness_prompt,
        "stage_skip_reactions": scenario.stage_skip_reactions,
        "client_prompt_template": scenario.client_prompt_template,
        "is_active": scenario.is_active,
    }


async def _create_scenario_version(db: AsyncSession, scenario, user: User, *, status_value: str = "published"):
    """Create a ScenarioVersion row.

    Used today only by ``create_scenario`` to mint v1 of a brand-new
    template. The full publish pipeline (validate + lock + supersede +
    pointer update) lives in ``services/scenario_publisher.publish_
    template`` — DON'T add new callers here without going through the
    publisher first (TZ-3 §7.3.1).

    NB: After PR C1 (alembic 20260426_003) ``content_hash`` is NOT NULL
    on scenario_versions. We reuse the publisher's deterministic hash
    helper so create-vs-publish writes produce identical hashes for
    identical snapshots.
    """
    from app.models.scenario import ScenarioVersion
    from app.services.scenario_publisher import _content_hash

    latest = (await db.execute(
        select(func.max(ScenarioVersion.version_number)).where(
            ScenarioVersion.template_id == scenario.id
        )
    )).scalar() or 0
    snapshot = _scenario_template_snapshot(scenario)
    version = ScenarioVersion(
        template_id=scenario.id,
        version_number=int(latest) + 1,
        status=status_value,
        snapshot=snapshot,
        created_by=user.id,
        published_at=datetime.now(timezone.utc) if status_value == "published" else None,
        content_hash=_content_hash(snapshot),
        # validation_report uses the column server_default '{}'::jsonb;
        # explicit publish via publish_template overwrites it with the
        # real validator output.
    )
    db.add(version)
    await db.flush()
    return version


# ═══════════════════════════════════════════════════════════════════════════
# SESSION BROWSER
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/sessions")
async def browse_sessions(
    user_id: uuid.UUID | None = Query(None),
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    min_score: float | None = Query(None),
    max_score: float | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: User = Depends(_require_methodologist),
    db: AsyncSession = Depends(get_db),
):
    """Browse all training sessions with filters."""
    from app.models.training import TrainingSession, SessionStatus

    base = select(TrainingSession, User.full_name).join(
        User, User.id == TrainingSession.user_id
    ).where(TrainingSession.status == SessionStatus.completed)

    if user_id:
        base = base.where(TrainingSession.user_id == user_id)
    if date_from:
        base = base.where(TrainingSession.started_at >= date_from)
    if date_to:
        base = base.where(TrainingSession.started_at <= date_to)
    if min_score is not None:
        base = base.where(TrainingSession.score_total >= min_score)
    if max_score is not None:
        base = base.where(TrainingSession.score_total <= max_score)

    # Count total
    count_q = select(func.count()).select_from(base.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    # Paginate
    offset = (page - 1) * page_size
    result = await db.execute(
        base.order_by(desc(TrainingSession.started_at))
        .offset(offset)
        .limit(page_size)
    )
    rows = result.all()

    items = []
    for session, user_name in rows:
        items.append({
            "id": str(session.id),
            "user_id": str(session.user_id),
            "user_name": user_name or "Anonymous",
            "scenario_title": getattr(session, "scenario_title", None),
            "archetype": getattr(session, "archetype_code", None),
            "score_total": float(session.score_total) if session.score_total else None,
            "status": session.status.value,
            "duration_seconds": session.duration_seconds,
            "started_at": session.started_at.isoformat() if session.started_at else None,
            "completed_at": session.completed_at.isoformat() if hasattr(session, "completed_at") and session.completed_at else None,
        })

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "has_next": offset + page_size < total,
    }


@router.get("/sessions/{session_id}/details")
async def get_session_details(
    session_id: uuid.UUID,
    user: User = Depends(_require_methodologist),
    db: AsyncSession = Depends(get_db),
):
    """Full session details with scoring breakdown."""
    from app.models.training import TrainingSession

    result = await db.execute(
        select(TrainingSession).where(TrainingSession.id == session_id)
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    user_r = await db.execute(select(User.full_name).where(User.id == session.user_id))
    user_name = user_r.scalar() or "Anonymous"

    return {
        "id": str(session.id),
        "user_id": str(session.user_id),
        "user_name": user_name,
        "status": session.status.value,
        "score_total": float(session.score_total) if session.score_total else None,
        "score_breakdown": getattr(session, "score_breakdown", None),
        "duration_seconds": session.duration_seconds,
        "started_at": session.started_at.isoformat() if session.started_at else None,
        "archetype_code": getattr(session, "archetype_code", None),
        "scenario_code": getattr(session, "scenario_code", None),
        "emotion_timeline": getattr(session, "emotion_timeline", None),
        "trap_data": getattr(session, "trap_data", None),
    }


# ═══════════════════════════════════════════════════════════════════════════
# SCENARIO MANAGEMENT
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/scenarios")
async def list_scenarios(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    user: User = Depends(_require_methodologist),
    db: AsyncSession = Depends(get_db),
):
    """List all scenario templates."""
    from app.models.scenario import ScenarioTemplate

    total_r = await db.execute(select(func.count(ScenarioTemplate.id)))
    total = total_r.scalar() or 0

    offset = (page - 1) * page_size
    result = await db.execute(
        select(ScenarioTemplate)
        .order_by(ScenarioTemplate.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    scenarios = result.scalars().all()

    return {
        "items": [
            {
                "id": str(s.id),
                "title": s.name,
                "description": s.description,
                "scenario_code": s.code,
                "group": getattr(s, "group_name", "custom"),
                "who_calls": getattr(s, "who_calls", "manager"),
                "is_active": getattr(s, "is_active", True),
                "created_at": s.created_at.isoformat() if s.created_at else None,
            }
            for s in scenarios
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.post("/scenarios", status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
async def create_scenario(
    request: Request,
    data: dict,
    user: User = Depends(_require_methodologist),
    db: AsyncSession = Depends(get_db),
):
    """Create a new scenario template."""
    from app.models.scenario import ScenarioTemplate

    fields = _scenario_template_fields_from_payload(data, for_update=False)
    scenario = ScenarioTemplate(**fields)
    db.add(scenario)
    await db.flush()
    version = await _create_scenario_version(db, scenario, user)
    # Point the freshly-created template at its v1 immediately so the
    # runtime resolver (PR C3) doesn't have to fall back through legacy
    # paths for newly-created templates. update_scenario doesn't touch
    # the pointer — only publish_scenario does — so this is safe.
    scenario.current_published_version_id = version.id
    await db.commit()

    return {"id": str(scenario.id), "version_id": str(version.id), "message": "Scenario created"}


@router.put("/scenarios/{scenario_id}")
@limiter.limit("10/minute")
async def update_scenario(
    request: Request,
    scenario_id: uuid.UUID,
    data: dict,
    user: User = Depends(_require_methodologist),
    db: AsyncSession = Depends(get_db),
):
    """Update an existing scenario template (draft-only).

    TZ-3 §7.3.1 (load-bearing fix of PR C2): this handler **MUST NOT
    create a ScenarioVersion**. Before this PR every save auto-published
    a new version, directly violating §8 invariant 2 ("ScenarioVersion.
    snapshot after publish never changes" — we were creating noise, not
    protecting immutability). Now save only:

      * mutates the editable ScenarioTemplate fields,
      * bumps ``draft_revision`` so concurrent editors notice each other
        on the next publish (optimistic-concurrency token, §15.1),
      * returns the new revision so the FE can pin it as
        ``expected_draft_revision`` for the eventual Publish action.

    A new published version is created **only** by ``POST
    /rop/scenarios/{id}/publish`` (handler below).
    """
    from app.models.scenario import ScenarioTemplate

    result = await db.execute(
        select(ScenarioTemplate).where(ScenarioTemplate.id == scenario_id)
    )
    scenario = result.scalar_one_or_none()
    if not scenario:
        raise HTTPException(status_code=404, detail="Scenario not found")

    fields = _scenario_template_fields_from_payload(data, for_update=True)
    for field, value in fields.items():
        setattr(scenario, field, value)

    # Bump the optimistic-concurrency cursor. None case keeps backwards
    # compat with rows that haven't been touched since the C1 backfill
    # set draft_revision=0 (server_default).
    scenario.draft_revision = int(scenario.draft_revision or 0) + 1

    await db.commit()
    return {
        "id": str(scenario.id),
        "draft_revision": scenario.draft_revision,
        "message": "Scenario draft updated (not yet published)",
    }


@router.post("/scenarios/{scenario_id}/publish")
@limiter.limit("10/minute")
async def publish_scenario(
    request: Request,
    scenario_id: uuid.UUID,
    body: dict | None = None,
    user: User = Depends(_require_methodologist),
    db: AsyncSession = Depends(get_db),
):
    """Atomically publish the current draft as a new immutable
    ScenarioVersion.

    Body (optional):
        {"expected_draft_revision": int}

    Behaviour (TZ-3 §15.1):
      * If ``expected_draft_revision`` matches the actual value on the
        template — proceed (validate → freeze → create version → update
        pointer → mark previous as superseded).
      * If it doesn't match — return 409 with ``{expected, actual}`` so
        the FE can show "another user edited this" and let the operator
        decide.
      * If the validator returns any error-level issue — return 422 with
        the full report so the FE can highlight failing fields.
      * If absent — log a warning and proceed in trust-last-writer mode
        (legacy clients before C4 frontend work).

    Concurrency guarantee: two simultaneous calls with the same
    ``expected_draft_revision`` produce exactly one 200 + one 409 (the
    publisher uses ``SELECT ... FOR UPDATE`` to serialise — see
    ``test_scenario_publisher.test_concurrent_publish_only_one_succeeds``).
    """
    from app.services.scenario_publisher import (
        PublishConflict,
        PublishValidationFailed,
        TemplateNotFound,
        publish_template,
    )

    payload = body or {}
    expected = payload.get("expected_draft_revision")
    expected_int: int | None = None
    if expected is not None:
        try:
            expected_int = int(expected)
        except (TypeError, ValueError):
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "scenario_publish_bad_revision",
                    "message": "expected_draft_revision must be an integer.",
                },
            )

    try:
        result = await publish_template(
            db,
            template_id=scenario_id,
            expected_draft_revision=expected_int,
            actor_id=user.id,
        )
    except TemplateNotFound:
        await db.rollback()
        raise HTTPException(status_code=404, detail="Scenario not found or archived")
    except PublishConflict as exc:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail={
                "code": "scenario_publish_conflict",
                "message": (
                    "Шаблон был изменён другим пользователем. Обновите "
                    "редактор и опубликуйте заново."
                ),
                "expected": exc.expected,
                "actual": exc.actual,
            },
        )
    except PublishValidationFailed as exc:
        await db.rollback()
        raise HTTPException(
            status_code=422,
            detail={
                "code": "scenario_publish_invalid",
                "message": "Сценарий не прошёл валидацию — исправьте ошибки и повторите.",
                "validation_report": exc.report.to_jsonb(),
            },
        )

    await db.commit()
    return {
        "template_id": str(result.template_id),
        "version_id": str(result.new_version_id),
        "version_number": result.new_version_number,
        "content_hash": result.content_hash,
        "superseded_version_id": (
            str(result.superseded_version_id)
            if result.superseded_version_id
            else None
        ),
        "validation_report": result.validation_report,
        "message": "Scenario published",
    }


# ═══════════════════════════════════════════════════════════════════════════
# SCORING CONFIG
# ═══════════════════════════════════════════════════════════════════════════

# Scoring weights are stored in Redis for runtime access
SCORING_CONFIG_KEY = "config:scoring_weights"

@router.get("/scoring-config")
async def get_scoring_config(
    user: User = Depends(_require_methodologist),
):
    """Get current scoring weights (L1-L10)."""
    from app.core.redis_pool import get_redis

    redis = await get_redis()
    import json
    raw = await redis.get(SCORING_CONFIG_KEY) if redis else None

    if raw:
        config = json.loads(raw)
    else:
        # Default weights
        config = {
            "weights": {
                "L1_script_adherence": 1.0,
                "L2_objection_handling": 1.0,
                "L3_communication_quality": 1.0,
                "L4_anti_patterns": 1.0,
                "L5_result": 1.0,
                "L6_chain_traversal": 0.8,
                "L7_trap_handling": 0.8,
                "L8_human_factor": 0.6,
                "L9_narrative_depth": 0.6,
                "L10_legal_accuracy": 1.0,
            },
            "thresholds": {},
            "updated_at": None,
            "updated_by": None,
        }

    return config


@router.put("/scoring-config")
@limiter.limit("5/minute")
async def update_scoring_config(
    request: Request,
    data: dict,
    user: User = Depends(_require_methodologist),
):
    """Update scoring weights."""
    from app.core.redis_pool import get_redis
    import json

    redis = await get_redis()
    if not redis:
        raise HTTPException(status_code=503, detail="Redis unavailable")

    config = {
        "weights": data.get("weights", {}),
        "thresholds": data.get("thresholds", {}),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "updated_by": str(user.id),
    }
    await redis.set(SCORING_CONFIG_KEY, json.dumps(config))
    return {"message": "Scoring config updated", "config": config}


# ═══════════════════════════════════════════════════════════════════════════
# ARENA CONTENT CRUD (LegalKnowledgeChunk)
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/arena/chunks")
async def list_chunks(
    category: str | None = Query(None),
    difficulty: int | None = Query(None, ge=1, le=5),
    search: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    user: User = Depends(_require_methodologist),
    db: AsyncSession = Depends(get_db),
):
    """List legal knowledge chunks with filters.

    Response keeps the legacy `title` / `content` / `article_reference`
    aliases for the FE ArenaContentEditor (PR #47). Internally these
    map to canonical ORM columns `law_article` / `fact_text` /
    `law_article` (so a Pydantic schema would round-trip cleanly).
    Once the FE migrates to canonical names (planned C5.1), drop the
    aliases from the response shape.
    """
    from app.models.rag import LegalKnowledgeChunk

    base = select(LegalKnowledgeChunk)

    if category:
        base = base.where(LegalKnowledgeChunk.category == category)
    if difficulty:
        base = base.where(LegalKnowledgeChunk.difficulty_level == difficulty)
    if search:
        # Search the canonical column (`fact_text`) — the legacy code
        # tried `LegalKnowledgeChunk.content.ilike(...)` which would
        # raise AttributeError because the model has no `content` column.
        # That code path was unreachable on the previous deploy because
        # callers never sent ?search=…; now the bug is fixed and the
        # endpoint works for search queries too.
        base = base.where(LegalKnowledgeChunk.fact_text.ilike(f"%{search}%"))

    total_r = await db.execute(select(func.count()).select_from(base.subquery()))
    total = total_r.scalar() or 0

    offset = (page - 1) * page_size
    result = await db.execute(
        base.order_by(LegalKnowledgeChunk.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    chunks = result.scalars().all()

    return {
        "items": [
            {
                "id": str(c.id),
                # Canonical fields
                "fact_text": c.fact_text,
                "law_article": c.law_article,
                # Legacy aliases for backward-compat with FE
                # ArenaContentEditor (PR #47). Map to canonical columns.
                "title": c.law_article or str(c.id),
                "content": (c.fact_text[:200] + "...") if c.fact_text and len(c.fact_text) > 200 else (c.fact_text or ""),
                "article_reference": c.law_article,
                # Other canonical fields
                "category": c.category.value if hasattr(c.category, 'value') else str(c.category),
                "common_errors": list(c.common_errors or []),
                "match_keywords": list(c.match_keywords or []),
                "correct_response_hint": c.correct_response_hint,
                "difficulty_level": getattr(c, "difficulty_level", 3),
                "is_court_practice": getattr(c, "is_court_practice", False),
                "court_case_reference": getattr(c, "court_case_reference", None),
                "question_templates": list(c.question_templates or []),
                "tags": list(c.tags or []),
                "created_at": c.created_at.isoformat() if c.created_at else None,
            }
            for c in chunks
        ],
        "total": total,
    }


@router.post("/arena/chunks", status_code=status.HTTP_201_CREATED)
@limiter.limit("15/minute")
async def create_chunk(
    request: Request,
    data: dict,
    user: User = Depends(_require_methodologist),
    db: AsyncSession = Depends(get_db),
):
    """Create a new legal knowledge chunk.

    TZ-3 §12 / §14.5 fix: the previous implementation passed
    `title=...` / `content=...` / `article_reference=...` kwargs to
    the LegalKnowledgeChunk constructor — fields that DON'T EXIST on
    the model. SQLAlchemy raised TypeError on every call. Now we
    validate via the canonical `ArenaChunkCreateRequest` schema (which
    accepts the legacy aliases as fallbacks but always emits canonical
    column names via `.to_orm_kwargs()`).
    """
    from app.models.rag import LegalKnowledgeChunk
    from app.schemas.rop import ArenaChunkCreateRequest

    try:
        payload = ArenaChunkCreateRequest.model_validate(data)
        kwargs = payload.to_orm_kwargs()
    except Exception as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "arena_chunk_invalid_payload",
                "message": f"Некорректный payload: {exc}",
            },
        )

    chunk = LegalKnowledgeChunk(**kwargs)
    db.add(chunk)
    await db.flush()
    await db.commit()

    return {"id": str(chunk.id), "message": "Chunk created"}


@router.put("/arena/chunks/{chunk_id}")
@limiter.limit("15/minute")
async def update_chunk(
    request: Request,
    chunk_id: uuid.UUID,
    data: dict,
    user: User = Depends(_require_methodologist),
    db: AsyncSession = Depends(get_db),
):
    """Update a legal knowledge chunk.

    Same canonical-vs-alias normalization as create. The previous
    implementation iterated over `["title", "content", ...]` and
    `setattr`'d those names onto the ORM row — silently no-op for the
    fields that don't exist on the model (SQLAlchemy adds attribute
    but doesn't persist). Drift was invisible until first read tried
    to use the missing column.
    """
    from app.models.rag import LegalKnowledgeChunk
    from app.schemas.rop import ArenaChunkUpdateRequest

    result = await db.execute(
        select(LegalKnowledgeChunk).where(LegalKnowledgeChunk.id == chunk_id)
    )
    chunk = result.scalar_one_or_none()
    if not chunk:
        raise HTTPException(status_code=404, detail="Chunk not found")

    try:
        payload = ArenaChunkUpdateRequest.model_validate(data)
        updates = payload.to_orm_kwargs()
    except Exception as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "arena_chunk_invalid_payload",
                "message": f"Некорректный payload: {exc}",
            },
        )

    for canonical_name, value in updates.items():
        setattr(chunk, canonical_name, value)

    await db.commit()
    return {"id": str(chunk.id), "message": "Chunk updated"}


@router.delete("/arena/chunks/{chunk_id}")
@limiter.limit("10/minute")
async def delete_chunk(
    request: Request,
    chunk_id: uuid.UUID,
    user: User = Depends(_require_methodologist),
    db: AsyncSession = Depends(get_db),
):
    """Delete a legal knowledge chunk."""
    from app.models.rag import LegalKnowledgeChunk

    result = await db.execute(
        select(LegalKnowledgeChunk).where(LegalKnowledgeChunk.id == chunk_id)
    )
    chunk = result.scalar_one_or_none()
    if not chunk:
        raise HTTPException(status_code=404, detail="Chunk not found")

    await db.delete(chunk)
    await db.commit()
    return {"message": "Chunk deleted"}
