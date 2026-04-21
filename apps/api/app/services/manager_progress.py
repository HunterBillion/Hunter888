"""
ТЗ-06: Inter-session адаптация, расчёт навыков, XP, уровни, достижения.

Анализирует историю сессий менеджера и формирует:
- 6 скилл-рейтингов (0-100)
- Слабые места и рекомендации
- XP и прогрессия уровней
- Достижения
- Параметры следующей сессии
"""
from __future__ import annotations

import logging
import math
import random
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from statistics import mean, stdev
from typing import Any

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.progress import (
    ManagerProgress,
    SessionHistory,
    EarnedAchievement as Achievement,
    AchievementDefinition,
    ALL_ARCHETYPES,
    ALL_SCENARIOS,
    SKILL_NAMES,
)
from scripts.seed_levels import (
    LEVEL_XP_THRESHOLDS,
    ACHIEVEMENTS as ACHIEVEMENT_DEFS,
    get_cumulative_archetypes,
    get_cumulative_scenarios,
    get_max_difficulty,
    get_level_for_xp,
    get_level_name,
)

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────
#  Константы
# ──────────────────────────────────────────────────────────────────────

XP_CAP_PER_SESSION = 200
SKILL_SMOOTHING_ALPHA = 0.30
COLD_START_SESSIONS = 5
WEAK_POINT_GAP = 15  # навык ниже среднего на 15+ → weak

# ── Skill mastery levels ─────────────────────────────────────────────
SKILL_MASTERY_LEVELS: list[dict] = [
    {"level": 1, "name": "Стажёр",       "name_en": "trainee",      "min_score": 0,  "max_score": 25,  "badge": "🔰"},
    {"level": 2, "name": "Практикант",    "name_en": "apprentice",   "min_score": 26, "max_score": 45,  "badge": "📘"},
    {"level": 3, "name": "Специалист",    "name_en": "specialist",   "min_score": 46, "max_score": 65,  "badge": "⭐"},
    {"level": 4, "name": "Профессионал",  "name_en": "professional", "min_score": 66, "max_score": 80,  "badge": "🏅"},
    {"level": 5, "name": "Эксперт",       "name_en": "expert",       "min_score": 81, "max_score": 95,  "badge": "💎"},
    {"level": 6, "name": "Мастер",        "name_en": "master",       "min_score": 96, "max_score": 100, "badge": "👑"},
]


def get_skill_mastery(score: float) -> dict:
    """Get mastery level info for a skill score (0-100).

    Returns dict with: level, name, name_en, badge, progress_in_level (0-100%).
    """
    score = max(0.0, min(100.0, score))
    for mastery in reversed(SKILL_MASTERY_LEVELS):
        if score >= mastery["min_score"]:
            range_size = mastery["max_score"] - mastery["min_score"] + 1
            progress = ((score - mastery["min_score"]) / range_size) * 100 if range_size > 0 else 100
            return {
                "level": mastery["level"],
                "name": mastery["name"],
                "name_en": mastery["name_en"],
                "badge": mastery["badge"],
                "progress_in_level": round(min(100.0, progress), 1),
            }
    return {"level": 1, "name": "Стажёр", "name_en": "trainee", "badge": "🔰", "progress_in_level": 0}


def get_all_skill_masteries(skills: dict[str, float]) -> dict[str, dict]:
    """Get mastery levels for all 6 skills.

    Args:
        skills: Dict of skill_name → score (0-100)

    Returns:
        Dict of skill_name → mastery info
    """
    return {skill: get_skill_mastery(score) for skill, score in skills.items()}

# Маппинг навыков → архетипы для рекомендаций
SKILL_ARCHETYPE_MAP: dict[str, list[str]] = {
    "empathy": ["anxious", "desperate", "crying", "ashamed", "overwhelmed"],
    "knowledge": ["know_it_all", "lawyer_client", "shopper", "sarcastic"],
    "objection_handling": ["skeptic", "paranoid", "shopper", "negotiator"],
    "stress_resistance": ["aggressive", "hostile", "manipulator", "blamer", "couple"],
    "closing": ["pragmatic", "negotiator", "passive", "avoidant", "rushed"],
    "qualification": ["passive", "avoidant", "delegator", "overwhelmed"],
}

# Маппинг навыков → сценарии для рекомендаций
SKILL_SCENARIO_MAP: dict[str, list[str]] = {
    "empathy": ["in_hotline", "warm_callback", "rescue"],
    "knowledge": ["in_website", "cold_ad", "upsell"],
    "objection_handling": ["cold_base", "warm_refused", "cold_partner"],
    "stress_resistance": ["cold_base", "rescue", "special_couple"],
    "closing": ["in_website", "warm_callback", "in_social"],
    "qualification": ["cold_ad", "cold_base", "in_website", "in_social"],
}

# Архетипы для расчёта навыков
EMPATHY_ARCHETYPES = {"anxious", "desperate", "crying", "ashamed", "overwhelmed"}
KNOWLEDGE_ARCHETYPES = {"know_it_all", "lawyer_client", "shopper", "sarcastic"}
OBJECTION_ARCHETYPES = {"skeptic", "paranoid", "shopper", "know_it_all", "sarcastic"}
STRESS_ARCHETYPES = {"aggressive", "hostile", "manipulator", "blamer", "couple"}
QUALIFICATION_SCENARIOS = {"in_website", "in_hotline", "in_social", "cold_ad", "cold_base"}

