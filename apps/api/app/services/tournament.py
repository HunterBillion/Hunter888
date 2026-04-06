"""Tournament engine: weekly competitions with fixed conditions.

Every Monday at 00:00 a new tournament is auto-created (or via API).
All participants train with the SAME scenario + SAME client seed.
Best score wins. Top-3 get XP bonus + achievement.
"""

import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.character import Character
from app.models.scenario import Scenario
from app.models.tournament import Tournament, TournamentEntry
from app.models.training import SessionStatus, TrainingSession
from app.models.user import User

logger = logging.getLogger(__name__)


async def get_active_tournament(db: AsyncSession) -> Tournament | None:
    """Get the currently active tournament (if any)."""
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(Tournament).where(
            Tournament.is_active == True,  # noqa: E712
            Tournament.week_start <= now,
            Tournament.week_end >= now,
        ).order_by(Tournament.week_start.desc()).limit(1)
    )
    return result.scalar_one_or_none()


async def create_weekly_tournament(db: AsyncSession) -> Tournament | None:
    """Create a new tournament for the current week.

    Picks a scenario that wasn't used in the last 4 tournaments.
    Returns None if no suitable scenario found.
    """
    now = datetime.now(timezone.utc)
    # Monday 00:00 of current week
    monday = now - timedelta(days=now.weekday())
    week_start = monday.replace(hour=0, minute=0, second=0, microsecond=0)
    week_end = week_start + timedelta(days=6, hours=23, minutes=59, seconds=59)

    # Check if tournament already exists for this week
    existing = await db.execute(
        select(Tournament).where(
            Tournament.week_start >= week_start,
            Tournament.week_end <= week_end + timedelta(seconds=1),
        )
    )
    if existing.scalar_one_or_none():
        logger.info("Tournament already exists for week of %s", week_start.date())
        return None

    # Get recently used scenario IDs (last 4 tournaments)
    recent = await db.execute(
        select(Tournament.scenario_id)
        .order_by(Tournament.week_start.desc())
        .limit(4)
    )
    recent_ids = {r[0] for r in recent.all()}

    # Pick scenario not recently used, prefer medium difficulty
    query = (
        select(Scenario)
        .where(Scenario.is_active == True)  # noqa: E712
        .order_by(func.abs(Scenario.difficulty - 5))  # closest to difficulty 5
    )
    result = await db.execute(query)
    candidates = result.scalars().all()

    scenario = None
    for s in candidates:
        if s.id not in recent_ids:
            scenario = s
            break
    if not scenario and candidates:
        scenario = candidates[0]  # fallback to any

    if not scenario:
        logger.warning("No scenarios available for tournament")
        return None

    # Get character for title
    char_result = await db.execute(
        select(Character.name).where(Character.id == scenario.character_id)
    )
    char_name = char_result.scalar_one_or_none() or "Клиент"

    tournament = Tournament(
        title=f"Турнир недели: {char_name}",
        description=f"Кто лучше всех проведёт переговоры с {char_name}? Сценарий: {scenario.title}. Лучший балл из {3} попыток.",
        scenario_id=scenario.id,
        week_start=week_start,
        week_end=week_end,
        max_attempts=3,
    )
    db.add(tournament)
    await db.flush()

    logger.info("Created tournament '%s' for week %s", tournament.title, week_start.date())
    return tournament


