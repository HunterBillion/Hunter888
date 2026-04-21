"""Story Chapter Definitions — 'Путь Охотника' narrative arc.

4 Epochs, 12 Chapters, 52 weeks.
This is the PERMANENT progression per user (unlike ContentSeason which rotates quarterly).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class StoryEpoch:
    id: int
    code: str
    name: str
    tagline: str
    months: tuple[int, int]        # (start_month, end_month)
    chapters: tuple[int, ...]      # chapter ids in this epoch
    levels: tuple[int, int]        # (min_level, max_level)


@dataclass(frozen=True)
class StoryChapter:
    id: int                        # 1-12
    epoch: int                     # 1-4
    code: str                      # unique slug
    name: str                      # display name
    narrative_intro: str           # opening text
    unlock_level: int              # min ManagerProgress.current_level
    unlock_score_threshold: int    # min avg score in chapter to advance
    unlock_sessions: int           # min sessions completed in chapter
    unlocked_archetypes: list[str] = field(default_factory=list)
    unlocked_scenarios: list[str] = field(default_factory=list)
    unlocked_features: list[str] = field(default_factory=list)
    max_difficulty: int = 3
    weeks: tuple[int, int] = (1, 4)
    narrative_trigger: str | None = None   # shown on chapter completion


# ═══════════════════════════════════════════════════════════════════════════
# 4 Epochs
# ═══════════════════════════════════════════════════════════════════════════

EPOCHS: dict[int, StoryEpoch] = {
    1: StoryEpoch(
        id=1, code="first_calls", name="ПЕРВЫЕ ЗВОНКИ",
        tagline="Ты только что пришёл. Телефон тяжёлый. Голос дрожит. Но ты набираешь номер.",
        months=(1, 3), chapters=(1, 2, 3), levels=(1, 5),
    ),
    2: StoryEpoch(
        id=2, code="mastery", name="МАСТЕРСТВО",
        tagline="Ты уже не боишься. Теперь — учись слышать то, что не говорят.",
        months=(3, 6), chapters=(4, 5, 6), levels=(6, 10),
    ),
    3: StoryEpoch(
        id=3, code="mentor", name="НАСТАВНИК",
        tagline="Ты уже можешь закрыть любую сделку. Вопрос: можешь ли ты научить другого?",
        months=(6, 9), chapters=(7, 8, 9), levels=(11, 15),
    ),
    4: StoryEpoch(
        id=4, code="legend", name="ЛЕГЕНДА",
        tagline="Ты стал тем, кого боятся. Не клиенты — они уважают. Боятся конкуренты.",
        months=(9, 12), chapters=(10, 11, 12), levels=(16, 20),
    ),
}


# ═══════════════════════════════════════════════════════════════════════════
# 12 Chapters
# ═══════════════════════════════════════════════════════════════════════════

CHAPTERS: dict[int, StoryChapter] = {
    # ── ЭПОХА I: ПЕРВЫЕ ЗВОНКИ ─────────────────────────────────────────

    1: StoryChapter(
        id=1, epoch=1, code="first_number",
        name="Первый номер",
        narrative_intro=(
            "Ты только что пришёл в компанию. Наставник объясняет основы. "
            "Первый звонок — тёплый лид, который уже интересуется. "
            "Задача: не облажаться."
        ),
        unlock_level=1,
        unlock_score_threshold=0,
        unlock_sessions=0,
        unlocked_archetypes=["anxious", "passive", "concrete"],
        unlocked_scenarios=["in_website", "cold_ad", "warm_callback"],
        max_difficulty=3,
        weeks=(1, 4),
        narrative_trigger=None,
    ),

    2: StoryChapter(
        id=2, epoch=1, code="first_rejection",
        name="Первый отказ",
        narrative_intro=(
            "Первые холодные звонки. Люди бросают трубку. "
            "Наставник говорит: 'Это нормально. 7 из 10 — отказ. "
            "Важно — как ты реагируешь.' Первые ловушки."
        ),
        unlock_level=3,
        unlock_score_threshold=40,
        unlock_sessions=5,
        unlocked_archetypes=["procrastinator", "pragmatic"],
        unlocked_scenarios=["cold_base", "cold_referral"],
        unlocked_features=["daily_drill", "traps_level_1"],
        max_difficulty=4,
        weeks=(5, 8),
        narrative_trigger="Ты выдержал первые отказы. Это уже больше, чем многие.",
    ),

    3: StoryChapter(
        id=3, epoch=1, code="first_deal",
        name="Первая сделка",
        narrative_intro=(
            "Кульминация эпохи. Сложный клиент, долгий разговор. "
            "Ты должен применить всё, чему научился. "
            "Score >70 — 'сделка закрыта'."
        ),
        unlock_level=5,
        unlock_score_threshold=50,
        unlock_sessions=8,
        unlocked_archetypes=["skeptic"],
        unlocked_scenarios=["warm_noanswer", "in_hotline"],
        unlocked_features=["pvp_arena"],
        max_difficulty=5,
        weeks=(9, 12),
        narrative_trigger=(
            "Месяц назад ты боялся набрать номер. Сейчас — ты закрыл первую сделку. "
            "Ты вырос. Цифры подтверждают."
        ),
    ),

    # ── ЭПОХА II: МАСТЕРСТВО ───────────────────────────────────────────

    4: StoryChapter(
        id=4, epoch=2, code="manipulator",
        name="Манипулятор",
        narrative_intro=(
            "Появляются клиенты, которые врут, давят на жалость, угрожают. "
            "Наставник: 'Не верь словам. Верь паттернам.' "
            "Ты учишься распознавать ловушки."
        ),
        unlock_level=6,
        unlock_score_threshold=55,
        unlock_sessions=10,
        unlocked_archetypes=["sarcastic", "aggressive", "blamer", "stubborn"],
        unlocked_scenarios=["cold_competitor", "warm_referred", "follow_up_promise"],
        unlocked_features=["traps_level_2", "traps_level_3"],
        max_difficulty=7,
        weeks=(13, 20),
        narrative_trigger="Ты научился видеть сквозь маски. Манипуляторы больше не страшны.",
    ),

    5: StoryChapter(
        id=5, epoch=2, code="arena",
        name="Арена",
        narrative_intro=(
            "Ты вступаешь в PvP. Первые дуэли, первые поражения от более опытных. "
            "Наставник: 'Лучший учитель — тот, кто лучше тебя.'"
        ),
        unlock_level=8,
        unlock_score_threshold=60,
        unlock_sessions=12,
        unlocked_archetypes=[],
        unlocked_scenarios=["crisis_threat_court", "crisis_media_threat"],
        unlocked_features=["pvp_ranked", "tournaments", "team_challenges", "arena_streak"],
        max_difficulty=8,
        weeks=(21, 24),
        narrative_trigger="Арена закалила тебя. Теперь ты знаешь свой уровень.",
    ),

    6: StoryChapter(
        id=6, epoch=2, code="crisis",
        name="Кризис",
        narrative_intro=(
            "Сюжетный поворот: серия сложнейших клиентов. "
            "Агрессор + юридическая ловушка + эмоциональный шантаж. "
            "Пройди 3 из 3 — и станешь 'антикризисным'."
        ),
        unlock_level=9,
        unlock_score_threshold=65,
        unlock_sessions=15,
        unlocked_archetypes=["hostile", "elderly_paranoid", "hysteric_litigious"],
        unlocked_scenarios=["crisis_claim_refund", "compliance_audit", "compliance_overdue"],
        unlocked_features=["all_archetypes"],
        max_difficulty=10,
        weeks=(25, 26),
        narrative_trigger=(
            "Инициация пройдена. Ты — Мастер. "
            "Доступ к наставничеству открыт. "
            "Короткий ролик: твой путь от первого звонка до кризиса."
        ),
    ),

    # ── ЭПОХА III: НАСТАВНИК ───────────────────────────────────────────

    7: StoryChapter(
        id=7, epoch=3, code="apprentice",
        name="Ученик",
        narrative_intro=(
            "Ты получаешь 'ученика' — AI-бот, который делает ошибки. "
            "Задача: не звонить самому, а АНАЛИЗИРОВАТЬ звонки ученика "
            "и давать feedback."
        ),
        unlock_level=11,
        unlock_score_threshold=65,
        unlock_sessions=18,
        unlocked_archetypes=["power_player", "strategist"],
        unlocked_scenarios=["multi_couple_disagreeing", "multi_family_pressure"],
        unlocked_features=["mentor_mode", "custom_scenarios"],
        max_difficulty=10,
        weeks=(27, 32),
        narrative_trigger="Ты учишь других. Это следующий уровень.",
    ),

    8: StoryChapter(
        id=8, epoch=3, code="special_ops",
        name="Спецоперация",
        narrative_intro=(
            "Командные миссии: 3-5 менеджеров vs AI. "
            "Каждый звонит своему клиенту, но клиенты связаны. "
            "Результат одного влияет на другого."
        ),
        unlock_level=13,
        unlock_score_threshold=68,
        unlock_sessions=20,
        unlocked_archetypes=[],
        unlocked_scenarios=["multi_business_partner", "multi_guarantor"],
        unlocked_features=["team_missions"],
        max_difficulty=10,
        weeks=(33, 38),
        narrative_trigger="Спецоперация завершена. Ты — командный игрок.",
    ),

    9: StoryChapter(
        id=9, epoch=3, code="commander",
        name="Командир",
        narrative_intro=(
            "Ты руководишь командой в турнире. "
            "Твоя задача — не играть, а распределять сценарии между игроками, "
            "выбирать стратегию."
        ),
        unlock_level=14,
        unlock_score_threshold=70,
        unlock_sessions=22,
        unlocked_archetypes=[],
        unlocked_scenarios=[],
        unlocked_features=["corp_tournaments", "create_tournaments"],
        max_difficulty=10,
        weeks=(39, 42),
        narrative_trigger=(
            "Досье сформировано. Полная статистика за 9 месяцев: "
            "каждая ловушка, каждый архетип, каждый PvP-матч. "
            "Визуализация роста."
        ),
    ),

    # ── ЭПОХА IV: ЛЕГЕНДА ─────────────────────────────────────────────

    10: StoryChapter(
        id=10, epoch=4, code="grandmaster",
        name="Гроссмейстер",
        narrative_intro=(
            "Сценарии на сложности 10/10 с комбинированными архетипами. "
            "AI-клиент адаптируется к твоему стилю в реальном времени."
        ),
        unlock_level=16,
        unlock_score_threshold=72,
        unlock_sessions=25,
        unlocked_archetypes=["puppet_master", "lawyer_client"],
        unlocked_scenarios=["crisis_media_threat", "compliance_regulator"],
        unlocked_features=["adaptive_ai", "legendary_achievements"],
        max_difficulty=10,
        weeks=(43, 46),
        narrative_trigger="Гроссмейстер. AI адаптируется к тебе — и всё равно проигрывает.",
    ),

    11: StoryChapter(
        id=11, epoch=4, code="methodologist",
        name="Методолог",
        narrative_intro=(
            "Ты создаёшь собственные архетипы и сценарии, "
            "которые попадают в пул для ДРУГИХ игроков. "
            "Твой контент оценивается community."
        ),
        unlock_level=18,
        unlock_score_threshold=75,
        unlock_sessions=28,
        unlocked_archetypes=[],
        unlocked_scenarios=[],
        unlocked_features=["archetype_creation", "community_content", "community_voting"],
        max_difficulty=10,
        weeks=(47, 50),
        narrative_trigger="Ты — Методолог. Твои сценарии тренируют других.",
    ),

    12: StoryChapter(
        id=12, epoch=4, code="hunter",
        name="Охотник",
        narrative_intro=(
            "Финальное испытание: марафон из 10 звонков подряд, "
            "каждый сложнее предыдущего. Рандомные архетипы, "
            "максимальная сложность. Score >80 на всех 10 = титул 'Охотник'."
        ),
        unlock_level=20,
        unlock_score_threshold=78,
        unlock_sessions=30,
        unlocked_archetypes=[],
        unlocked_scenarios=[],
        unlocked_features=["marathon", "hall_of_fame", "legendary_skin"],
        max_difficulty=10,
        weeks=(51, 52),
        narrative_trigger=(
            "Ты — Охотник. Титул получен. "
            "Место в Зале Славы. Вечный badge. "
            "Но история не заканчивается — начинаются сезоны."
        ),
    ),
}


def get_chapter(chapter_id: int) -> StoryChapter | None:
    return CHAPTERS.get(chapter_id)


def get_epoch(epoch_id: int) -> StoryEpoch | None:
    return EPOCHS.get(epoch_id)


def epoch_for_chapter(chapter_id: int) -> StoryEpoch | None:
    ch = CHAPTERS.get(chapter_id)
    if ch is None:
        return None
    return EPOCHS.get(ch.epoch)


def cumulative_unlocked_archetypes(up_to_chapter: int) -> list[str]:
    """All archetypes unlocked from chapter 1 through up_to_chapter."""
    result: list[str] = []
    for cid in range(1, up_to_chapter + 1):
        ch = CHAPTERS.get(cid)
        if ch:
            result.extend(ch.unlocked_archetypes)
    return result


def cumulative_unlocked_scenarios(up_to_chapter: int) -> list[str]:
    """All scenarios unlocked from chapter 1 through up_to_chapter."""
    result: list[str] = []
    for cid in range(1, up_to_chapter + 1):
        ch = CHAPTERS.get(cid)
        if ch:
            result.extend(ch.unlocked_scenarios)
    return result


def cumulative_unlocked_features(up_to_chapter: int) -> list[str]:
    """All features unlocked from chapter 1 through up_to_chapter."""
    result: list[str] = []
    for cid in range(1, up_to_chapter + 1):
        ch = CHAPTERS.get(cid)
        if ch:
            result.extend(ch.unlocked_features)
    return result


def max_difficulty_for_chapter(chapter_id: int) -> int:
    ch = CHAPTERS.get(chapter_id)
    return ch.max_difficulty if ch else 3
