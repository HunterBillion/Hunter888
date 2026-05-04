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
from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Header,
    HTTPException,
    Query,
    Request,
    UploadFile,
    status,
)
from sqlalchemy import desc, func, select, types as sqltypes
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, require_role
from app.database import get_db
from app.models.user import User
from app.services.audit import write_audit_log

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

    # SEC-2026-05-02 (9-layer audit fix #9): restrict to caller's team.
    # See ``_filter_session_by_caller_team`` for the rationale + admin
    # escape semantics. The JOIN against ``User`` is already in ``base``,
    # so the helper just appends a ``WHERE users.team_id = ...``.
    base = _filter_session_by_caller_team(base, user)

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

    # SEC-2026-05-02 (9-layer audit fix #9): team-scope guard on the
    # session-details lookup. Without this any ROP could read sensitive
    # training transcripts of users in other teams.
    await _scope_check_session(db, session.user_id, user)

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
@limiter.limit("60/minute")
async def list_chunks(
    request: Request,
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
    aliases for the FE ArenaContentEditor — but `content` now equals
    the FULL `fact_text`, not the `[:200] + "..."` truncation that hid
    the tail of every chunk on prod (375/375 affected). The FE clamps
    visually via CSS; the API speaks truth.

    Search now matches across `fact_text || law_article || tags ||
    match_keywords || court_case_reference` so the methodologist's
    queries like "несостоятельность" / "304-ЭС17" / a tag name don't
    return zero hits when the term is present in a non-text field.
    """
    from sqlalchemy import or_

    from app.models.rag import LegalKnowledgeChunk

    # Soft-delete filter: tombstones are excluded by default; admins
    # can opt in via ?include_deleted=1 for forensics / undelete UI.
    base = select(LegalKnowledgeChunk).where(LegalKnowledgeChunk.deleted_at.is_(None))

    if category:
        base = base.where(LegalKnowledgeChunk.category == category)
    if difficulty:
        base = base.where(LegalKnowledgeChunk.difficulty_level == difficulty)
    if search:
        like = f"%{search}%"
        base = base.where(
            or_(
                LegalKnowledgeChunk.fact_text.ilike(like),
                LegalKnowledgeChunk.law_article.ilike(like),
                LegalKnowledgeChunk.court_case_reference.ilike(like),
                LegalKnowledgeChunk.correct_response_hint.ilike(like),
                # JSONB match_keywords / tags — cast to text so ILIKE works
                # even before we add a proper trigram index. Avoids the
                # "методолог искал по тегу — 0 хитов" workflow trap.
                func.cast(LegalKnowledgeChunk.match_keywords, sqltypes.String).ilike(like),
                func.cast(LegalKnowledgeChunk.tags, sqltypes.String).ilike(like),
            )
        )

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
                # ArenaContentEditor. Map to canonical columns. `content`
                # is now FULL fact_text — the [:200] truncation pre-fix
                # made the UI lossy on every chunk.
                "title": c.law_article or str(c.id),
                "content": c.fact_text or "",
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
                "updated_at": c.updated_at.isoformat() if getattr(c, "updated_at", None) else None,
                # Diagnostics — lets the FE flag "embedding pending"
                # rows (NULL means RAG can't find this chunk yet).
                "embedding_ready": c.embedding is not None,
                "retrieval_count": int(getattr(c, "retrieval_count", 0) or 0),
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
    chunk.created_by = user.id
    chunk.last_edited_by = user.id
    db.add(chunk)
    await db.flush()

    # Audit trail (152-ФЗ touchpoint). Pre-fix the entire CRUD surface
    # was un-audited — operators couldn't answer "who created this
    # chunk and why" from the panel. The same write_audit_log helper
    # is used by admin_users.py:patch_user.
    await write_audit_log(
        db,
        actor=user,
        action="arena_chunk_create",
        entity_type="legal_knowledge_chunks",
        entity_id=chunk.id,
        new_values={
            "fact_text": (chunk.fact_text or "")[:500],
            "law_article": chunk.law_article,
            "category": getattr(chunk.category, "value", str(chunk.category)),
            "difficulty_level": chunk.difficulty_level,
        },
        request=request,
    )
    await db.commit()

    # Live re-embedding: enqueue so the new chunk gets a vector and
    # becomes RAG-discoverable before the next API restart. Pre-fix the
    # only path through `enqueue_chunk` was the auto-publish import flow
    # (line ~1718) — manually-created chunks waited until cold sweep,
    # which only runs at boot.
    await _enqueue_chunk_safely(chunk.id)

    return {"id": str(chunk.id), "message": "Chunk created"}


@router.put("/arena/chunks/{chunk_id}")
@limiter.limit("15/minute")
async def update_chunk(
    request: Request,
    chunk_id: uuid.UUID,
    data: dict,
    user: User = Depends(_require_methodologist),
    db: AsyncSession = Depends(get_db),
    if_match: str | None = Header(None, alias="If-Match"),
):
    """Update a legal knowledge chunk.

    Optimistic locking via the ``If-Match`` header.

    Send the chunk's current ``updated_at`` (ISO-8601, exact bytes from
    the GET response) as ``If-Match: <updated_at>``. The server compares
    against the persisted value and rejects with 412 ``stale_chunk`` if
    they diverge — that means another editor saved between this PUT's
    GET and its commit. The FE then re-fetches and the human reconciles.

    The header is OPTIONAL during the PR-2/PR-3 transition (the FE form
    will start sending it in PR-3). Without the header the legacy
    last-write-wins behaviour is preserved so existing scripts don't
    break, but a deprecation warning is logged so we can drop the
    fallback once the FE rolls out the new editor.

    Soft-deleted chunks (``deleted_at IS NOT NULL``) reject with 410
    ``chunk_deleted`` — restoring them is an admin action that goes
    through a separate endpoint (TBD in PR-3).
    """
    from app.models.rag import LegalKnowledgeChunk
    from app.schemas.rop import ArenaChunkUpdateRequest

    result = await db.execute(
        select(LegalKnowledgeChunk).where(LegalKnowledgeChunk.id == chunk_id)
    )
    chunk = result.scalar_one_or_none()
    if not chunk:
        raise HTTPException(status_code=404, detail="Chunk not found")
    if chunk.deleted_at is not None:
        raise HTTPException(
            status_code=410,
            detail={
                "code": "chunk_deleted",
                "message": "Чанк помечен удалённым. Сначала восстановите его.",
                "deleted_at": chunk.deleted_at.isoformat(),
            },
        )

    if if_match is not None:
        current = (
            chunk.updated_at.isoformat() if chunk.updated_at is not None else ""
        )
        if if_match.strip().strip('"') != current:
            raise HTTPException(
                status_code=412,
                detail={
                    "code": "stale_chunk",
                    "message": (
                        "Чанк изменён другим редактором. Перезагрузите страницу "
                        "и примените свои правки повторно."
                    ),
                    "expected": if_match,
                    "actual": current,
                },
            )

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
    if not updates:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "arena_chunk_no_fields",
                "message": "Нечего обновлять — payload не содержит изменяемых полей.",
            },
        )

    # Snapshot for audit diff — only the fields actually being touched.
    old_values = {
        name: (
            getattr(chunk, name).value
            if hasattr(getattr(chunk, name), "value")
            else (
                str(getattr(chunk, name))
                if isinstance(getattr(chunk, name), uuid.UUID)
                else getattr(chunk, name)
            )
        )
        for name in updates
        if hasattr(chunk, name)
    }

    for canonical_name, value in updates.items():
        setattr(chunk, canonical_name, value)
    chunk.last_edited_by = user.id

    await db.flush()

    new_values = {
        name: (
            getattr(chunk, name).value
            if hasattr(getattr(chunk, name), "value")
            else (
                str(getattr(chunk, name))
                if isinstance(getattr(chunk, name), uuid.UUID)
                else getattr(chunk, name)
            )
        )
        for name in updates
        if hasattr(chunk, name)
    }

    await write_audit_log(
        db,
        actor=user,
        action="arena_chunk_update",
        entity_type="legal_knowledge_chunks",
        entity_id=chunk.id,
        old_values=old_values,
        new_values=new_values,
        request=request,
    )

    # Snapshot the values we need in the response BEFORE commit —
    # SQLAlchemy expires attributes on commit by default, and the next
    # access triggers a sync lazy-load that the async session can't
    # service without a greenlet wrapper (MissingGreenlet error).
    chunk_id_str = str(chunk.id)
    updated_at_iso = (
        chunk.updated_at.isoformat() if chunk.updated_at is not None else None
    )

    await db.commit()

    # The `before_update` listener (apps/api/app/models/rag.py) nulls
    # `embedding` whenever `fact_text` or `law_article` change. Without
    # the enqueue here the chunk is invisible to RAG until the next
    # cold sweep at API restart — i.e. for hours-to-days. Enqueue every
    # update; the worker's hash-check de-dups no-op edits cheaply.
    await _enqueue_chunk_safely(chunk.id)

    return {
        "id": chunk_id_str,
        "message": "Chunk updated",
        "updated_at": updated_at_iso,
    }


@router.delete("/arena/chunks/{chunk_id}")
@limiter.limit("10/minute")
async def delete_chunk(
    request: Request,
    chunk_id: uuid.UUID,
    user: User = Depends(_require_methodologist),
    db: AsyncSession = Depends(get_db),
):
    """Soft-delete a legal knowledge chunk.

    Pre-fix this endpoint did ``db.delete(chunk)`` — physical row drop.
    That broke the FK target on ``legal_validation_results.knowledge_
    chunk_id`` (set NULL → orphaned analytics) and lost the chunk's
    history forever. Now we set ``deleted_at = now()`` and the chunk
    stops appearing in list/RAG retrievals (the indexes filter on
    ``deleted_at IS NULL``) but stays in the DB for audit + undelete.
    """
    from app.models.rag import LegalKnowledgeChunk

    result = await db.execute(
        select(LegalKnowledgeChunk).where(LegalKnowledgeChunk.id == chunk_id)
    )
    chunk = result.scalar_one_or_none()
    if not chunk:
        raise HTTPException(status_code=404, detail="Chunk not found")
    if chunk.deleted_at is not None:
        # Idempotent — repeating DELETE on a tombstone is a no-op,
        # not a 404 (that would suggest the chunk never existed).
        return {
            "message": "Chunk already deleted",
            "deleted_at": chunk.deleted_at.isoformat(),
        }

    chunk.deleted_at = datetime.now(timezone.utc)
    chunk.last_edited_by = user.id

    await write_audit_log(
        db,
        actor=user,
        action="arena_chunk_delete",
        entity_type="legal_knowledge_chunks",
        entity_id=chunk.id,
        old_values={
            "fact_text": (chunk.fact_text or "")[:500],
            "law_article": chunk.law_article,
            "category": getattr(chunk.category, "value", str(chunk.category)),
        },
        new_values={"deleted_at": chunk.deleted_at.isoformat()},
        request=request,
    )
    await db.commit()
    return {"message": "Chunk deleted", "soft_delete": True}


async def _enqueue_chunk_safely(chunk_id: uuid.UUID) -> None:
    """Best-effort enqueue for live embedding backfill.

    The live worker is gated by `arena_embedding_live_backfill_enabled`
    and a healthy Redis connection. Both can be off — when they are,
    we'd rather still return 200 from the CRUD path than fail the whole
    edit because the indexer is down. The eventual-consistency story is
    that the next cold sweep (API boot) picks up the row anyway.
    """
    try:
        from app.services.embedding_live_backfill import enqueue_chunk

        await enqueue_chunk(chunk_id)
    except Exception:  # pragma: no cover — best-effort; logged centrally
        logger.warning("arena: enqueue_chunk failed", exc_info=True)


# ═══════════════════════════════════════════════════════════════════════════
# TZ-5 — INPUT FUNNEL: training material → ScenarioDraft → ScenarioTemplate
# ═══════════════════════════════════════════════════════════════════════════
#
# Three endpoints make up the import flow that the FE
# /dashboard/methodology/scenarios/import surface consumes:
#
#   POST   /scenarios/import           — upload bytes, run extractor,
#                                         persist ScenarioDraft.
#   GET    /scenarios/drafts           — list drafts (with optional
#                                         status filter).
#   GET    /scenarios/drafts/{id}      — fetch one draft (full payload).
#   PUT    /scenarios/drafts/{id}      — ROP edits the structured payload
#                                         in-place; status flips to
#                                         'edited'.
#   POST   /scenarios/drafts/{id}/create-scenario — convert draft to
#                                         ScenarioTemplate + v1 (status=
#                                         draft, NOT auto-published).
#   POST   /scenarios/drafts/{id}/discard         — terminal discard.
#
# Auth: every endpoint sits behind ``_require_methodologist`` (rop +
# admin). Rate limits are deliberately low because the import flow is
# manual, not bulk.

_LOW_CONFIDENCE_THRESHOLD = 0.6  # TZ-5 §4 invariant


def _is_admin(caller: User) -> bool:
    """Single source of truth for admin escape. Used by every team-scope
    helper so a future rename of ``UserRole.admin`` only changes one
    place. Admins always bypass team-anchored gates because their role
    is intentionally cross-team (audit + recovery).
    """
    return getattr(caller.role, "value", str(caller.role)) == "admin"


def _filter_session_by_caller_team(stmt, caller: User):
    """Append ``team_id``-anchored WHERE to a ``TrainingSession`` SELECT.

    SEC-2026-05-02 (9-layer audit fix #9): ``browse_sessions`` and
    ``get_session_details`` previously filtered ONLY by role
    (``rop`` or ``admin``). A ROP from team-A could read every team-B
    session by hitting these endpoints with a session_id, or page
    through them via the listing. This helper restricts the view to
    sessions owned by users in the caller's own team.

    Admins bypass the filter (cross-team audit). ROP without a team
    gets an empty result set, NOT a 403 — the listing endpoint is
    paginated and surfacing 403 would break legitimate pre-team
    accounts; an empty result is informative enough.

    The filter is composed via a JOIN ON ``users.team_id`` so the
    base query stays decoupled from caller team resolution. Caller
    must have already JOINed ``User`` (which all session endpoints
    do for the user_name column).
    """
    if _is_admin(caller):
        return stmt
    caller_team = getattr(caller, "team_id", None)
    if caller_team is None:
        # No team to anchor on — return a trivially-empty filter.
        # We use a literal-false WHERE rather than 403 so the listing
        # endpoint pages cleanly with zero results.
        return stmt.where(User.team_id == uuid.UUID(int=0))
    return stmt.where(User.team_id == caller_team)


async def _scope_check_session(
    db: AsyncSession,
    session_user_id: uuid.UUID,
    caller: User,
) -> None:
    """Verify the caller can read a single ``TrainingSession``.

    SEC-2026-05-02: counterpart to :func:`_filter_session_by_caller_team`
    for the ``get_session_details`` endpoint where pagination doesn't
    apply. Raises 403 if the session's owner is in a different team.
    Admins bypass (cross-team audit).
    """
    if _is_admin(caller):
        return
    caller_team = getattr(caller, "team_id", None)
    if caller_team is None:
        raise HTTPException(
            status_code=403,
            detail="Доступ запрещён: ваш аккаунт не привязан к команде.",
        )
    owner_team = (
        await db.execute(select(User.team_id).where(User.id == session_user_id))
    ).scalar_one_or_none()
    if owner_team is None or owner_team != caller_team:
        raise HTTPException(
            status_code=403,
            detail="Доступ запрещён: сессия принадлежит другой команде.",
        )


async def _scope_check_draft(
    db: AsyncSession,
    draft,
    caller: User,
) -> None:
    """Audit fix (#6 from 5-agent review) — enforce team-scoped access on
    a ScenarioDraft. Without this any ROP could read/edit/approve/discard
    another team's drafts because all draft endpoints only had a role
    gate (rop+admin) and never checked the relationship between the
    caller's team and the draft's owner.

    Rules:
      * admin role: always allowed (cross-team audit + recovery).
      * draft.created_by IS NULL (legacy / system-imported): allowed
        for any rop+admin caller — no team to anchor on.
      * otherwise: caller's team_id must match the team of the user
        who created the draft. ROP without a team gets denied.

    Raises HTTPException(403) when access is forbidden.
    """
    is_admin = getattr(caller.role, "value", str(caller.role)) == "admin"
    if is_admin:
        return
    if draft.created_by is None:
        return
    creator_row = await db.execute(
        select(User.team_id).where(User.id == draft.created_by)
    )
    creator_team_id = creator_row.scalar_one_or_none()
    if creator_team_id is None:
        # Creator has no team_id → can't anchor. Refuse, surface
        # message that admin can recover.
        raise HTTPException(
            status_code=403,
            detail="Доступ запрещён: автор черновика не привязан к команде.",
        )
    if caller.team_id != creator_team_id:
        raise HTTPException(
            status_code=403,
            detail="Доступ запрещён: черновик принадлежит другой команде.",
        )


def _draft_to_response(
    draft, *, attachment_filename: str | None = None, include_raw: bool = False
) -> dict:  # noqa: D401
    return _build_draft_response(draft, attachment_filename=attachment_filename, include_raw=include_raw)


def _build_draft_response(
    draft, *, attachment_filename: str | None = None, include_raw: bool = False
) -> dict:
    """Serialize a ``ScenarioDraft`` row for the API.

    Implements TZ-5 §4 invariant: when ``confidence < 0.6`` the structured
    payload is hidden (``extracted_visible=False``) and the FE falls back
    to showing ``source_text`` only.

    PR-1.1 audit fix — ``extracted_raw`` (the unfiltered LLM output that
    may contain hallucinated PII fragments the second-pass scrub didn't
    catch) is now ONLY included when ``include_raw=True``. The list
    endpoint omits it; the detail endpoint accepts ``?include_raw=1``.
    Without this gate, low-confidence drafts could leak hallucinated
    phone-number-shaped strings to any FE consumer that bypassed the
    "show anyway" toggle.
    """
    payload = draft.extracted or {}
    visible = float(draft.confidence or 0.0) >= _LOW_CONFIDENCE_THRESHOLD
    response: dict = {
        "id": str(draft.id),
        "attachment_id": str(draft.attachment_id),
        "attachment_filename": attachment_filename,
        # PR-2 multi-route fields
        "route_type": getattr(draft, "route_type", "scenario"),
        "target_id": str(draft.target_id) if getattr(draft, "target_id", None) else None,
        "scenario_template_id": (
            str(draft.scenario_template_id) if draft.scenario_template_id else None
        ),
        "status": draft.status,
        "confidence": float(draft.confidence or 0.0),
        "original_confidence": (
            float(draft.original_confidence)
            if getattr(draft, "original_confidence", None) is not None
            else None
        ),
        "extracted_visible": visible,
        "extracted": payload if visible else None,
        # Auth-gated download URL (replaces direct StaticFiles access).
        "download_url": f"/api/rop/scenarios/drafts/{draft.id}/download",
        "source_text": draft.source_text,
        "error_message": draft.error_message,
        "created_at": draft.created_at.isoformat() if draft.created_at else None,
        "updated_at": draft.updated_at.isoformat() if draft.updated_at else None,
    }
    if include_raw:
        response["extracted_raw"] = payload
    return response


@router.post("/scenarios/import", status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
async def import_scenario_material(
    request: Request,
    file: UploadFile = File(...),
    consent_152fz: bool = Form(False),
    forced_route_type: str | None = Form(None),
    user: User = Depends(_require_methodologist),
    db: AsyncSession = Depends(get_db),
):
    """Upload a training material and produce a ScenarioDraft.

    Body: ``multipart/form-data`` with ``file`` and ``consent_152fz``.

    Flow (TZ-5 §3.2):
      1. Validate consent box (152-FZ acceptance).
      2. Validate format (.pdf/.docx/.txt/.md/.pptx) + size (≤ 50 MB).
      3. ``ingest_training_material`` persists the Attachment row.
      4. ``mark_classified(document_type='training_material')`` flips
         ``classification_status`` from ``classification_pending`` to
         ``classified``. (No real classifier worker is invoked — the
         endpoint knows the document type by virtue of being the import
         endpoint.)
      5. ``run_extraction`` parses the bytes, scrubs PII, runs the LLM
         pipeline, persists the ScenarioDraft row, and transitions the
         attachment through ``scenario_draft_extracting → scenario_draft_ready``.

    Response: serialized draft (with confidence-gated payload).
    """
    from app.services.attachment_pipeline import (
        SOURCE_SCENARIO_IMPORT,
        ingest_training_material,
        mark_classified,
    )
    from app.services.attachment_storage import (
        MAX_TRAINING_MATERIAL_BYTES,
        TRAINING_MATERIAL_EXTENSIONS,
        UnsupportedAttachmentType,
    )
    from app.services.scenario_extractor import run_extraction

    if not consent_152fz:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "scenario_import_consent_required",
                "message": (
                    "Подтвердите согласие на обработку обучающего материала "
                    "(152-ФЗ): загружаемые данные не должны содержать "
                    "несогласованной персональной информации клиентов."
                ),
            },
        )

    # Read up to limit+1 so we can distinguish "exact limit" from "over".
    data = await file.read(MAX_TRAINING_MATERIAL_BYTES + 1)
    if not data:
        raise HTTPException(status_code=400, detail="Файл пустой")
    if len(data) > MAX_TRAINING_MATERIAL_BYTES:
        raise HTTPException(
            status_code=413,
            detail=(
                "Файл больше "
                f"{MAX_TRAINING_MATERIAL_BYTES // (1024 * 1024)} МБ — "
                "разделите материал на части."
            ),
        )

    try:
        attachment = await ingest_training_material(
            db,
            uploaded_by=user.id,
            raw_bytes=data,
            raw_filename=file.filename,
            content_type=file.content_type,
            source=SOURCE_SCENARIO_IMPORT,
            allowed_extensions=TRAINING_MATERIAL_EXTENSIONS,
        )
    except UnsupportedAttachmentType as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc

    # Manual classification flip — the import endpoint knows the type by
    # construction, so we don't wait for the async classifier worker.
    await mark_classified(
        db,
        attachment=attachment,
        document_type="training_material",
        actor_id=user.id,
        source=SOURCE_SCENARIO_IMPORT,
    )

    # PR-2: validate forced_route_type if caller pre-decided the branch
    # (e.g. user clicked "Импорт" from the ScenariosEditor and KNOWS this
    # is a scenario). When None, the classifier picks the route.
    from app.services.scenario_extractor import ROUTE_TYPES, run_extraction

    if forced_route_type is not None and forced_route_type not in ROUTE_TYPES:
        raise HTTPException(
            status_code=422,
            detail=(
                f"forced_route_type must be one of {ROUTE_TYPES}, "
                f"got {forced_route_type!r}"
            ),
        )

    draft = await run_extraction(
        db,
        attachment=attachment,
        raw_bytes=data,
        actor_id=user.id,
        forced_route_type=forced_route_type,
    )
    await db.commit()

    response = _draft_to_response(draft, attachment_filename=attachment.filename)
    response["message"] = (
        "Черновик создан"
        if draft.status == "ready" and float(draft.confidence) >= _LOW_CONFIDENCE_THRESHOLD
        else "Материал загружен; уверенность низкая — отредактируйте вручную."
    )
    return response


# ── PR-2: unified /imports alias ─────────────────────────────────────────
# Same handler under a route-neutral path so the FE can call POST
# /rop/imports from the ImportWizard regardless of which panel triggered
# it. The classifier decides the route unless forced_route_type is set.

@router.post("/imports", status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
async def unified_import(
    request: Request,
    file: UploadFile = File(...),
    consent_152fz: bool = Form(False),
    forced_route_type: str | None = Form(None),
    user: User = Depends(_require_methodologist),
    db: AsyncSession = Depends(get_db),
):
    """Unified import endpoint — alias of POST /rop/scenarios/import.

    The FE ImportWizard hits this path. Classifier picks scenario /
    character / arena_knowledge unless ``forced_route_type`` is set
    (e.g. user clicked "Импорт" from a specific panel and pre-committed
    to that branch).
    """
    return await import_scenario_material(
        request=request,
        file=file,
        consent_152fz=consent_152fz,
        forced_route_type=forced_route_type,
        user=user,
        db=db,
    )


@router.get("/scenarios/drafts")
async def list_scenario_drafts(
    status_filter: str | None = Query(None, alias="status"),
    route_type: str | None = Query(None),
    only_mine: bool = Query(False),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    user: User = Depends(_require_methodologist),
    db: AsyncSession = Depends(get_db),
):
    """List import drafts (most recent first).

    Filters:
      * ``status`` — extracting / ready / edited / converted / discarded / failed
      * ``route_type`` — scenario / character / arena_knowledge (PR-2)
      * ``only_mine=true`` — restrict to drafts the caller uploaded;
        admins see everyone by default.
    """
    from app.models.client import Attachment
    from app.models.scenario import ScenarioDraft

    stmt = select(ScenarioDraft, Attachment.filename).join(
        Attachment, ScenarioDraft.attachment_id == Attachment.id
    )
    if status_filter:
        stmt = stmt.where(ScenarioDraft.status == status_filter)
    if route_type:
        stmt = stmt.where(ScenarioDraft.route_type == route_type)
    if only_mine:
        stmt = stmt.where(ScenarioDraft.created_by == user.id)
    stmt = (
        stmt.order_by(desc(ScenarioDraft.created_at))
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = (await db.execute(stmt)).all()

    count_stmt = select(func.count(ScenarioDraft.id))
    if status_filter:
        count_stmt = count_stmt.where(ScenarioDraft.status == status_filter)
    if route_type:
        count_stmt = count_stmt.where(ScenarioDraft.route_type == route_type)
    if only_mine:
        count_stmt = count_stmt.where(ScenarioDraft.created_by == user.id)
    total = (await db.execute(count_stmt)).scalar() or 0

    return {
        "drafts": [
            _draft_to_response(draft, attachment_filename=filename)
            for draft, filename in rows
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/scenarios/drafts/{draft_id}")
async def get_scenario_draft(
    draft_id: uuid.UUID,
    include_raw: bool = Query(False),
    user: User = Depends(_require_methodologist),
    db: AsyncSession = Depends(get_db),
):
    from app.models.client import Attachment
    from app.models.scenario import ScenarioDraft

    row = (
        await db.execute(
            select(ScenarioDraft, Attachment.filename)
            .join(Attachment, ScenarioDraft.attachment_id == Attachment.id)
            .where(ScenarioDraft.id == draft_id)
        )
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Draft not found")
    draft, filename = row
    await _scope_check_draft(db, draft, user)
    if include_raw:
        # Audit-log access to the raw (potentially-PII) LLM output.
        logger.info(
            "scenario_draft.raw_accessed actor=%s draft=%s",
            user.id, draft.id,
        )
    return _draft_to_response(
        draft, attachment_filename=filename, include_raw=include_raw
    )


@router.put("/scenarios/drafts/{draft_id}")
@limiter.limit("30/minute")
async def update_scenario_draft(
    request: Request,
    draft_id: uuid.UUID,
    data: dict,
    user: User = Depends(_require_methodologist),
    db: AsyncSession = Depends(get_db),
):
    """ROP edits the structured draft in-place.

    Body: ``{"extracted": {...full ScenarioDraftPayload shape...}}``.
    Optional ``confidence`` override lets ROP raise a low-confidence draft
    after manual review.

    The status transitions from ``ready`` to ``edited`` on the first edit,
    so analytics can distinguish raw-LLM drafts from human-curated ones.
    Subsequent edits keep ``edited``. Drafts in ``converted``/``discarded``/
    ``failed`` cannot be edited (TZ-5 §3 invariant).
    """
    from app.models.scenario import ScenarioDraft

    result = await db.execute(
        select(ScenarioDraft).where(ScenarioDraft.id == draft_id)
    )
    draft = result.scalar_one_or_none()
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    await _scope_check_draft(db, draft, user)
    if draft.status not in ("ready", "edited"):
        raise HTTPException(
            status_code=409,
            detail={
                "code": "scenario_draft_immutable",
                "message": f"Черновик в статусе {draft.status!r} нельзя редактировать.",
            },
        )

    extracted = data.get("extracted")
    extracted_changed = False
    if extracted is not None:
        if not isinstance(extracted, dict):
            raise HTTPException(status_code=422, detail="`extracted` must be an object")
        # Audit fix (BLOCKER bypass): the gate checked
        # `extracted is not None`, which let a no-op PUT (`extracted={}` or
        # a verbatim copy of `draft.extracted`) flip the gate open and
        # allow confidence ≥ 0.6 without curation. Now require
        # MEANINGFULLY DIFFERENT content. Cheap deep-equal via JSON
        # serialisation (both blobs are JSONB-shaped).
        import json as _json

        old_blob = _json.dumps(draft.extracted or {}, sort_keys=True)
        new_blob = _json.dumps(extracted, sort_keys=True)
        extracted_changed = old_blob != new_blob
        draft.extracted = extracted

    if "confidence" in data:
        try:
            new_conf = float(data["confidence"])
        except (TypeError, ValueError):
            raise HTTPException(status_code=422, detail="`confidence` must be a number")
        if not (0.0 <= new_conf <= 1.0):
            raise HTTPException(status_code=422, detail="`confidence` out of [0,1]")

        # PR-1.1 audit fix — refuse to raise confidence above the §4 threshold
        # without an accompanying `extracted` edit. Otherwise a ROP could
        # flip a hallucinated draft to "high confidence" via a single PUT
        # without curating it. Lowering or keeping below threshold is fine.
        previous_conf = float(draft.confidence or 0.0)
        if (
            new_conf >= _LOW_CONFIDENCE_THRESHOLD
            and previous_conf < _LOW_CONFIDENCE_THRESHOLD
            and not extracted_changed
        ):
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "scenario_draft_confidence_override_requires_review",
                    "message": (
                        "Чтобы поднять уверенность выше "
                        f"{_LOW_CONFIDENCE_THRESHOLD:.0%}, отредактируйте "
                        "содержание черновика в этом же запросе."
                    ),
                    "previous": previous_conf,
                    "requested": new_conf,
                },
            )

        # Audit-log every confidence override regardless of direction so
        # the publish path has a traceable record of "who raised confidence
        # on this imported draft" (TZ-5 §4 compliance).
        if new_conf != previous_conf:
            logger.info(
                "scenario_draft.confidence_overridden actor=%s draft=%s old=%.2f new=%.2f",
                user.id, draft.id, previous_conf, new_conf,
            )
        draft.confidence = new_conf

    if draft.status == "ready":
        draft.status = "edited"

    await db.commit()
    return _draft_to_response(draft)


@router.post("/scenarios/drafts/{draft_id}/create-scenario", status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
async def create_scenario_from_draft(
    request: Request,
    draft_id: uuid.UUID,
    user: User = Depends(_require_methodologist),
    db: AsyncSession = Depends(get_db),
):
    """Convert a ``ScenarioDraft`` into a ``ScenarioTemplate`` + v1.

    The created template lands with ``status='draft'`` per TZ-5 §3.2 step 4
    so the runtime never sees a half-baked imported template until the
    ROP explicitly publishes it through the existing TZ-3 flow
    (``POST /rop/scenarios/{id}/publish``).

    The draft row is marked ``converted`` and gets ``scenario_template_id``
    pointing at the new template (1-to-1 link, enforced by the UNIQUE
    constraint at the column level).
    """
    from app.models.scenario import ScenarioDraft, ScenarioTemplate
    from app.services.scenario_extractor import (
        ScenarioDraftPayload,
        ScenarioStep,
        draft_payload_to_template_fields,
    )

    result = await db.execute(
        select(ScenarioDraft).where(ScenarioDraft.id == draft_id).with_for_update()
    )
    draft = result.scalar_one_or_none()
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    await _scope_check_draft(db, draft, user)
    if draft.status not in ("ready", "edited"):
        raise HTTPException(
            status_code=409,
            detail={
                "code": "scenario_draft_not_convertible",
                "message": (
                    f"Черновик в статусе {draft.status!r} нельзя конвертировать. "
                    "Допустимые статусы: ready, edited."
                ),
            },
        )

    raw = draft.extracted or {}
    try:
        payload = ScenarioDraftPayload(
            title_suggested=raw.get("title_suggested", "Импортированный сценарий"),
            summary=raw.get("summary", ""),
            archetype_hint=raw.get("archetype_hint"),
            steps=[
                ScenarioStep(**s) if isinstance(s, dict) else s
                for s in raw.get("steps", [])
            ],
            expected_objections=list(raw.get("expected_objections", [])),
            success_criteria=list(raw.get("success_criteria", [])),
            quotes_from_source=list(raw.get("quotes_from_source", [])),
            confidence=float(raw.get("confidence", draft.confidence or 0.0)),
        )
    except Exception as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "scenario_draft_payload_invalid",
                "message": f"Структура черновика повреждена: {exc}",
            },
        )

    fallback_code = f"imported_{str(draft.id)[:8]}"
    fields = draft_payload_to_template_fields(payload, fallback_code=fallback_code)

    template = ScenarioTemplate(**fields)
    db.add(template)
    await db.flush()
    # TZ-5 §3.2 step 4 — imported templates start in 'draft', NOT
    # auto-published. The runtime resolver (PR C3) follows
    # ``current_published_version_id``, so leaving it NULL keeps the
    # template invisible to live training sessions until the ROP
    # explicitly publishes via the existing TZ-3 publish flow.
    version = await _create_scenario_version(db, template, user, status_value="draft")
    template.current_published_version_id = None

    draft.status = "converted"
    draft.scenario_template_id = template.id

    await db.commit()
    return {
        "draft_id": str(draft.id),
        "template_id": str(template.id),
        "version_id": str(version.id),
        "message": "Сценарий создан как черновик. Опубликуйте через TZ-3 publish flow.",
    }


@router.get("/scenarios/drafts/{draft_id}/download")
@limiter.limit("30/minute")
async def download_training_material(
    request: Request,
    draft_id: uuid.UUID,
    user: User = Depends(_require_methodologist),
    db: AsyncSession = Depends(get_db),
):
    """Auth-gated download of the underlying training-material file.

    PR-1.1 audit fix — replaces direct `/api/uploads/attachments/
    _training_materials/{sha[:16]}_{filename}` access. The StaticFiles
    mount now refuses that prefix; callers must come through this
    endpoint. Authorization: caller must be the original uploader OR
    have admin role (admins always allowed for audit/cross-ROP review).
    """
    from fastapi.responses import FileResponse

    from app.models.client import Attachment
    from app.models.scenario import ScenarioDraft

    row = (
        await db.execute(
            select(ScenarioDraft, Attachment)
            .join(Attachment, ScenarioDraft.attachment_id == Attachment.id)
            .where(ScenarioDraft.id == draft_id)
        )
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Draft not found")
    draft, attachment = row

    is_admin = getattr(user.role, "value", str(user.role)) == "admin"
    if not is_admin and attachment.uploaded_by != user.id:
        raise HTTPException(
            status_code=403,
            detail="Доступ только владельцу материала или администратору",
        )

    if not attachment.storage_path:
        raise HTTPException(status_code=410, detail="Файл больше недоступен")

    return FileResponse(
        path=attachment.storage_path,
        filename=attachment.filename,
        media_type=attachment.content_type or "application/octet-stream",
    )


@router.post("/scenarios/drafts/{draft_id}/discard")
@limiter.limit("10/minute")
async def discard_scenario_draft(
    request: Request,
    draft_id: uuid.UUID,
    user: User = Depends(_require_methodologist),
    db: AsyncSession = Depends(get_db),
):
    from app.models.scenario import ScenarioDraft

    result = await db.execute(
        select(ScenarioDraft).where(ScenarioDraft.id == draft_id)
    )
    draft = result.scalar_one_or_none()
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    await _scope_check_draft(db, draft, user)
    if draft.status == "converted":
        raise HTTPException(
            status_code=409,
            detail="Сконвертированный черновик нельзя отменить — удалите шаблон через TZ-3.",
        )
    draft.status = "discarded"
    await db.commit()
    return {"id": str(draft.id), "status": "discarded"}


# ── PR-2: unified /imports list alias + approve endpoints ───────────────


@router.get("/imports")
async def list_imports(
    status_filter: str | None = Query(None, alias="status"),
    route_type: str | None = Query(None),
    only_mine: bool = Query(False),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    user: User = Depends(_require_methodologist),
    db: AsyncSession = Depends(get_db),
):
    """Unified import-history endpoint — alias of GET /scenarios/drafts.

    The FE's ImportHistory component calls this from any panel. Filter
    by route_type to scope the list to the current panel's branch.
    """
    return await list_scenario_drafts(
        status_filter=status_filter,
        route_type=route_type,
        only_mine=only_mine,
        page=page,
        page_size=page_size,
        user=user,
        db=db,
    )


@router.post("/imports/{draft_id}/approve-character", status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
async def approve_character_draft(
    request: Request,
    draft_id: uuid.UUID,
    user: User = Depends(_require_methodologist),
    db: AsyncSession = Depends(get_db),
):
    """PR-2: convert a CHARACTER-route draft into a row in
    ``custom_characters``.

    The created row is owned by the approving user (current ROP) and
    starts with ``is_shared=False`` so it shows up in their personal
    Constructor list. ROP can then publish-share it from the existing
    Constructor UI if they want the team to see it.
    """
    from app.models.custom_character import CustomCharacter
    from app.models.scenario import ScenarioDraft

    result = await db.execute(
        select(ScenarioDraft).where(ScenarioDraft.id == draft_id).with_for_update()
    )
    draft = result.scalar_one_or_none()
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    await _scope_check_draft(db, draft, user)
    if draft.route_type != "character":
        raise HTTPException(
            status_code=409,
            detail=f"Draft route_type={draft.route_type!r} is not 'character'.",
        )
    if draft.status not in ("ready", "edited"):
        raise HTTPException(
            status_code=409,
            detail=f"Draft status={draft.status!r} is not convertible.",
        )

    raw = draft.extracted or {}
    character = CustomCharacter(
        user_id=user.id,
        name=str(raw.get("name") or "Импортированный персонаж")[:100],
        # Sensible defaults — ROP edits in Constructor before sharing.
        archetype=str(raw.get("archetype_hint") or "neutral")[:50],
        profession="other",
        lead_source="imported",
        difficulty=5,
        description=str(raw.get("description") or "")[:2000] or None,
        is_shared=False,
    )
    db.add(character)
    await db.flush()

    draft.status = "converted"
    draft.target_id = character.id
    await db.commit()
    return {
        "draft_id": str(draft.id),
        "character_id": str(character.id),
        "message": "Персонаж создан в Конструкторе. Отредактируйте перед публикацией.",
    }


@router.post("/imports/{draft_id}/approve-arena-knowledge", status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
async def approve_arena_knowledge_draft(
    request: Request,
    draft_id: uuid.UUID,
    user: User = Depends(_require_methodologist),
    db: AsyncSession = Depends(get_db),
):
    """Convert an ARENA_KNOWLEDGE-route draft into a ``LegalKnowledgeChunk``.

    Content→Arena PR-3 (2026-05-01): high-confidence drafts auto-publish
    (``is_active=True``) so the AI judge sees ROP-uploaded facts in the
    next dueled round, not whenever the review queue is processed
    manually. The threshold is governed by
    ``settings.arena_knowledge_auto_publish_confidence`` (default 0.85).

    We deliberately gate on ``draft.original_confidence`` — the LLM's
    immutable assessment from the extractor — NOT on the editable
    ``draft.confidence``. This protects against the post-hoc-bump
    attack documented in migration 20260429_002 (audit-fix C7): a
    methodologist who raises a hallucinated draft's confidence to 0.99
    can still NOT trick the system into auto-publishing — the auto path
    only trusts the extractor's original number.

    On miss (``original_confidence`` < threshold or NULL) the chunk is
    created with ``is_active=False`` and the existing review queue takes
    over — bit-for-bit identical to pre-PR-3 behaviour.
    """
    from app.config import settings as _app_settings
    from app.models.rag import LegalKnowledgeChunk
    from app.models.scenario import ScenarioDraft

    result = await db.execute(
        select(ScenarioDraft).where(ScenarioDraft.id == draft_id).with_for_update()
    )
    draft = result.scalar_one_or_none()
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    await _scope_check_draft(db, draft, user)
    if draft.route_type != "arena_knowledge":
        raise HTTPException(
            status_code=409,
            detail=f"Draft route_type={draft.route_type!r} is not 'arena_knowledge'.",
        )
    if draft.status not in ("ready", "edited"):
        raise HTTPException(
            status_code=409,
            detail=f"Draft status={draft.status!r} is not convertible.",
        )

    # Auto-publish gate: trust ONLY the immutable original_confidence.
    # NULL original_confidence (legacy PR-1 rows or missing field) is
    # treated as "below threshold" — no auto-publish, falls into the
    # review queue. This is the safe default: an unknown confidence
    # never gets the fast-track.
    threshold = float(_app_settings.arena_knowledge_auto_publish_confidence)
    original_conf = draft.original_confidence
    auto_publish = (
        original_conf is not None and float(original_conf) >= threshold
    )
    chunk_tags = ["imported"]
    if auto_publish:
        chunk_tags.append("auto_published")

    raw = draft.extracted or {}
    chunk = LegalKnowledgeChunk(
        category=str(raw.get("category") or "general")[:50],
        fact_text=str(raw.get("fact_text") or "")[:2000],
        law_article=str(raw.get("law_article") or "")[:200] or None,
        difficulty_level=int(raw.get("difficulty_level") or 2),
        match_keywords=list(raw.get("match_keywords") or []),
        common_errors=list(raw.get("common_errors") or []),
        correct_response_hint=str(raw.get("correct_response_hint") or "")[:1000],
        tags=chunk_tags,
        is_active=auto_publish,
    )
    db.add(chunk)
    await db.flush()

    draft.status = "converted"
    draft.target_id = chunk.id
    await db.commit()

    # Content→Arena PR-6: schedule live embedding backfill so the new
    # chunk gets its pgvector ``embedding`` populated within seconds —
    # otherwise auto-published chunks (PR-3) sit with ``embedding=NULL``
    # until the next API restart, defeating the auto-publish promise.
    # Best-effort: enqueue failure (Redis down) is logged + swallowed,
    # the cold sweep on next restart picks up the gap.
    try:
        from app.services.embedding_live_backfill import enqueue_chunk
        await enqueue_chunk(chunk.id)
    except Exception:
        # enqueue_chunk is itself best-effort; double-belt for safety.
        pass

    return {
        "draft_id": str(draft.id),
        "chunk_id": str(chunk.id),
        "auto_published": auto_publish,
        "original_confidence": float(original_conf) if original_conf is not None else None,
        "message": (
            "Факт автоопубликован — попадёт в Арену в ближайших дуэлях."
            if auto_publish
            else "Факт добавлен в очередь review для Арены."
        ),
    }


# ── PR #101 (TZ-5 wizard improvements) ──────────────────────────────────


@router.post("/imports/{draft_id}/re-extract")
@limiter.limit("5/minute")
async def re_extract_draft(
    request: Request,
    draft_id: uuid.UUID,
    body: dict | None = None,
    user: User = Depends(_require_methodologist),
    db: AsyncSession = Depends(get_db),
):
    """Re-run the extractor on the same uploaded bytes.

    Use case: first extract gave low confidence or wrong route — ROP wants
    to retry (e.g. force a different ``route_type``) without re-uploading
    the file. Reads the original bytes from the attachment's
    ``storage_path`` and re-runs ``extract_text_from_bytes`` +
    ``extract_for_route``.

    Body (optional): ``{"forced_route_type": "scenario|character|arena_knowledge"}``.
    Without forced_route_type the classifier picks again — useful if the
    extractor ships an LLM upgrade between the first try and now.

    Lifecycle: only `ready`, `edited`, `failed` drafts can be re-extracted
    (NOT `converted` or `discarded` — those are terminal). The draft's
    `extracted` JSONB and `confidence` are overwritten; status flips back
    to `ready`. `original_confidence` is REPLACED so the audit invariant
    reflects the latest LLM run, not the first one.
    """
    from pathlib import Path

    from app.models.client import Attachment
    from app.models.scenario import ScenarioDraft
    from app.services.scenario_extractor import (
        ROUTE_TYPES,
        extract_text_from_bytes,
    )
    from app.services.scenario_extractor_llm import (
        llm_classify_material,
        llm_extract_for_route,
    )

    payload = body or {}
    forced = payload.get("forced_route_type")
    if forced is not None and forced not in ROUTE_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"forced_route_type must be one of {ROUTE_TYPES}",
        )

    row = (
        await db.execute(
            select(ScenarioDraft, Attachment)
            .join(Attachment, ScenarioDraft.attachment_id == Attachment.id)
            .where(ScenarioDraft.id == draft_id)
        )
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Draft not found")
    draft, attachment = row
    await _scope_check_draft(db, draft, user)

    # Audit fix (#8 follow-up): allow re-extract from `scenario_draft_extracting`
    # too — see scenario_extractor.run_extraction now lands in `failed` on
    # any unexpected exception, but legacy stuck rows from before the fix
    # need a recovery path. `failed` was already allowed.
    if draft.status not in ("ready", "edited", "failed"):
        raise HTTPException(
            status_code=409,
            detail=(
                f"Re-extract запрещён для статуса {draft.status!r}. "
                "Допустимы: ready, edited, failed."
            ),
        )

    storage_path = Path(attachment.storage_path) if attachment.storage_path else None
    if not storage_path or not storage_path.exists():
        raise HTTPException(
            status_code=410,
            detail="Файл больше недоступен на диске — повторно загрузите через wizard.",
        )

    try:
        raw_bytes = storage_path.read_bytes()
    except OSError as exc:
        # Log full OSError (including filesystem path) server-side; return
        # a generic message to the client. Earlier we leaked the storage
        # path + raw OSError text via the response detail, which exposes
        # internal layout to anyone who can hit this admin endpoint.
        logger.error(
            "Failed to read attachment from storage",
            extra={"attachment_id": str(attachment.id), "error": str(exc)},
            exc_info=True,
        )
        raise HTTPException(
            status_code=500,
            detail="Не удалось прочитать файл. Попробуйте позже или загрузите заново.",
        ) from exc

    try:
        source_text = extract_text_from_bytes(attachment.filename, raw_bytes)
    except Exception as exc:
        # Generic exception class + raw text could include parser internals
        # (PyPDF2 stack traces, MS Office binary chunks). Log server-side,
        # return a safe-to-show message. Filename is fine to surface — the
        # admin who uploaded already knows it.
        logger.error(
            "Attachment text extraction failed",
            extra={
                "attachment_id": str(attachment.id),
                "filename": attachment.filename,
                "error_class": type(exc).__name__,
                "error": str(exc),
            },
            exc_info=True,
        )
        raise HTTPException(
            status_code=422,
            detail=f"Не удалось распарсить файл «{attachment.filename}». Проверьте формат и повторите.",
        ) from exc

    chosen_route = forced
    if not chosen_route:
        chosen_route = (await llm_classify_material(source_text)).route_type

    extracted = await llm_extract_for_route(source_text, chosen_route)
    new_confidence = float(extracted.get("confidence", 0.0))

    draft.route_type = chosen_route
    draft.extracted = extracted
    draft.confidence = new_confidence
    draft.original_confidence = new_confidence
    draft.status = "ready"
    draft.error_message = None

    logger.info(
        "scenario_draft.re_extracted actor=%s draft=%s route=%s confidence=%.2f forced=%s",
        user.id, draft.id, chosen_route, new_confidence, bool(forced),
    )
    await db.commit()
    return _draft_to_response(draft, attachment_filename=attachment.filename)