NEGATIVE_EMOTION_PEAKS = {"hostile", "hangup", "cold", "guarded"}
POSITIVE_EMOTION_PEAKS = {"deal", "callback", "considering", "negotiating"}

# Emotion peak scoring для empathy
EMOTION_PEAK_SCORES: dict[str, int] = {
    "hostile": 0, "hangup": 5, "cold": 20, "guarded": 30,
    "testing": 40, "curious": 65, "considering": 75,
    "negotiating": 85, "callback": 90, "deal": 100,
}

# Tips для каждого навыка
SKILL_TIPS: dict[str, list[str]] = {
    "empathy": [
        "Начинайте ответ со слов «Я понимаю...» перед тем, как давать информацию",
        "Обращайте внимание на слова клиента о чувствах и отражайте их",
        "Делайте паузу после эмоциональных высказываний клиента",
    ],
    "knowledge": [
        "Запомните: порог 500К, срок 5 лет, единственное жильё защищено",
        "Когда клиент утверждает факт — не соглашайтесь, проверяйте по 127-ФЗ",
        "Изучите основные статьи: ст. 213.3, ст. 213.4, ст. 213.25, ст. 213.30",
    ],
    "objection_handling": [
        "Используйте технику «Согласие + Но»: «Да, я понимаю, и именно поэтому...»",
        "Не спорьте — переводите возражение в вопрос",
        "После обработки возражения сразу предлагайте следующий шаг",
    ],
    "stress_resistance": [
        "Когда клиент кричит — досчитайте до трёх перед ответом",
        "Не принимайте агрессию лично — клиент злится на ситуацию",
        "Техника «стена»: спокойным голосом повторите ключевую выгоду",
    ],
    "closing": [
        "Предлагайте КОНКРЕТНОЕ время: «Завтра в 15:00 удобно?»",
        "Используйте альтернативный выбор: «Утром или вечером?»",
        "После согласия — сразу подтвердите детали (адрес, время, имя юриста)",
    ],
    "qualification": [
        "Задавайте открытые вопросы: «Расскажите о вашей ситуации»",
        "Узнайте 4 ключевых факта: сумму, кредиторов, имущество, доход",
        "Не переходите к продаже, пока не собрали минимум информации",
    ],
}


# ──────────────────────────────────────────────────────────────────────
#  Data classes
# ──────────────────────────────────────────────────────────────────────

@dataclass
class SessionParams:
    """Рекомендованные параметры следующей сессии."""
    difficulty: int
    scenario: str
    archetype: str
    focus_skill: str
    traps_focus: list[str]
    confidence: str = "medium"
    weak_points: list[str] | None = None
    tips: list[str] | None = None


@dataclass
class XPBreakdown:
    """Разбивка XP за сессию."""
    base: int = 0
    difficulty: int = 0
    outcome: int = 0
    traps: int = 0
    chain: int = 0
    comeback: int = 0
    time: int = 0
    session_total: int = 0
    achievements: int = 0
    grand_total: int = 0


@dataclass
class SkillUpdate:
    """Результат обновления навыков."""
    old_skills: dict[str, int]
    new_skills: dict[str, int]
    changes: dict[str, int]


# ──────────────────────────────────────────────────────────────────────
#  ManagerProgressService
# ──────────────────────────────────────────────────────────────────────

