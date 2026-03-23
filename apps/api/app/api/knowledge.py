"""REST API for Knowledge Quiz (127-FZ testing).

Endpoints:
  GET  /knowledge/categories        -- list categories with user progress
  POST /knowledge/sessions          -- create quiz session (returned before WS)
  GET  /knowledge/sessions/{id}     -- get session results
  GET  /knowledge/history           -- paginated history of quiz sessions
  GET  /knowledge/progress          -- overall progress by category
  GET  /knowledge/weak-areas        -- weak categories based on error history
  GET  /knowledge/leaderboard       -- PvP leaderboard
  POST /knowledge/challenges        -- create PvP challenge (alternative to WS)
  GET  /knowledge/challenges/active -- list active challenges
"""

import logging
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import case, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.database import get_db
from app.models.knowledge import (
    KnowledgeAnswer,
    KnowledgeQuizSession,
    QuizChallenge,
    QuizMode,
    QuizParticipant,
    QuizSessionStatus,
)
from app.models.rag import LegalCategory
from app.models.user import User
from app.schemas.knowledge import (
    ActiveChallengesResponse,
    AnswerResponse,
    CategoriesResponse,
    CategoryProgress,
    CategoryProgressDetail,
    ChallengeCreateRequest,
    ChallengeResponse,
    HistoryEntry,
    HistoryResponse,
    KnowledgeLeaderboardResponse,
    LeaderboardEntry,
    OverallProgressResponse,
    ParticipantResponse,
    SessionCreateRequest,
    SessionDetailResponse,
    SessionResponse,
    WeakArea,
    WeakAreasResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# Display names for legal categories
CATEGORY_DISPLAY_NAMES: dict[str, str] = {
    "eligibility": "Условия подачи",
    "procedure": "Порядок процедуры",
    "property": "Имущество",
    "consequences": "Последствия",
    "costs": "Стоимость",
    "creditors": "Кредиторы",
    "documents": "Документы",
    "timeline": "Сроки",
    "court": "Судебные процессы",
    "rights": "Права должника",
}


def _display_name(category: str) -> str:
    return CATEGORY_DISPLAY_NAMES.get(category, category.replace("_", " ").title())


# ---------------------------------------------------------------------------
# GET /categories — list categories with user progress
# ---------------------------------------------------------------------------

@router.get("/categories", response_model=CategoriesResponse)
async def list_categories(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all quiz categories with the current user's progress in each."""
    # Aggregate answers by category for this user
    stmt = (
        select(
            KnowledgeAnswer.question_category,
            func.count(KnowledgeAnswer.id).label("total"),
            func.sum(case((KnowledgeAnswer.is_correct == True, 1), else_=0)).label("correct"),  # noqa: E712
            func.count(func.distinct(KnowledgeAnswer.session_id)).label("sessions"),
            func.max(KnowledgeAnswer.created_at).label("last_attempt"),
        )
        .where(KnowledgeAnswer.user_id == user.id)
        .group_by(KnowledgeAnswer.question_category)
    )
    result = await db.execute(stmt)
    rows = result.all()
    progress_map = {
        row.question_category: row for row in rows
    }

    # Best score per category from sessions
    best_stmt = (
        select(
            KnowledgeQuizSession.category,
            func.max(KnowledgeQuizSession.score).label("best_score"),
        )
        .where(
            KnowledgeQuizSession.user_id == user.id,
            KnowledgeQuizSession.status == QuizSessionStatus.completed,
            KnowledgeQuizSession.category.isnot(None),
        )
        .group_by(KnowledgeQuizSession.category)
    )
    best_result = await db.execute(best_stmt)
    best_map = {row.category: row.best_score or 0.0 for row in best_result.all()}

    categories = []
    for cat in LegalCategory:
        row = progress_map.get(cat.value)
        total = row.total if row else 0
        correct = row.correct if row else 0
        categories.append(CategoryProgress(
            category=cat.value,
            display_name=_display_name(cat.value),
            total_questions_answered=total,
            correct_answers=correct,
            accuracy_percent=round((correct / total * 100) if total > 0 else 0.0, 1),
            sessions_count=row.sessions if row else 0,
            best_score=best_map.get(cat.value, 0.0),
            last_attempt_at=row.last_attempt if row else None,
        ))

    return CategoriesResponse(categories=categories)


# ---------------------------------------------------------------------------
# POST /sessions — create quiz session
# ---------------------------------------------------------------------------

@router.post("/sessions", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
async def create_session(
    body: SessionCreateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new quiz session. Returns session ID to use with WebSocket."""
    # Validate mode
    try:
        mode = QuizMode(body.mode)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid mode '{body.mode}'. Must be one of: {[m.value for m in QuizMode]}",
        )

    # Themed mode requires category
    if mode == QuizMode.themed and not body.category:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Category is required for themed mode.",
        )

    # Validate category if provided
    if body.category:
        valid_categories = [c.value for c in LegalCategory]
        if body.category not in valid_categories:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid category '{body.category}'. Must be one of: {valid_categories}",
            )

    # PvP mode requires max_players > 1
    if mode == QuizMode.pvp and body.max_players < 2:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="PvP mode requires max_players >= 2.",
        )

    session = KnowledgeQuizSession(
        user_id=user.id,
        mode=mode,
        category=body.category,
        difficulty=body.difficulty,
        max_players=body.max_players,
        ai_personality=body.ai_personality,
        status=QuizSessionStatus.waiting if mode == QuizMode.pvp else QuizSessionStatus.active,
    )
    db.add(session)

    # Add creator as first participant
    participant = QuizParticipant(
        session_id=session.id,
        user_id=user.id,
    )
    db.add(participant)

    await db.commit()
    await db.refresh(session)

    return SessionResponse(
        id=session.id,
        user_id=session.user_id,
        mode=session.mode.value,
        category=session.category,
        difficulty=session.difficulty,
        total_questions=session.total_questions,
        correct_answers=session.correct_answers,
        incorrect_answers=session.incorrect_answers,
        skipped=session.skipped,
        score=session.score,
        max_players=session.max_players,
        status=session.status.value,
        started_at=session.started_at,
        ended_at=session.ended_at,
        duration_seconds=session.duration_seconds,
        ai_personality=session.ai_personality,
        created_at=session.created_at,
    )


# ---------------------------------------------------------------------------
# GET /sessions/{session_id} — get session results
# ---------------------------------------------------------------------------

@router.get("/sessions/{session_id}", response_model=SessionDetailResponse)
async def get_session(
    session_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get detailed results for a quiz session (answers + participants)."""
    stmt = select(KnowledgeQuizSession).where(KnowledgeQuizSession.id == session_id)
    result = await db.execute(stmt)
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found.")

    # Only allow session owner or participants to view
    participant_ids = [p.user_id for p in session.participants]
    if session.user_id != user.id and user.id not in participant_ids:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied.")

    answers = [
        AnswerResponse(
            id=a.id,
            question_number=a.question_number,
            question_text=a.question_text,
            question_category=a.question_category,
            user_answer=a.user_answer,
            is_correct=a.is_correct,
            explanation=a.explanation,
            article_reference=a.article_reference,
            score_delta=a.score_delta,
            hint_used=a.hint_used,
            response_time_ms=a.response_time_ms,
            created_at=a.created_at,
        )
        for a in session.answers
    ]

    participants = [
        ParticipantResponse(
            id=p.id,
            user_id=p.user_id,
            score=p.score,
            correct_answers=p.correct_answers,
            incorrect_answers=p.incorrect_answers,
            final_rank=p.final_rank,
            joined_at=p.joined_at,
        )
        for p in session.participants
    ]

    return SessionDetailResponse(
        id=session.id,
        user_id=session.user_id,
        mode=session.mode.value,
        category=session.category,
        difficulty=session.difficulty,
        total_questions=session.total_questions,
        correct_answers=session.correct_answers,
        incorrect_answers=session.incorrect_answers,
        skipped=session.skipped,
        score=session.score,
        max_players=session.max_players,
        status=session.status.value,
        started_at=session.started_at,
        ended_at=session.ended_at,
        duration_seconds=session.duration_seconds,
        ai_personality=session.ai_personality,
        created_at=session.created_at,
        answers=answers,
        participants=participants,
    )


# ---------------------------------------------------------------------------
# GET /history — paginated history
# ---------------------------------------------------------------------------

@router.get("/history", response_model=HistoryResponse)
async def get_history(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    mode: str | None = Query(None, description="Filter by mode"),
    category: str | None = Query(None, description="Filter by category"),
):
    """Get paginated history of the user's quiz sessions."""
    base = select(KnowledgeQuizSession).where(KnowledgeQuizSession.user_id == user.id)

    if mode:
        try:
            base = base.where(KnowledgeQuizSession.mode == QuizMode(mode))
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid mode '{mode}'.",
            )

    if category:
        base = base.where(KnowledgeQuizSession.category == category)

    # Total count
    count_stmt = select(func.count()).select_from(base.subquery())
    total = (await db.execute(count_stmt)).scalar() or 0

    # Paginated results
    offset = (page - 1) * page_size
    data_stmt = base.order_by(desc(KnowledgeQuizSession.started_at)).offset(offset).limit(page_size)
    result = await db.execute(data_stmt)
    sessions = result.scalars().all()

    items = [
        HistoryEntry(
            id=s.id,
            mode=s.mode.value,
            category=s.category,
            status=s.status.value,
            score=s.score,
            total_questions=s.total_questions,
            correct_answers=s.correct_answers,
            duration_seconds=s.duration_seconds,
            started_at=s.started_at,
            ended_at=s.ended_at,
        )
        for s in sessions
    ]

    return HistoryResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        has_next=(offset + page_size) < total,
    )


# ---------------------------------------------------------------------------
# GET /progress — overall progress by category
# ---------------------------------------------------------------------------

@router.get("/progress", response_model=OverallProgressResponse)
async def get_progress(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get overall knowledge progress broken down by category."""
    # Overall stats from sessions
    session_stats_stmt = (
        select(
            func.count(KnowledgeQuizSession.id).label("total_sessions"),
            func.sum(KnowledgeQuizSession.total_questions).label("total_q"),
            func.sum(KnowledgeQuizSession.correct_answers).label("total_correct"),
            func.avg(KnowledgeQuizSession.score).label("avg_score"),
        )
        .where(
            KnowledgeQuizSession.user_id == user.id,
            KnowledgeQuizSession.status == QuizSessionStatus.completed,
        )
    )
    overall = (await db.execute(session_stats_stmt)).one()

    total_sessions = overall.total_sessions or 0
    total_q = overall.total_q or 0
    total_correct = overall.total_correct or 0
    avg_score = float(overall.avg_score or 0.0)

    # Per-category stats from answers
    cat_stmt = (
        select(
            KnowledgeAnswer.question_category,
            func.count(KnowledgeAnswer.id).label("total"),
            func.sum(case((KnowledgeAnswer.is_correct == True, 1), else_=0)).label("correct"),  # noqa: E712
            func.count(func.distinct(KnowledgeAnswer.session_id)).label("sessions"),
        )
        .where(KnowledgeAnswer.user_id == user.id)
        .group_by(KnowledgeAnswer.question_category)
    )
    cat_result = await db.execute(cat_stmt)
    cat_rows = {row.question_category: row for row in cat_result.all()}

    # Best and avg score per category from sessions
    cat_score_stmt = (
        select(
            KnowledgeQuizSession.category,
            func.avg(KnowledgeQuizSession.score).label("avg_score"),
            func.max(KnowledgeQuizSession.score).label("best_score"),
        )
        .where(
            KnowledgeQuizSession.user_id == user.id,
            KnowledgeQuizSession.status == QuizSessionStatus.completed,
            KnowledgeQuizSession.category.isnot(None),
        )
        .group_by(KnowledgeQuizSession.category)
    )
    cat_scores = {
        row.category: (float(row.avg_score or 0), float(row.best_score or 0))
        for row in (await db.execute(cat_score_stmt)).all()
    }

    # Recent trend: compare last 5 sessions avg vs previous 5
    trend_stmt = (
        select(KnowledgeQuizSession.category, KnowledgeQuizSession.score)
        .where(
            KnowledgeQuizSession.user_id == user.id,
            KnowledgeQuizSession.status == QuizSessionStatus.completed,
            KnowledgeQuizSession.category.isnot(None),
        )
        .order_by(desc(KnowledgeQuizSession.started_at))
        .limit(50)  # enough for trend calc
    )
    trend_rows = (await db.execute(trend_stmt)).all()
    trend_by_cat: dict[str, list[float]] = {}
    for row in trend_rows:
        trend_by_cat.setdefault(row.category, []).append(float(row.score))

    def _calc_trend(scores: list[float]) -> str:
        if len(scores) < 4:
            return "stable"
        recent = sum(scores[:3]) / 3
        older = sum(scores[3:6]) / min(len(scores[3:6]), 3)
        if recent > older + 5:
            return "improving"
        elif recent < older - 5:
            return "declining"
        return "stable"

    categories = []
    for cat in LegalCategory:
        crow = cat_rows.get(cat.value)
        cat_total = crow.total if crow else 0
        cat_correct = crow.correct if crow else 0
        cat_sessions = crow.sessions if crow else 0
        scores = cat_scores.get(cat.value, (0.0, 0.0))
        trend_scores = trend_by_cat.get(cat.value, [])

        categories.append(CategoryProgressDetail(
            category=cat.value,
            display_name=_display_name(cat.value),
            total_sessions=cat_sessions,
            total_questions=cat_total,
            correct_answers=cat_correct,
            accuracy_percent=round((cat_correct / cat_total * 100) if cat_total > 0 else 0.0, 1),
            avg_score=round(scores[0], 1),
            best_score=round(scores[1], 1),
            trend=_calc_trend(trend_scores),
        ))

    return OverallProgressResponse(
        total_sessions=total_sessions,
        total_questions=total_q,
        overall_accuracy=round((total_correct / total_q * 100) if total_q > 0 else 0.0, 1),
        avg_score=round(avg_score, 1),
        categories=categories,
    )


# ---------------------------------------------------------------------------
# GET /weak-areas — categories where user struggles
# ---------------------------------------------------------------------------

@router.get("/weak-areas", response_model=WeakAreasResponse)
async def get_weak_areas(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    min_questions: int = Query(3, ge=1, description="Min questions to consider a category"),
    limit: int = Query(5, ge=1, le=10, description="Max weak areas to return"),
):
    """Identify weakest categories based on error history."""
    stmt = (
        select(
            KnowledgeAnswer.question_category,
            func.count(KnowledgeAnswer.id).label("total"),
            func.sum(case((KnowledgeAnswer.is_correct == True, 1), else_=0)).label("correct"),  # noqa: E712
            func.sum(case((KnowledgeAnswer.is_correct == False, 1), else_=0)).label("incorrect"),  # noqa: E712
        )
        .where(KnowledgeAnswer.user_id == user.id)
        .group_by(KnowledgeAnswer.question_category)
        .having(func.count(KnowledgeAnswer.id) >= min_questions)
    )
    result = await db.execute(stmt)
    rows = result.all()

    # Calculate accuracy and sort ascending (worst first)
    areas = []
    for row in rows:
        total = row.total
        correct = row.correct or 0
        incorrect = row.incorrect or 0
        accuracy = round((correct / total * 100) if total > 0 else 0.0, 1)

        if accuracy < 80:  # Only flag categories below 80% accuracy
            recommendation = _generate_recommendation(row.question_category, accuracy)
            areas.append(WeakArea(
                category=row.question_category,
                display_name=_display_name(row.question_category),
                accuracy_percent=accuracy,
                total_questions=total,
                incorrect_answers=incorrect,
                recommendation=recommendation,
            ))

    areas.sort(key=lambda a: a.accuracy_percent)

    return WeakAreasResponse(weak_areas=areas[:limit])


def _generate_recommendation(category: str, accuracy: float) -> str:
    """Generate a study recommendation based on category and accuracy."""
    severity = "critically low" if accuracy < 40 else "low" if accuracy < 60 else "below target"
    display = _display_name(category)
    return (
        f"Your accuracy in '{display}' is {severity} ({accuracy}%). "
        f"We recommend reviewing this topic in themed mode to improve."
    )


# ---------------------------------------------------------------------------
# GET /leaderboard — PvP / overall leaderboard
# ---------------------------------------------------------------------------

@router.get("/leaderboard", response_model=KnowledgeLeaderboardResponse)
async def get_leaderboard(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    top: int = Query(20, ge=1, le=100, description="Number of top entries"),
    mode: str | None = Query(None, description="Filter by mode (e.g. pvp)"),
):
    """Get knowledge quiz leaderboard ranked by total score."""
    base = (
        select(
            KnowledgeQuizSession.user_id,
            func.sum(KnowledgeQuizSession.score).label("total_score"),
            func.count(KnowledgeQuizSession.id).label("sessions_count"),
            func.avg(
                case(
                    (
                        KnowledgeQuizSession.total_questions > 0,
                        KnowledgeQuizSession.correct_answers * 100.0 / KnowledgeQuizSession.total_questions,
                    ),
                    else_=0.0,
                )
            ).label("avg_accuracy"),
        )
        .where(KnowledgeQuizSession.status == QuizSessionStatus.completed)
    )

    if mode:
        try:
            base = base.where(KnowledgeQuizSession.mode == QuizMode(mode))
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid mode '{mode}'.",
            )

    base = (
        base
        .group_by(KnowledgeQuizSession.user_id)
        .order_by(desc("total_score"))
        .limit(top)
    )

    result = await db.execute(base)
    rows = result.all()

    # Fetch display names for all users in one query
    user_ids = [row.user_id for row in rows]
    if user_ids:
        users_stmt = select(User.id, User.full_name).where(User.id.in_(user_ids))
        users_result = await db.execute(users_stmt)
        user_names = {uid: name or "Anonymous" for uid, name in users_result.all()}
    else:
        user_names = {}

    entries = []
    user_rank = None
    for idx, row in enumerate(rows, 1):
        entries.append(LeaderboardEntry(
            rank=idx,
            user_id=row.user_id,
            display_name=user_names.get(row.user_id, "Anonymous"),
            total_score=round(float(row.total_score or 0), 1),
            sessions_count=row.sessions_count,
            avg_accuracy=round(float(row.avg_accuracy or 0), 1),
        ))
        if row.user_id == user.id:
            user_rank = idx

    # If current user not in top N, find their rank
    if user_rank is None:
        rank_stmt = (
            select(func.count())
            .select_from(
                select(KnowledgeQuizSession.user_id)
                .where(KnowledgeQuizSession.status == QuizSessionStatus.completed)
                .group_by(KnowledgeQuizSession.user_id)
                .having(
                    func.sum(KnowledgeQuizSession.score) >= (
                        select(func.sum(KnowledgeQuizSession.score))
                        .where(
                            KnowledgeQuizSession.user_id == user.id,
                            KnowledgeQuizSession.status == QuizSessionStatus.completed,
                        )
                    )
                )
                .subquery()
            )
        )
        rank_result = await db.execute(rank_stmt)
        user_rank = rank_result.scalar()

    # Total players
    total_stmt = (
        select(func.count(func.distinct(KnowledgeQuizSession.user_id)))
        .where(KnowledgeQuizSession.status == QuizSessionStatus.completed)
    )
    total_players = (await db.execute(total_stmt)).scalar() or 0

    return KnowledgeLeaderboardResponse(
        entries=entries,
        user_rank=user_rank,
        total_players=total_players,
    )


# ---------------------------------------------------------------------------
# POST /challenges — create PvP challenge
# ---------------------------------------------------------------------------

@router.post("/challenges", response_model=ChallengeResponse, status_code=status.HTTP_201_CREATED)
async def create_challenge(
    body: ChallengeCreateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a PvP challenge. Other users can see and accept it."""
    # Validate category if provided
    if body.category:
        valid_categories = [c.value for c in LegalCategory]
        if body.category not in valid_categories:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid category '{body.category}'. Must be one of: {valid_categories}",
            )

    # Check if user already has an active challenge
    existing_stmt = (
        select(QuizChallenge)
        .where(
            QuizChallenge.challenger_id == user.id,
            QuizChallenge.is_active == True,  # noqa: E712
            QuizChallenge.expires_at > func.now(),
        )
    )
    existing = (await db.execute(existing_stmt)).scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You already have an active challenge. Wait for it to expire or be accepted.",
        )

    challenge = QuizChallenge(
        challenger_id=user.id,
        category=body.category,
        max_players=body.max_players,
        is_active=True,
        accepted_by=[],
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=60),
    )
    db.add(challenge)
    await db.commit()
    await db.refresh(challenge)

    return ChallengeResponse(
        id=challenge.id,
        challenger_id=challenge.challenger_id,
        category=challenge.category,
        max_players=challenge.max_players,
        is_active=challenge.is_active,
        session_id=challenge.session_id,
        accepted_by=challenge.accepted_by or [],
        expires_at=challenge.expires_at,
        created_at=challenge.created_at,
    )


# ---------------------------------------------------------------------------
# GET /challenges/active — list active challenges
# ---------------------------------------------------------------------------

@router.get("/challenges/active", response_model=ActiveChallengesResponse)
async def list_active_challenges(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List currently active PvP challenges that can be joined."""
    stmt = (
        select(QuizChallenge)
        .where(
            QuizChallenge.is_active == True,  # noqa: E712
            QuizChallenge.expires_at > func.now(),
        )
        .order_by(desc(QuizChallenge.created_at))
        .limit(50)
    )
    result = await db.execute(stmt)
    challenges = result.scalars().all()

    return ActiveChallengesResponse(
        challenges=[
            ChallengeResponse(
                id=c.id,
                challenger_id=c.challenger_id,
                category=c.category,
                max_players=c.max_players,
                is_active=c.is_active,
                session_id=c.session_id,
                accepted_by=c.accepted_by or [],
                expires_at=c.expires_at,
                created_at=c.created_at,
            )
            for c in challenges
        ]
    )