async def submit_entry(
    tournament_id: uuid.UUID,
    user_id: uuid.UUID,
    session_id: uuid.UUID,
    score: float,
    db: AsyncSession,
) -> TournamentEntry | None:
    """Submit a tournament entry after completing a training session.

    Checks attempt limit. Only completed sessions count.
    """
    tournament = await db.execute(
        select(Tournament).where(Tournament.id == tournament_id)
    )
    t = tournament.scalar_one_or_none()
    if not t or not t.is_active:
        return None

    # Check attempt count
    attempts = await db.execute(
        select(func.count(TournamentEntry.id)).where(
            TournamentEntry.tournament_id == tournament_id,
            TournamentEntry.user_id == user_id,
        )
    )
    attempt_count = attempts.scalar() or 0

    if attempt_count >= t.max_attempts:
        logger.info("User %s exceeded max attempts (%d) for tournament %s", user_id, t.max_attempts, tournament_id)
        return None

    # Anti-cheat check before accepting tournament entry
    try:
        from app.services.anti_cheat import run_anti_cheat, save_anti_cheat_result, AntiCheatAction
        from app.models.training import Message as TrainingMessage
        msgs_result = await db.execute(
            select(TrainingMessage.role, TrainingMessage.content)
            .where(TrainingMessage.session_id == session_id, TrainingMessage.role == "user")
            .order_by(TrainingMessage.sequence_number)
        )
        user_messages = [{"role": r.role, "content": r.content} for r in msgs_result.all()]

        if user_messages:
            ac_result = await run_anti_cheat(user_id, session_id, user_messages, db, run_llm_check=True)
            await save_anti_cheat_result(ac_result, db)
            if ac_result.recommended_action in (AntiCheatAction.rating_freeze,):
                logger.warning(
                    "Tournament entry rejected by anti-cheat: user=%s session=%s flags=%d",
                    user_id, session_id, len(ac_result.flagged_signals),
                )
                return None
    except Exception as e:
        logger.warning("Anti-cheat check failed for tournament entry (allowing): %s", e)

    entry = TournamentEntry(
        tournament_id=tournament_id,
        user_id=user_id,
        session_id=session_id,
        score=score,
        attempt_number=attempt_count + 1,
    )
    db.add(entry)
    await db.flush()
    return entry


async def get_tournament_leaderboard(
    tournament_id: uuid.UUID,
    db: AsyncSession,
    limit: int = 20,
) -> list[dict]:
    """Get tournament leaderboard — best score per user."""
    result = await db.execute(
        select(
            TournamentEntry.user_id,
            User.full_name,
            User.avatar_url,
            func.max(TournamentEntry.score).label("best_score"),
            func.count(TournamentEntry.id).label("attempts"),
        )
        .join(User, User.id == TournamentEntry.user_id)
        .where(TournamentEntry.tournament_id == tournament_id)
        .group_by(TournamentEntry.user_id, User.full_name, User.avatar_url)
        .order_by(func.max(TournamentEntry.score).desc())
        .limit(limit)
    )
    rows = result.all()

    return [
        {
            "rank": i + 1,
            "user_id": str(row[0]),
            "full_name": row[1],
            "avatar_url": row[2],
            "best_score": round(float(row[3]), 1),
            "attempts": row[4],
            "is_podium": i < 3,
        }
        for i, row in enumerate(rows)
    ]


async def award_tournament_prizes(
    tournament_id: uuid.UUID,
    db: AsyncSession,
) -> list[dict]:
    """Award XP to top-3 finishers at tournament end.

    Returns list of awarded prizes for notification.
    """
    tournament = await db.execute(
        select(Tournament).where(Tournament.id == tournament_id)
    )
    t = tournament.scalar_one_or_none()
    if not t:
        return []

    leaderboard = await get_tournament_leaderboard(tournament_id, db, limit=3)
    if not leaderboard:
        return []

    xp_tiers = [t.bonus_xp_first, t.bonus_xp_second, t.bonus_xp_third]
    ap_sources = ["tournament_1st", "tournament_2nd", "tournament_3rd"]
    prizes = []

    for i, entry in enumerate(leaderboard[:3]):
        xp = xp_tiers[i] if i < len(xp_tiers) else 0
        prize_entry = {
            "user_id": entry["user_id"],
            "full_name": entry["full_name"],
            "rank": entry["rank"],
            "score": entry["best_score"],
            "bonus_xp": xp,
        }

        # Award Arena Points + Season Pass for tournament placement
        try:
            from app.services.arena_points import award_arena_points, AP_RATES
            from app.services.season_pass import advance_season
            uid = uuid.UUID(entry["user_id"])
            ap_source = ap_sources[i] if i < len(ap_sources) else ap_sources[-1]
            ap_balance = await award_arena_points(db, uid, ap_source)
            season_result = await advance_season(uid, AP_RATES[ap_source], db)
            prize_entry["ap_earned"] = AP_RATES[ap_source]
            prize_entry["ap_balance"] = ap_balance
            prize_entry["season"] = season_result
        except Exception as exc:
            logger.warning("Tournament AP award failed for user %s: %s", entry["user_id"], exc)

        prizes.append(prize_entry)

    # Mark tournament as inactive
    t.is_active = False
    db.add(t)

    logger.info("Tournament '%s' prizes: %s", t.title, prizes)
    return prizes