class ManagerProgressService:
    """Управляет прогрессией менеджера между сессиями."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    # ── Получение / создание профиля ──

    async def get_or_create_profile(
        self, user_id: uuid.UUID, *, lock: bool = False,
    ) -> ManagerProgress:
        query = select(ManagerProgress).where(ManagerProgress.user_id == user_id)
        if lock:
            query = query.with_for_update()
        result = await self._db.execute(query)
        profile = result.scalar_one_or_none()
        if profile is None:
            profile = ManagerProgress(user_id=user_id)
            self._db.add(profile)
            await self._db.flush()
        return profile

    # ── Основной метод: обработка завершённой сессии ──

    async def update_after_session(
        self,
        user_id: uuid.UUID,
        session_result: SessionHistory,
        adaptive_data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Обрабатывает завершённую сессию: обновляет навыки, XP, уровень, достижения.

        Returns:
            dict с ключами: xp_breakdown, level_up, new_level, new_achievements, skills_update
        """
        # Diag v9: FOR UPDATE prevents lost-update race on concurrent session completions
        profile = await self.get_or_create_profile(user_id, lock=True)

        # 1. Рассчитать XP
        xp_breakdown = self.calculate_xp(session_result, adaptive_data)

        # 2. Обновить навыки
        skills_update = await self._update_skills(profile, session_result)

        # 3. Проверить достижения
        new_achievements = await self._check_achievements(profile, session_result, adaptive_data)

        # Добавить XP за достижения
        achievement_xp = sum(a.xp_bonus for a in new_achievements)
        xp_breakdown.achievements = achievement_xp
        xp_breakdown.grand_total = xp_breakdown.session_total + achievement_xp

        # 3b. Write XPLog entry for audit trail
        try:
            from app.models.xp_log import XPLog, SP_RATES
            xp_log = XPLog(
                user_id=user_id,
                source="training_session",
                amount=xp_breakdown.session_total,
                multiplier=1.0,
                season_points=SP_RATES.get("training_session", 10),
            )
            self._db.add(xp_log)
            if achievement_xp > 0:
                ach_xp_log = XPLog(
                    user_id=user_id,
                    source="achievement",
                    amount=achievement_xp,
                    multiplier=1.0,
                    season_points=SP_RATES.get("achievement", 10),
                )
                self._db.add(ach_xp_log)
        except Exception:
            logger.warning("Failed to write XPLog for user %s", user_id, exc_info=True)

        # 4. Apply daily soft cap (S3-02) then update profile
        try:
            from app.services.xp_daily_cap import apply_daily_cap
            # Session XP goes through cap; achievement XP is exempt
            capped_session_xp = await apply_daily_cap(
                user_id, xp_breakdown.session_total, source="training_session",
            )
            capped_achievement_xp = await apply_daily_cap(
                user_id, achievement_xp, source="achievement",
            )
            xp_breakdown.grand_total = capped_session_xp + capped_achievement_xp
        except Exception:
            logger.warning("Daily XP cap unavailable, using full XP", exc_info=True)

        profile.total_xp += xp_breakdown.grand_total
        profile.current_xp += xp_breakdown.grand_total
        profile.total_sessions += 1
        profile.total_hours = float(profile.total_hours) + session_result.duration_seconds / 3600.0

        # 5. Обновить deal streak
        if session_result.outcome == "deal":
            profile.current_deal_streak += 1
            profile.best_deal_streak = max(profile.best_deal_streak, profile.current_deal_streak)
        else:
            profile.current_deal_streak = 0

        # 5b. Обновить perfect streak (sessions with score >80)
        if session_result.score_total and session_result.score_total >= 80:
            profile.perfect_streak += 1
            profile.best_perfect_streak = max(profile.best_perfect_streak, profile.perfect_streak)
        else:
            profile.perfect_streak = 0

        # 6. Обновить калибровку
        if not profile.calibration_complete:
            profile.calibration_sessions += 1
            if profile.calibration_sessions >= COLD_START_SESSIONS:
                profile.calibration_complete = True
                profile.skill_confidence = "medium"
            else:
                profile.skill_confidence = "low"
        elif profile.total_sessions >= 20:
            profile.skill_confidence = "very_high"
        elif profile.total_sessions >= 10:
            profile.skill_confidence = "high"

        # 7. Проверить level up
        level_up_result = await self._check_level_up(profile)

        # 8. Обновить weak points
        self._update_weak_points(profile)

        await self._db.flush()

        return {
            "xp_breakdown": asdict(xp_breakdown),
            "level_up": level_up_result["leveled_up"],
            "new_level": level_up_result.get("new_level"),
            "new_level_name": level_up_result.get("new_level_name"),
            "new_achievements": [
                {"code": a.achievement_code, "name": a.achievement_name, "xp": a.xp_bonus}
                for a in new_achievements
            ],
            "skills_update": asdict(skills_update) if skills_update else None,
        }

    # ── XP расчёт ──

    @staticmethod
    def calculate_xp(
        result: SessionHistory,
        adaptive_data: dict[str, Any] | None = None,
    ) -> XPBreakdown:
        """Рассчитывает XP за сессию (cap: 200 без достижений)."""
        xp = XPBreakdown()

        # Базовый XP = score
        xp.base = result.score_total

        # Бонус за сложность
        xp.difficulty = result.difficulty * 5

        # Бонус за результат
        outcome_bonuses = {"deal": 30, "callback": 15, "hangup": 0, "hostile": 0, "timeout": 0}
        xp.outcome = outcome_bonuses.get(result.outcome, 0)

        # Бонус за ловушки
        trap_bonus = result.traps_dodged * 5
        trap_penalty = result.traps_fell * 2
        xp.traps = max(0, trap_bonus - trap_penalty)

        # Бонус за цепочку
        xp.chain = 20 if result.chain_completed else 0

        # Бонус за камбэк
        had_comeback = adaptive_data.get("had_comeback", False) if adaptive_data else result.had_comeback
        xp.comeback = 15 if had_comeback else 0

        # Бонус за время
        duration_min = result.duration_seconds / 60.0
        if 5 <= duration_min <= 12:
            xp.time = 10
        elif 3 <= duration_min < 5:
            xp.time = 5
        else:
            xp.time = 0

        raw = xp.base + xp.difficulty + xp.outcome + xp.traps + xp.chain + xp.comeback + xp.time
        xp.session_total = min(XP_CAP_PER_SESSION, raw)
        xp.grand_total = xp.session_total  # achievements added later

        return xp

    # ── Расчёт навыков ──

    async def calculate_skills(self, user_id: uuid.UUID) -> dict[str, int]:
        """Рассчитывает все 6 навыков на основе последних сессий."""
        sessions = await self._get_recent_sessions(user_id, limit=10)
        if not sessions:
            return {s: 50 for s in SKILL_NAMES}

        return {
            "empathy": self._calc_empathy(sessions),
            "knowledge": self._calc_knowledge(sessions),
            "objection_handling": self._calc_objection_handling(sessions),
            "stress_resistance": self._calc_stress_resistance(sessions),
            "closing": self._calc_closing(sessions),
            "qualification": self._calc_qualification(sessions),
        }

    async def calculate_skills_with_arena(self, user_id: uuid.UUID) -> dict[str, int]:
        """Рассчитывает навыки с учётом данных Арены знаний.

        Knowledge skill = training_component * 0.5 + arena_accuracy * 0.35 + pvp_win_rate * 0.15

        Block 5 (Cross-Module): Arena data enriches the knowledge skill.
        """
        sessions = await self._get_recent_sessions(user_id, limit=10)
        if not sessions:
            return {s: 50 for s in SKILL_NAMES}

        base_skills = {
            "empathy": self._calc_empathy(sessions),
            "knowledge": self._calc_knowledge(sessions),
            "objection_handling": self._calc_objection_handling(sessions),
            "stress_resistance": self._calc_stress_resistance(sessions),
            "closing": self._calc_closing(sessions),
            "qualification": self._calc_qualification(sessions),
        }

        # Enrich knowledge skill with Arena data
        try:
            arena_knowledge = await self._calc_knowledge_with_arena(
                user_id, base_skills["knowledge"],
            )
            base_skills["knowledge"] = arena_knowledge
        except Exception:
            logger.debug("Arena data unavailable for knowledge skill", exc_info=True)

        return base_skills

    async def _calc_knowledge_with_arena(
        self, user_id: uuid.UUID, training_score: int,
    ) -> int:
        """Calculate knowledge skill combining training + Arena quiz + PvP data.

        Formula:
            knowledge = training_component * 0.5 + arena_accuracy * 0.35 + pvp_win_rate * 0.15
        """
        from app.services.knowledge_quiz import get_category_progress

        # Arena quiz accuracy
        arena_score = 0
        try:
            category_progress = await get_category_progress(user_id, self._db)
            if category_progress:
                total_correct = sum(
                    cp.get("correct_answers", 0) for cp in category_progress
                )
                total_answered = sum(
                    cp.get("total_answers", 0) for cp in category_progress
                )
                if total_answered >= 5:  # Minimum data threshold
                    arena_score = int((total_correct / total_answered) * 100)
                else:
                    # Not enough Arena data — use training only
                    return training_score
        except Exception:
            return training_score

        # PvP win rate (from PvP ratings)
        pvp_score = 0
        try:
            from app.models.pvp import PvPRating
            result = await self._db.execute(
                select(PvPRating).where(
                    PvPRating.user_id == user_id,
                    PvPRating.rating_type == "knowledge_arena",
                )
            )
            rating = result.scalar_one_or_none()
            if rating and rating.total_duels >= 3:  # Minimum 3 duels
                pvp_score = int((rating.wins / rating.total_duels) * 100)
            else:
                # Not enough PvP data — split between training and arena
                final = int(training_score * 0.6 + arena_score * 0.4)
                return max(0, min(100, final))
        except Exception:
            final = int(training_score * 0.6 + arena_score * 0.4)
            return max(0, min(100, final))

        # Full formula with all three components
        final = int(
            training_score * 0.5
            + arena_score * 0.35
            + pvp_score * 0.15
        )
        return max(0, min(100, final))

    # ── Рекомендация следующей сессии ──

    async def recommend_next_session(self, user_id: uuid.UUID) -> SessionParams:
        """Генерирует рекомендованные параметры для следующей сессии."""
        profile = await self.get_or_create_profile(user_id)
        sessions = await self._get_recent_sessions(user_id, limit=10)

        # Базовая сложность
        if not sessions:
            return SessionParams(
                difficulty=2,
                scenario="in_website",
                archetype="anxious",
                focus_skill="empathy",
                traps_focus=[],
                confidence="low",
                tips=["Первая сессия — просто попробуйте пройти разговор до конца"],
            )

        # Взвешенный средний score
        weights = [0.5 + 0.5 * (i / len(sessions)) for i in range(len(sessions))]
        total_weight = sum(weights)
        w_avg_score = sum((s.score_total or 0) * w for s, w in zip(sessions, weights)) / total_weight

        avg_diff = mean(s.difficulty for s in sessions)

        if w_avg_score >= 80:
            diff_delta = 2
        elif w_avg_score >= 65:
            diff_delta = 1
        elif w_avg_score >= 45:
            diff_delta = 0
        elif w_avg_score >= 30:
            diff_delta = -1
        else:
            diff_delta = -2

        max_diff = get_max_difficulty(profile.current_level)
        new_difficulty = max(1, min(max_diff, round(avg_diff) + diff_delta))

        # Слабые места
        skills = profile.skills_dict()
        avg_skill = mean(skills.values()) if skills else 50
        weak = sorted(
            [(k, v) for k, v in skills.items() if v < avg_skill - WEAK_POINT_GAP],
            key=lambda x: x[1],
        )
        if not weak:
            weakest_name = min(skills, key=skills.get)
            weak = [(weakest_name, skills[weakest_name])]

        primary_weakness = weak[0][0]

        # Выбор сценария
        available_scenarios = get_cumulative_scenarios(profile.current_level)
        recommended_scenarios = SKILL_SCENARIO_MAP.get(primary_weakness, [])
        scenario_candidates = [s for s in recommended_scenarios if s in available_scenarios]
        if not scenario_candidates:
            scenario_candidates = available_scenarios or ["in_website"]

        # Избегаем повторения последних 3
        recent_scenarios = [s.scenario_code for s in sessions[:3]]
        fresh = [s for s in scenario_candidates if s not in recent_scenarios]
        if fresh:
            scenario_candidates = fresh
        scenario = random.choice(scenario_candidates)

        # Выбор архетипа
        available_archetypes = get_cumulative_archetypes(profile.current_level)
        recommended_archetypes = SKILL_ARCHETYPE_MAP.get(primary_weakness, [])
        arch_candidates = [a for a in recommended_archetypes if a in available_archetypes]
        if not arch_candidates:
            arch_candidates = available_archetypes or ["skeptic"]

        recent_archs = [s.archetype_code for s in sessions[:3]]
        fresh_archs = [a for a in arch_candidates if a not in recent_archs]
        if fresh_archs:
            arch_candidates = fresh_archs
        archetype = random.choice(arch_candidates)

        # Tips
        tips = random.sample(SKILL_TIPS.get(primary_weakness, []), min(2, len(SKILL_TIPS.get(primary_weakness, []))))

        return SessionParams(
            difficulty=new_difficulty,
            scenario=scenario,
            archetype=archetype,
            focus_skill=primary_weakness,
            traps_focus=[],
            confidence=profile.skill_confidence,
            weak_points=[w[0] for w in weak],
            tips=tips,
        )

    # ── Получение слабых мест ──

    async def get_weak_points(self, user_id: uuid.UUID) -> list[dict[str, Any]]:
        profile = await self.get_or_create_profile(user_id)
        skills = profile.skills_dict()
        avg = mean(skills.values()) if skills else 50
        std = stdev(skills.values()) if len(skills) > 1 else 0

        result = []
        for name, value in skills.items():
            absolute_weak = value < 40
            relative_weak = std > 0 and value < (avg - std)
            lagging = value < (avg - WEAK_POINT_GAP)

            if absolute_weak and relative_weak:
                priority = "critical"
            elif absolute_weak or (relative_weak and lagging):
                priority = "high"
            elif lagging:
                priority = "medium"
            else:
                continue

            result.append({
                "skill": name,
                "value": value,
                "gap": round(avg - value, 1),
                "priority": priority,
            })

        result.sort(key=lambda x: (-{"critical": 3, "high": 2, "medium": 1}[x["priority"]], -x["gap"]))
        return result

    # ──────────────────────────────────────────────────────────────────
    #  Внутренние методы: расчёт навыков
    # ──────────────────────────────────────────────────────────────────

    @staticmethod
    def _calc_empathy(sessions: list[SessionHistory]) -> int:
        scores = []
        for s in sessions:
            score = 0.0
            bd = s.score_breakdown or {}
            comm = bd.get("communication", 10)
            score += (comm / 20.0) * 40

            peak = EMOTION_PEAK_SCORES.get(s.emotion_peak, 40)
            score += (peak / 100.0) * 30

            if s.archetype_code in EMPATHY_ARCHETYPES:
                if s.outcome in ("deal", "callback"):
                    score += 20
                elif s.score_total >= 60:
                    score += 12
                else:
                    score += 5
            else:
                score += 10

            anti = abs(bd.get("anti_patterns", 0))
            score += max(0, 10 - anti * 0.67)

            scores.append(min(100, round(score)))
        return round(mean(scores)) if scores else None

    @staticmethod
    def _calc_knowledge(sessions: list[SessionHistory]) -> int:
        scores = []
        for s in sessions:
            score = 0.0
            bd = s.score_breakdown or {}

            trap_h = bd.get("trap_handling", 0)
            score += ((trap_h + 10) / 20.0) * 40

            chain = bd.get("chain_traversal", 5)
            score += (chain / 10.0) * 25

            if s.archetype_code in KNOWLEDGE_ARCHETYPES:
                if s.traps_dodged > s.traps_fell:
                    score += 25
                elif s.traps_dodged == s.traps_fell:
                    score += 12
                else:
                    score += 5
            else:
                score += 12.5

            total_traps = s.traps_dodged + s.traps_fell
            if total_traps > 0:
                score += (s.traps_dodged / total_traps) * 10
            else:
                score += 5

            scores.append(min(100, round(score)))
        return round(mean(scores)) if scores else None

    @staticmethod
    def _calc_objection_handling(sessions: list[SessionHistory]) -> int:
        scores = []
        for s in sessions:
            score = 0.0
            bd = s.score_breakdown or {}

            obj = bd.get("objection_handling", 12)
            score += (obj / 25.0) * 50

            if s.archetype_code in OBJECTION_ARCHETYPES:
                outcome_sc = {"deal": 25, "callback": 18, "hangup": 5, "hostile": 0}
                score += outcome_sc.get(s.outcome, 5)
            else:
                score += 12.5

            score += (s.score_total / 100.0) * 15
            score += min(10, s.difficulty)

            scores.append(min(100, round(score)))
        return round(mean(scores)) if scores else None

    @staticmethod
    def _calc_stress_resistance(sessions: list[SessionHistory]) -> int:
        scores = []
        for s in sessions:
            score = 0.0
            bd = s.score_breakdown or {}

            if s.archetype_code in STRESS_ARCHETYPES:
                outcome_sc = {"deal": 40, "callback": 28, "hangup": 10, "hostile": 0}
                score += outcome_sc.get(s.outcome, 5)
            else:
                score += (s.score_total / 100.0) * 20

            if s.emotion_peak in NEGATIVE_EMOTION_PEAKS:
                if s.outcome in ("deal", "callback"):
                    score += 25
                elif s.score_total >= 50:
                    score += 15
                else:
                    score += 5
            else:
                score += 12.5

            anti = abs(bd.get("anti_patterns", 0))
            score += (max(0, 15 + bd.get("anti_patterns", 0)) / 15.0) * 20

            score += min(15, s.difficulty * 1.5)

            scores.append(min(100, round(score)))
        return round(mean(scores)) if scores else None

    @staticmethod
    def _calc_closing(sessions: list[SessionHistory]) -> int:
        scores = []
        for s in sessions:
            score = 0.0
            bd = s.score_breakdown or {}

            result_sc = bd.get("result", 5)
            score += (result_sc / 10.0) * 35

            outcome_sc = {"deal": 35, "callback": 20, "hangup": 5, "hostile": 0}
            score += outcome_sc.get(s.outcome, 5)

            if s.chain_completed:
                score += 15
            else:
                chain_p = bd.get("chain_traversal", 5)
                score += (chain_p / 10.0) * 10

            if s.outcome == "deal":
                score += min(15, s.difficulty * 1.5)
            elif s.outcome == "callback":
                score += min(10, s.difficulty)
            else:
                score += min(5, s.difficulty * 0.5)

            scores.append(min(100, round(score)))
        return round(mean(scores)) if scores else None

    @staticmethod
    def _calc_qualification(sessions: list[SessionHistory]) -> int:
        scores = []
        for s in sessions:
            score = 0.0
            bd = s.score_breakdown or {}

            script = bd.get("script_adherence", 15)
            score += (script / 30.0) * 45

            if s.scenario_code in QUALIFICATION_SCENARIOS:
                if script >= 20:
                    score += 25
                elif script >= 15:
                    score += 18
                elif script >= 10:
                    score += 10
                else:
                    score += 3
            else:
                score += 12.5

            score += (s.score_total / 100.0) * 20

            dur_min = s.duration_seconds / 60.0
            if 5 <= dur_min <= 15:
                score += 10
            elif 3 <= dur_min < 5 or 15 < dur_min <= 20:
                score += 7
            else:
                score += 3

            scores.append(min(100, round(score)))
        return round(mean(scores)) if scores else None

    @staticmethod
    def _calc_from_radar(sessions: list[SessionHistory], radar_key: str) -> int | None:
        """Average a per-session skill-radar axis across recent sessions.

        Used for skills that v5 scoring computes per session but the legacy
        aggregator doesn't have a dedicated _calc_* for:
        time_management, adaptation, legal_knowledge, rapport_building.
        """
        vals = []
        for s in sessions:
            bd = s.score_breakdown or {}
            radar = bd.get("_skill_radar") or {}
            v = radar.get(radar_key)
            if v is not None:
                vals.append(float(v))
        if not vals:
            return None
        return round(mean(vals))

    # ──────────────────────────────────────────────────────────────────
    #  Обновление навыков с экспоненциальным сглаживанием
    # ──────────────────────────────────────────────────────────────────

    async def _update_skills(
        self, profile: ManagerProgress, session: SessionHistory,
    ) -> SkillUpdate:
        sessions = await self._get_recent_sessions(profile.user_id, limit=10)
        new_raw = {
            "empathy": self._calc_empathy(sessions),
            "knowledge": self._calc_knowledge(sessions),
            "objection_handling": self._calc_objection_handling(sessions),
            "stress_resistance": self._calc_stress_resistance(sessions),
            "closing": self._calc_closing(sessions),
            "qualification": self._calc_qualification(sessions),
            # 4 additional v5 skills — derived from per-session skill_radar
            "time_management": self._calc_from_radar(sessions, "time_management"),
            "adaptation": self._calc_from_radar(sessions, "adaptation"),
            "legal_knowledge": self._calc_from_radar(sessions, "legal_knowledge"),
            "rapport_building": self._calc_from_radar(sessions, "rapport_building"),
        }

        old_skills = profile.skills_dict()

        # Alpha зависит от количества сессий (cold start)
        alpha = self._get_alpha(profile.calibration_sessions)

        new_skills = {}
        for name in SKILL_NAMES:
            old_val = old_skills[name]
            new_val = new_raw.get(name)
            if new_val is None:
                # No real session data for this skill yet — keep current (default=50) value.
                # Real skills with data will still be updated via EMA.
                new_skills[name] = old_val
                continue
            smoothed = round(alpha * new_val + (1 - alpha) * old_val)
            new_skills[name] = max(0, min(100, smoothed))

        profile.set_skills(new_skills)

        changes = {k: new_skills[k] - old_skills[k] for k in SKILL_NAMES}
        return SkillUpdate(old_skills=old_skills, new_skills=new_skills, changes=changes)

    @staticmethod
    def _get_alpha(calibration_sessions: int) -> float:
        """Alpha (коэффициент обучения) зависит от количества сессий."""
        if calibration_sessions <= 1:
            return 0.70
        elif calibration_sessions == 2:
            return 0.55
        elif calibration_sessions == 3:
            return 0.45
        elif calibration_sessions == 4:
            return 0.35
        else:
            return SKILL_SMOOTHING_ALPHA  # 0.30

    # ──────────────────────────────────────────────────────────────────
    #  Level up
    # ──────────────────────────────────────────────────────────────────

    async def _check_level_up(self, profile: ManagerProgress) -> dict[str, Any]:
        new_level = get_level_for_xp(profile.total_xp)
        if new_level > profile.current_level:
            # DOC_04: Gate level-up on required checkpoints
            try:
                from app.services.checkpoint_validator import CheckpointValidator
                validator = CheckpointValidator(self._db)
                eligibility = await validator.can_level_up(profile.user_id, profile.current_level)
                if not eligibility.checkpoints_met:
                    # XP sufficient but checkpoints not met — soft gate
                    profile.level_checkpoints_met = False
                    logger.info(
                        "Level up blocked by checkpoints: user=%s, level=%d, missing=%s",
                        profile.user_id, profile.current_level, eligibility.missing_checkpoints,
                    )
                    return {
                        "leveled_up": False,
                        "xp_sufficient": True,
                        "checkpoints_blocked": True,
                        "missing_checkpoints": eligibility.missing_checkpoints,
                    }
                profile.level_checkpoints_met = True
            except Exception as e:
                # If checkpoint system fails, don't block progression
                logger.warning("Checkpoint validation failed, allowing level up: %s", e)

            old_level = profile.current_level
            profile.current_level = new_level
            # Обновить разблокировки
            profile.unlocked_archetypes = get_cumulative_archetypes(new_level)
            profile.unlocked_scenarios = get_cumulative_scenarios(new_level)
            logger.info(
                "Level up! user=%s: %d → %d (%s)",
                profile.user_id, old_level, new_level, get_level_name(new_level),
            )
            # BUG-1 fix: emit EVENT_LEVEL_UP so notifications are sent
            from app.services.event_bus import event_bus, GameEvent, EVENT_LEVEL_UP
            try:
                await event_bus.emit(GameEvent(
                    kind=EVENT_LEVEL_UP,
                    user_id=profile.user_id,
                    db=self._db,
                    payload={
                        "old_level": old_level,
                        "new_level": new_level,
                        "new_level_name": get_level_name(new_level),
                    },
                ))
            except Exception as e:
                logger.warning("Failed to emit level_up event: %s", e)
            return {
                "leveled_up": True,
                "old_level": old_level,
                "new_level": new_level,
                "new_level_name": get_level_name(new_level),
            }
        return {"leveled_up": False}

    # ──────────────────────────────────────────────────────────────────
    #  Достижения
    # ──────────────────────────────────────────────────────────────────

    async def _check_achievements(
        self,
        profile: ManagerProgress,
        session: SessionHistory,
        adaptive_data: dict[str, Any] | None = None,
    ) -> list[Achievement]:
        """Проверяет и выдаёт новые достижения."""
        # Получить уже полученные
        existing = await self._db.execute(
            select(Achievement.achievement_code).where(Achievement.user_id == profile.user_id),
        )
        existing_codes = set(existing.scalars().all())

        # Pre-compute aggregate stats for condition types that need DB queries
        _extra_stats: dict[str, Any] = {}
        try:
            _ua = await self._db.execute(
                select(func.count(func.distinct(SessionHistory.archetype_code)))
                .where(SessionHistory.user_id == profile.user_id)
            )
            _extra_stats["unique_archetypes"] = _ua.scalar() or 0

            _us = await self._db.execute(
                select(func.count(func.distinct(SessionHistory.scenario_code)))
                .where(SessionHistory.user_id == profile.user_id)
            )
            _extra_stats["unique_scenarios"] = _us.scalar() or 0

            _week_ago = datetime.now(timezone.utc) - timedelta(days=7)
            _ws = await self._db.execute(
                select(func.count(SessionHistory.id))
                .where(SessionHistory.user_id == profile.user_id, SessionHistory.created_at >= _week_ago)
            )
            _extra_stats["weekly_sessions"] = _ws.scalar() or 0

            from app.services.gamification import calculate_streak
            _extra_stats["daily_streak"] = await calculate_streak(profile.user_id, self._db)
        except Exception:
            pass

        new_achievements: list[Achievement] = []

        for ach_def in ACHIEVEMENT_DEFS:
            code = ach_def["code"]
            if code in existing_codes:
                continue

            cond = ach_def["condition"]
            earned = self._evaluate_achievement(cond, profile, session, adaptive_data, _extra_stats)

            if earned:
                achievement = Achievement(
                    user_id=profile.user_id,
                    achievement_code=code,
                    achievement_name=ach_def["name"],
                    achievement_description=ach_def["description"],
                    rarity=ach_def["rarity"],
                    xp_bonus=ach_def["xp_bonus"],
                    category=ach_def["category"],
                    session_id=session.session_id,
                )
                self._db.add(achievement)
                new_achievements.append(achievement)
                logger.info("Achievement unlocked: %s for user %s", code, profile.user_id)

        return new_achievements

    def _evaluate_achievement(
        self,
        condition: dict,
        profile: ManagerProgress,
        session: SessionHistory,
        adaptive_data: dict[str, Any] | None,
        extra_stats: dict[str, Any] | None = None,
    ) -> bool:
        """Проверяет, выполнено ли условие достижения."""
        ctype = condition.get("type", "")
        _stats = extra_stats or {}

        if ctype == "outcome_count":
            if condition["outcome"] == session.outcome:
                return True

        elif ctype == "score_threshold":
            return session.score_total >= condition["min_score"]

        elif ctype == "deal_streak":
            return profile.current_deal_streak >= condition["count"]

        elif ctype == "total_sessions":
            return profile.total_sessions + 1 >= condition["count"]

        elif ctype == "trap_dodge_streak":
            # Упрощённая проверка: dodged >= count и fell == 0 в текущей сессии
            return session.traps_dodged >= condition["count"] and session.traps_fell == 0

        elif ctype == "chain_completion_streak":
            return session.chain_completed  # упрощено — нужен трек серий

        elif ctype == "zero_antipatterns":
            bd = session.score_breakdown or {}
            return bd.get("anti_patterns", -1) == 0

        elif ctype == "skill_threshold":
            skill_val = getattr(profile, f"skill_{condition['skill']}", 0)
            return skill_val >= condition["min_value"]

        elif ctype == "all_skills_threshold":
            min_val = condition["min_value"]
            return all(v >= min_val for v in profile.skills_dict().values())

        elif ctype == "deal_with_archetype":
            return (
                session.outcome == "deal"
                and session.archetype_code in condition.get("archetypes", [])
                and session.difficulty >= condition.get("min_difficulty", 1)
            )

        elif ctype == "deal_with_scenario":
            return (
                session.outcome == "deal"
                and session.scenario_code in condition.get("scenarios", [])
                and session.difficulty >= condition.get("min_difficulty", 1)
            )

        elif ctype == "comeback":
            had = adaptive_data.get("had_comeback", False) if adaptive_data else session.had_comeback
            return had and session.outcome == "deal"

        elif ctype == "deal_under_time":
            return session.outcome == "deal" and session.duration_seconds <= condition["max_seconds"]

        elif ctype == "deal_in_boss_mode":
            mg = adaptive_data.get("max_good_streak", 0) if adaptive_data else session.max_good_streak
            return session.outcome == "deal" and mg >= condition["min_good_streak"]

        elif ctype == "deal_after_mercy":
            mercy = adaptive_data.get("mercy_activated", False) if adaptive_data else session.mercy_activated
            return session.outcome == "deal" and mercy

        elif ctype == "deal_at_difficulty":
            return session.outcome == "deal" and session.difficulty >= condition["difficulty"]

        elif ctype == "score_at_difficulty":
            return (
                session.score_total >= condition["min_score"]
                and session.difficulty >= condition["difficulty"]
            )

        elif ctype == "reach_level":
            return profile.current_level >= condition["level"]

        elif ctype == "unique_archetypes_played":
            return _stats.get("unique_archetypes", 0) >= condition.get("count", 1)

        elif ctype == "unique_scenarios_played":
            return _stats.get("unique_scenarios", 0) >= condition.get("count", 1)

        elif ctype == "weekly_sessions":
            return _stats.get("weekly_sessions", 0) >= condition.get("count", 1)

        elif ctype == "daily_streak":
            return _stats.get("daily_streak", 0) >= condition.get("count", 1)

        return False

    # ──────────────────────────────────────────────────────────────────
    #  Weak points
    # ──────────────────────────────────────────────────────────────────

    def _update_weak_points(self, profile: ManagerProgress) -> None:
        skills = profile.skills_dict()
        avg = mean(skills.values())
        weak = [k for k, v in skills.items() if v < avg - WEAK_POINT_GAP]
        if not weak:
            weakest = min(skills, key=skills.get)
            weak = [weakest]
        profile.weak_points = weak

        # Focus recommendation
        focus = weak[0]
        names_ru = {
            "empathy": "эмпатию и слушание",
            "knowledge": "знание продукта (127-ФЗ)",
            "objection_handling": "работу с возражениями",
            "stress_resistance": "стрессоустойчивость",
            "closing": "закрытие сделки",
            "qualification": "квалификацию (сбор информации)",
        }
        profile.focus_recommendation = f"Рекомендуем потренировать: {names_ru.get(focus, focus)}"

    # ──────────────────────────────────────────────────────────────────
    #  DB helpers
    # ──────────────────────────────────────────────────────────────────

    async def _get_recent_sessions(
        self, user_id: uuid.UUID, limit: int = 10,
    ) -> list[SessionHistory]:
        result = await self._db.execute(
            select(SessionHistory)
            .where(SessionHistory.user_id == user_id)
            .order_by(SessionHistory.created_at.desc())
            .limit(limit),
        )
        return list(result.scalars().all())

    async def get_session_history(
        self, user_id: uuid.UUID, offset: int = 0, limit: int = 20,
    ) -> list[SessionHistory]:
        result = await self._db.execute(
            select(SessionHistory)
            .where(SessionHistory.user_id == user_id)
            .order_by(SessionHistory.created_at.desc())
            .offset(offset)
            .limit(limit),
        )
        return list(result.scalars().all())
