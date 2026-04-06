"""REST API for Methodologist tools.

Access: role == methodologist | admin only.

Endpoints:
  GET    /methodologist/sessions                  -- browse all training sessions
  GET    /methodologist/sessions/{id}/details     -- full session details
  GET    /methodologist/scenarios                  -- list scenario templates
  POST   /methodologist/scenarios                  -- create scenario
  PUT    /methodologist/scenarios/{id}             -- update scenario
  GET    /methodologist/scoring-config             -- get scoring weights
  PUT    /methodologist/scoring-config             -- update scoring weights
  GET    /methodologist/arena/chunks               -- list legal knowledge chunks
  POST   /methodologist/arena/chunks               -- create chunk
  PUT    /methodologist/arena/chunks/{id}          -- update chunk
  DELETE /methodologist/arena/chunks/{id}          -- delete chunk
"""

import logging
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, require_role
from app.database import get_db
from app.models.user import User

logger = logging.getLogger(__name__)

limiter = Limiter(key_func=get_remote_address)
router = APIRouter()

# All endpoints require methodologist or admin role
_require_methodologist = require_role("methodologist", "admin")


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
                "title": s.title,
                "description": getattr(s, "description", None),
                "scenario_code": s.scenario_code.value if hasattr(s.scenario_code, 'value') else str(s.scenario_code),
                "archetype": s.archetype_code.value if hasattr(s.archetype_code, 'value') else str(s.archetype_code),
                "difficulty": s.difficulty,
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

    scenario = ScenarioTemplate(
        title=data.get("title", "New Scenario"),
        description=data.get("description", ""),
        scenario_code=data.get("scenario_type", "in_website"),
        archetype_code=data.get("archetype", "skeptic"),
        difficulty=data.get("difficulty", 5),
        client_brief=data.get("client_brief"),
        emotional_profile=data.get("emotional_profile", {}),
        traps=data.get("traps", []),
        success_criteria=data.get("success_criteria", {}),
    )
    db.add(scenario)
    await db.flush()
    await db.commit()

    return {"id": str(scenario.id), "message": "Scenario created"}


@router.put("/scenarios/{scenario_id}")
@limiter.limit("10/minute")
async def update_scenario(
    request: Request,
    scenario_id: uuid.UUID,
    data: dict,
    user: User = Depends(_require_methodologist),
    db: AsyncSession = Depends(get_db),
):
    """Update an existing scenario template."""
    from app.models.scenario import ScenarioTemplate

    result = await db.execute(
        select(ScenarioTemplate).where(ScenarioTemplate.id == scenario_id)
    )
    scenario = result.scalar_one_or_none()
    if not scenario:
        raise HTTPException(status_code=404, detail="Scenario not found")

    for field in ["title", "description", "difficulty", "client_brief",
                  "emotional_profile", "traps", "success_criteria", "is_active"]:
        if field in data:
            setattr(scenario, field, data[field])

    await db.commit()
    return {"id": str(scenario.id), "message": "Scenario updated"}


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
        "updated_at": datetime.utcnow().isoformat(),
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
    """List legal knowledge chunks with filters."""
    from app.models.rag import LegalKnowledgeChunk

    base = select(LegalKnowledgeChunk)

    if category:
        base = base.where(LegalKnowledgeChunk.category == category)
    if difficulty:
        base = base.where(LegalKnowledgeChunk.difficulty_level == difficulty)
    if search:
        base = base.where(LegalKnowledgeChunk.content.ilike(f"%{search}%"))

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
                "title": c.title,
                "content": c.content[:200] + "..." if len(c.content) > 200 else c.content,
                "category": c.category.value if hasattr(c.category, 'value') else str(c.category),
                "article_reference": c.article_reference,
                "difficulty_level": getattr(c, "difficulty_level", 3),
                "is_court_practice": getattr(c, "is_court_practice", False),
                "court_case_reference": getattr(c, "court_case_reference", None),
                "question_templates": getattr(c, "question_templates", []) or [],
                "tags": getattr(c, "tags", []) or [],
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
    """Create a new legal knowledge chunk."""
    from app.models.rag import LegalKnowledgeChunk

    chunk = LegalKnowledgeChunk(
        title=data["title"],
        content=data["content"],
        category=data["category"],
        article_reference=data.get("article_reference"),
        difficulty_level=data.get("difficulty_level", 3),
        is_court_practice=data.get("is_court_practice", False),
        court_case_reference=data.get("court_case_reference"),
        question_templates=data.get("question_templates", []),
        tags=data.get("tags", []),
    )
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
    """Update a legal knowledge chunk."""
    from app.models.rag import LegalKnowledgeChunk

    result = await db.execute(
        select(LegalKnowledgeChunk).where(LegalKnowledgeChunk.id == chunk_id)
    )
    chunk = result.scalar_one_or_none()
    if not chunk:
        raise HTTPException(status_code=404, detail="Chunk not found")

    for field in ["title", "content", "category", "article_reference",
                  "difficulty_level", "is_court_practice", "court_case_reference",
                  "question_templates", "tags"]:
        if field in data:
            setattr(chunk, field, data[field])

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
