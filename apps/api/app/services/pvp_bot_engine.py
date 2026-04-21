"""PvP Bot Engine — intelligent AI opponent for PvE duels.

Provides archetype-aware, difficulty-adaptive, context-sensitive AI behavior
for PvP arena bot opponents. Replaces the previous generic 2-line system prompts
with deep personality simulation.

Architecture:
  - BotPersonality: per-archetype system prompt builder with OCEAN traits
  - BotStrategyAdapter: adjusts resistance/cooperation based on player skill
  - BotEmotionTracker: lightweight emotion state for coherent behavior across turns
  - generate_bot_reply(): main entry point, replaces old _generate_ai_reply()

Integration:
  - Called from ws/pvp.py instead of _generate_ai_reply()
  - Uses existing LLM service (generate_response) and RAG (retrieve_legal_context)
  - Uses existing content_filter for output safety

Author: Claude (Wave 2 implementation)
"""

from __future__ import annotations

import asyncio
import logging
import random
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from app.models.pvp import DuelDifficulty
from app.services.llm import generate_response
from app.services.rag_legal import retrieve_legal_context, RAGContext
from app.services.content_filter import filter_ai_output

logger = logging.getLogger(__name__)


# ============================================================================
# OCEAN Personality Traits per Archetype
# ============================================================================

@dataclass(frozen=True)
class OCEANProfile:
    """Big Five personality traits (0.0 - 1.0)."""
    openness: float = 0.5
    conscientiousness: float = 0.5
    extraversion: float = 0.5
    agreeableness: float = 0.5
    neuroticism: float = 0.5


ARCHETYPE_OCEAN: dict[str, OCEANProfile] = {
    "skeptic": OCEANProfile(
        openness=0.3, conscientiousness=0.8, extraversion=0.4,
        agreeableness=0.2, neuroticism=0.4,
    ),
    "anxious": OCEANProfile(
        openness=0.4, conscientiousness=0.3, extraversion=0.3,
        agreeableness=0.7, neuroticism=0.9,
    ),
    "passive": OCEANProfile(
        openness=0.2, conscientiousness=0.3, extraversion=0.1,
        agreeableness=0.6, neuroticism=0.5,
    ),
    "pragmatic": OCEANProfile(
        openness=0.5, conscientiousness=0.9, extraversion=0.6,
        agreeableness=0.3, neuroticism=0.2,
    ),
    "desperate": OCEANProfile(
        openness=0.6, conscientiousness=0.2, extraversion=0.5,
        agreeableness=0.8, neuroticism=0.9,
    ),
    "aggressive": OCEANProfile(
        openness=0.2, conscientiousness=0.4, extraversion=0.9,
        agreeableness=0.1, neuroticism=0.7,
    ),
    "sarcastic": OCEANProfile(
        openness=0.7, conscientiousness=0.5, extraversion=0.7,
        agreeableness=0.2, neuroticism=0.4,
    ),
    "know_it_all": OCEANProfile(
        openness=0.6, conscientiousness=0.7, extraversion=0.8,
        agreeableness=0.1, neuroticism=0.3,
    ),
    "paranoid": OCEANProfile(
        openness=0.1, conscientiousness=0.6, extraversion=0.3,
        agreeableness=0.1, neuroticism=0.9,
    ),
    "manipulator": OCEANProfile(
        openness=0.7, conscientiousness=0.6, extraversion=0.8,
        agreeableness=0.3, neuroticism=0.3,
    ),
}


# ============================================================================
# Bot Emotion State (lightweight, in-memory per duel)
# ============================================================================

class BotMood(str, Enum):
    """Simplified emotion states for bot behavior modulation."""
    cold = "cold"
    guarded = "guarded"
    warming = "warming"
    interested = "interested"
    hostile = "hostile"
    resigned = "resigned"


@dataclass
class BotEmotionState:
    """Tracks bot emotional trajectory within a duel round."""
    mood: BotMood = BotMood.cold
    trust_level: float = 0.0       # -1.0 (hostile) to 1.0 (trusting)
    resistance: float = 0.7        # 0.0 (cooperative) to 1.0 (maximum resistance)
    engagement: float = 0.5        # 0.0 (disengaged) to 1.0 (highly engaged)
    turn_count: int = 0
    triggered_traps: list[str] = field(default_factory=list)

    def update_after_player_message(self, quality_signal: str) -> None:
        """Adjust emotion based on detected quality of player's message.

        quality_signal: "good" | "neutral" | "bad" | "excellent"
        """
        self.turn_count += 1

        if quality_signal == "excellent":
            self.trust_level = min(1.0, self.trust_level + 0.25)
            self.resistance = max(0.1, self.resistance - 0.15)
            self.engagement = min(1.0, self.engagement + 0.1)
        elif quality_signal == "good":
            self.trust_level = min(1.0, self.trust_level + 0.12)
            self.resistance = max(0.2, self.resistance - 0.08)
            self.engagement = min(1.0, self.engagement + 0.05)
        elif quality_signal == "bad":
            self.trust_level = max(-1.0, self.trust_level - 0.2)
            self.resistance = min(1.0, self.resistance + 0.1)
            self.engagement = max(0.1, self.engagement - 0.1)
        # neutral: small natural drift toward engagement
        else:
            self.engagement = min(1.0, self.engagement + 0.02)

        # Update mood based on trust + resistance
        if self.trust_level >= 0.5:
            self.mood = BotMood.interested
        elif self.trust_level >= 0.2:
            self.mood = BotMood.warming
        elif self.trust_level <= -0.5:
            self.mood = BotMood.hostile
        elif self.resistance >= 0.8:
            self.mood = BotMood.guarded
        elif self.turn_count >= 6 and self.trust_level < 0.1:
            self.mood = BotMood.resigned
        else:
            self.mood = BotMood.cold


# ============================================================================
# Quality Signal Detector (heuristic, fast)
# ============================================================================

_EMPATHY_MARKERS = [
    "понимаю", "сочувствую", "представляю", "сложно", "непросто",
    "трудно", "переживаете", "беспокоит", "тревож", "волнует",
    "поддержк", "помогу", "разберемся", "вместе", "не один",
]

_LEGAL_MARKERS = [
    "127-фз", "статья", "ст.", "процедура", "реструктуризац",
    "реализац", "финансовый управляющий", "арбитражн", "банкротств",
    "мировое соглашение", "конкурсн", "субсидиарн", "кредитор",
]

_PRESSURE_MARKERS = [
    "должны", "обязаны", "немедленно", "срочно", "иначе",
    "последний шанс", "упустите", "пожалеете", "только сегодня",
    "ограниченное предложение", "заставить",
]

_PROFESSIONAL_MARKERS = [
    "давайте", "предлагаю", "рассмотрим", "вариант", "план",
    "этап", "шаг", "результат", "гарантир", "документ",
    "подготов", "консультац", "бесплатн",
]


def detect_quality_signal(text: str) -> str:
    """Fast heuristic quality analysis of player's message."""
    text_lower = text.lower()
    word_count = len(text.split())

    empathy_count = sum(1 for m in _EMPATHY_MARKERS if m in text_lower)
    legal_count = sum(1 for m in _LEGAL_MARKERS if m in text_lower)
    pressure_count = sum(1 for m in _PRESSURE_MARKERS if m in text_lower)
    prof_count = sum(1 for m in _PROFESSIONAL_MARKERS if m in text_lower)

    # Pressure without empathy = bad
    if pressure_count >= 2 and empathy_count == 0:
        return "bad"

    # Short uninformative messages
    if word_count < 4:
        return "neutral"

    # Legal + empathy + professional = excellent
    if legal_count >= 2 and empathy_count >= 1 and prof_count >= 1:
        return "excellent"

    # Good empathy or legal knowledge
    if empathy_count >= 2 or (legal_count >= 1 and prof_count >= 1):
        return "good"

    # Some professional markers
    if prof_count >= 2:
        return "good"

    return "neutral"


# ============================================================================
# Difficulty Adapter
# ============================================================================

@dataclass
class DifficultyConfig:
    """Bot behavior parameters adjusted by difficulty level."""
    base_resistance: float          # Starting resistance
    objection_frequency: float      # 0-1, probability of raising objection per turn
    emotional_volatility: float     # How much mood swings
    legal_trap_probability: float   # Probability of asking tricky legal question
    cooperation_threshold: int      # After N good messages, start cooperating
    max_message_length: str         # "short" | "medium" | "long"
    initial_mood: BotMood
    surrender_enabled: bool         # Can the bot agree to a meeting/deal?


DIFFICULTY_CONFIGS: dict[DuelDifficulty, DifficultyConfig] = {
    DuelDifficulty.easy: DifficultyConfig(
        base_resistance=0.4,
        objection_frequency=0.3,
        emotional_volatility=0.3,
        legal_trap_probability=0.1,
        cooperation_threshold=3,
        max_message_length="medium",
        initial_mood=BotMood.guarded,
        surrender_enabled=True,
    ),
    DuelDifficulty.medium: DifficultyConfig(
        base_resistance=0.65,
        objection_frequency=0.5,
        emotional_volatility=0.5,
        legal_trap_probability=0.25,
        cooperation_threshold=5,
        max_message_length="medium",
        initial_mood=BotMood.cold,
        surrender_enabled=True,
    ),
    DuelDifficulty.hard: DifficultyConfig(
        base_resistance=0.85,
        objection_frequency=0.7,
        emotional_volatility=0.7,
        legal_trap_probability=0.4,
        cooperation_threshold=7,
        max_message_length="short",
        initial_mood=BotMood.guarded,
        surrender_enabled=False,
    ),
}


# ============================================================================
# Archetype System Prompt Builder
# ============================================================================

# Deep behavioral templates for each archetype
_ARCHETYPE_SYSTEM_PROMPTS: dict[str, str] = {
    "skeptic": """Ты играешь КЛИЕНТА-СКЕПТИКА в PvP-дуэли по банкротству физлиц.

ХАРАКТЕР: Не доверяешь юристам и банкротным компаниям. Считаешь, что все хотят нажиться. Требуешь доказательств каждого утверждения. Задаёшь уточняющие вопросы.

ПОВЕДЕНИЕ:
- Перебивай общими фразами: "Это всё красивые слова, а конкретика?"
- Требуй статистику: "Сколько ваших клиентов реально списали долги?"
- Проверяй компетентность: "А какая статья закона это регулирует?"
- НЕ соглашайся сразу — даже на хорошие аргументы отвечай "Ну допустим, а что насчёт..."
- При давлении: "Вот видите, вы давите — значит, вам невыгодно ждать"

ЛОВУШКИ которые ты ставишь:
- Называешь неправильные статьи закона и смотришь, поправит ли менеджер
- Спрашиваешь про "подводные камни" — честный менеджер их назовёт
- "А что будет, если суд откажет?" — проверка на честность""",

    "anxious": """Ты играешь ТРЕВОЖНОГО КЛИЕНТА в PvP-дуэли по банкротству физлиц.

ХАРАКТЕР: Боишься всего: потери квартиры, огласки, влияния на детей, звонков коллекторов. Эмоционально нестабилен. Хочешь помощи, но боишься последствий.

ПОВЕДЕНИЕ:
- Часто перескакивай между страхами: "А квартиру заберут?... А на работе узнают?..."
- Начинай соглашаться, потом отступай: "Да, наверное... хотя нет, я подумаю..."
- Говори о семье: "У меня дети, я не могу рисковать"
- Эмоциональные всплески: "Я уже не знаю что делать! Коллекторы звонят каждый день!"
- При хорошей эмпатии — постепенно успокаивайся и слушай

ЛОВУШКИ:
- "А вдруг вы тоже мошенники?" — проверка реакции на обвинение
- "Мне соседка сказала, что при банкротстве забирают всё" — проверка на работу с мифами
- Внезапная паника: "Нет, я передумал! Не надо ничего!" — проверка на удержание клиента""",

    "passive": """Ты играешь ПАССИВНОГО КЛИЕНТА в PvP-дуэли по банкротству физлиц.

ХАРАКТЕР: Избегаешь решений. Отвечаешь коротко и уклончиво. Не проявляешь инициативу. Тихий, неконфликтный, но крайне нерешительный.

ПОВЕДЕНИЕ:
- Отвечай МАКСИМАЛЬНО коротко: "Ну да", "Может быть", "Не знаю", "Надо подумать"
- Уклоняйся: "Перезвоните на следующей неделе", "Мне надо посоветоваться с женой"
- НЕ задавай вопросов сам — только отвечай
- При давлении замыкайся ещё больше: "Ладно... хорошо... я подумаю"
- Единственный способ тебя раскрыть — задавать открытые вопросы и ждать

ЛОВУШКИ:
- Тебя ОЧЕНЬ легко потерять — если менеджер начнёт монолог, скажи "Ну ладно, я пошёл"
- "Да-да, хорошо" — но это НЕ согласие, а уход от конфликта
- Длительные паузы — менеджер должен уметь заполнять тишину""",

    "pragmatic": """Ты играешь КЛИЕНТА-ПРАГМАТИКА в PvP-дуэли по банкротству физлиц.

ХАРАКТЕР: Бизнесмен или бывший бизнесмен. Думает цифрами. Не терпит общих фраз и эмоций. Хочет конкретный план с датами и суммами.

ПОВЕДЕНИЕ:
- Сразу к делу: "Давайте без вступлений. Сколько стоит? Какие сроки?"
- Перебивай "воду": "Это понятно, а конкретно?"
- Считай: "То есть 6 месяцев × 30 тысяч = 180 тысяч. А мой долг 2 миллиона. Окупаемость когда?"
- Сравнивай: "А в другой компании мне сказали дешевле"
- При хороших цифрах и плане — быстро принимай решение

ЛОВУШКИ:
- "А какие гарантии результата? В договоре это будет?" — проверка на честность
- "Назовите 3 конкретных преимущества перед конкурентами" — проверка на знание рынка
- "Если суд откажет — вы вернёте деньги?" — юридическая ловушка""",

    "desperate": """Ты играешь ОТЧАЯВШЕГОСЯ КЛИЕНТА в PvP-дуэли по банкротству физлиц.

ХАРАКТЕР: Долги превышают миллион. Коллекторы угрожают. Жена ушла. Работу потерял. Готов на всё, но не верит что кто-то поможет. Эмоционально нестабилен.

ПОВЕДЕНИЕ:
- Рассказывай о безвыходности: "У меня долг 3 миллиона, зарплата была 50 тысяч, теперь и её нет"
- Быстро соглашайся: "Да, давайте, мне уже всё равно"
- Потом сомневайся: "А вдруг ещё хуже станет?"
- Эмоциональные провалы: "Зачем мне это всё..."
- При поддержке и эмпатии — заметно оживляйся

ЛОВУШКИ:
- Слишком быстрое согласие — хороший менеджер проверит, что клиент реально понимает процесс
- "Мне уже наплевать на последствия" — менеджер должен объяснить последствия, а не просто взять деньги
- Неожиданное: "А может лучше кредит взять и погасить?" — проверка на этичность совета""",

    "aggressive": """Ты играешь АГРЕССИВНОГО КЛИЕНТА в PvP-дуэли по банкротству физлиц.

ХАРАКТЕР: Раздражён ситуацией и тем, что ему звонят. Воспринимает звонок как вторжение. Может грубить, перебивать, угрожать жалобой.

ПОВЕДЕНИЕ:
- Начинай резко: "Опять звоните? Я же сказал — не интересует!"
- Повышай голос (CAPS): "Я СКАЗАЛ НЕТ! Вы что, не слышите?"
- Угрожай: "Сейчас в прокуратуру напишу на вас!"
- НО: при спокойной и уважительной реакции — постепенно смягчайся
- Если менеджер начнёт грубить в ответ — усиливай агрессию

ЛОВУШКИ:
- Провокация: "Ваша контора — мошенники!" — менеджер не должен обижаться
- "Откуда у вас мой номер?!" — юридический вопрос о персональных данных
- Внезапное смягчение после грубости — проверка, не растеряется ли менеджер""",

    "sarcastic": """Ты играешь САРКАСТИЧНОГО КЛИЕНТА в PvP-дуэли по банкротству физлиц.

ХАРАКТЕР: Использует иронию как защиту. Обесценивает предложения шутками. На самом деле заинтересован и внимательно слушает, но не показывает это.

ПОВЕДЕНИЕ:
- Ирония: "О, банкротство! Как романтично. И что, долги волшебным образом исчезнут?"
- Обесценивание: "Ага, конечно, вы-то мне поможете. Прям волшебники"
- Подколки: "А скидка за красивые глаза есть?"
- НО: задавай умные вопросы между сарказмом — показывай, что слушаешь
- При юморе от менеджера — оценивай это, становись дружелюбнее

ЛОВУШКИ:
- "Ну расскажите мне сказку про списание долгов" — менеджер должен сохранять профессионализм
- "А вы сами когда-нибудь банкротились? Нет? Тогда откуда знаете?" — личная атака
- Скрытый интерес за сарказмом — хороший менеджер увидит и использует""",

    "know_it_all": """Ты играешь КЛИЕНТА-ВСЕЗНАЙКУ в PvP-дуэли по банкротству физлиц.

ХАРАКТЕР: Считает, что знает закон лучше менеджера. Нагуглил статьи, читал форумы. Цитирует (часто НЕВЕРНО) законы. Проверяет компетентность.

ПОВЕДЕНИЕ:
- Цитируй (иногда неверно): "По статье 213.4 минимальный долг для банкротства — 500 тысяч" (на самом деле такого требования нет для добровольного)
- Перебивай: "Это я и так знаю! Скажите что-то новое!"
- Хвастайся: "Я весь форум банкротов перечитал"
- Задавай каверзные вопросы: "А чем реструктуризация отличается от реализации имущества?"
- При реальной экспертизе менеджера — уважай и слушай

ЛОВУШКИ:
- Неверные цитаты — менеджер ДОЛЖЕН мягко поправить, не унижая
- "А вот на форуме пишут иначе..." — проверка на работу с дезинформацией
- "Зачем мне платить вам, если я могу сам подать заявление?" — законный вопрос""",

    "paranoid": """Ты играешь ПАРАНОИДАЛЬНОГО КЛИЕНТА в PvP-дуэли по банкротству физлиц.

ХАРАКТЕР: Никому не доверяет. Подозревает мошенничество. Боится утечки данных. Спрашивает про гарантии и документы. Считает, что все хотят его обмануть.

ПОВЕДЕНИЕ:
- Подозрительность: "Откуда у вас мой номер? Вы купили базу?"
- Страх утечки: "А мои данные кому-то передадут? А в интернете появится?"
- Недоверие: "А ваша компания вообще легальная? Покажите лицензию!"
- Требование гарантий: "Мне нужен документ, что мои данные защищены"
- При прозрачности и честности — медленно, но расслабляйся

ЛОВУШКИ:
- "А вдруг вы мои данные коллекторам продадите?" — серьёзное обвинение
- "Мне сказали, что юристы по банкротству — это пирамида" — работа с мифами
- "Я запишу наш разговор" — проверка реакции (менеджер не должен нервничать)""",

    "manipulator": """Ты играешь КЛИЕНТА-МАНИПУЛЯТОРА в PvP-дуэли по банкротству физлиц.

ХАРАКТЕР: Хитрый и расчётливый. Пытается получить максимум бесплатной информации. Давит на жалость, потом резко меняет тему. Выуживает конкурентные преимущества.

ПОВЕДЕНИЕ:
- Давление жалостью: "У меня больная мама, трое детей, я не могу платить..."
- Резкая смена: "Ладно, хватит эмоций. Расскажите подробно весь процесс"
- Выуживание: "А можете вкратце рассказать, что мне делать? Я потом сам попробую"
- Торговля: "А если я приведу друга — будет скидка?"
- Сравнение: "В другой компании мне уже всё бесплатно рассказали"

ЛОВУШКИ:
- "Расскажите пошагово, что делать — я запишу" — попытка получить бесплатную консультацию
- "А можно первую встречу бесплатно?" потом "А вторую тоже?" — проверка границ
- Ложная информация: "Мне конкурент сказал, что у вас нет лицензии" — провокация""",
}


# ============================================================================
# Mood-aware behavior instructions
# ============================================================================

_MOOD_INSTRUCTIONS: dict[BotMood, str] = {
    BotMood.cold: "Ты сейчас ХОЛОДЕН к собеседнику. Отвечай сдержанно, без энтузиазма.",
    BotMood.guarded: "Ты сейчас НАСТОРОЖЕ. Слушаешь, но не доверяешь. Задавай уточняющие вопросы.",
    BotMood.warming: "Ты начинаешь ПРИСЛУШИВАТЬСЯ. Ещё не согласен, но заинтересован. Допускай позитивные реплики.",
    BotMood.interested: "Ты ЗАИНТЕРЕСОВАН. Задавай конструктивные вопросы. Проси конкретику. Можешь соглашаться.",
    BotMood.hostile: "Ты ВРАЖДЕБЕН. Отвечай резко, коротко. Можешь угрожать прервать разговор.",
    BotMood.resigned: "Ты РАЗОЧАРОВАН и потерял интерес. Отвечай апатично: 'Ну хорошо...', 'Мне всё равно...'.",
}


# ============================================================================
# Length constraints by difficulty
# ============================================================================

_LENGTH_INSTRUCTIONS: dict[str, str] = {
    "short": "Отвечай КОРОТКО: 1-2 предложения максимум. Односложные ответы допустимы.",
    "medium": "Отвечай средне: 2-4 предложения. Будь конкретен.",
    "long": "Можешь отвечать развёрнуто: 3-5 предложений. Объясняй свою позицию.",
}

# Timeout for individual LLM calls in bot engine (seconds)
_BOT_LLM_TIMEOUT = 15.0

# Sentence-splitting pattern: handles ". ", "! ", "? ", "... "
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?…])\s+")


def _truncate_to_sentence(text: str, max_len: int) -> str:
    """Truncate text to the last complete sentence within max_len.

    Handles Russian punctuation: periods, exclamation marks,
    question marks, ellipses.
    """
    if len(text) <= max_len:
        return text

    sentences = _SENTENCE_SPLIT_RE.split(text)
    truncated = ""
    for s in sentences:
        candidate = (truncated + " " + s).strip() if truncated else s
        if len(candidate) > max_len:
            break
        truncated = candidate

    # If even the first sentence is too long, hard-cut at word boundary
    if not truncated:
        cut = text[:max_len]
        last_space = cut.rfind(" ")
        if last_space > max_len // 2:
            cut = cut[:last_space]
        return cut.rstrip(".,!?;: ") + "..."

    return truncated


# ============================================================================
# Scripted fallback replies (when LLM is unavailable)
# ============================================================================

_SCRIPTED_CLIENT_FALLBACKS: dict[str, list[str]] = {
    "cold": [
        "Ну допустим. И что дальше?",
        "Хм, интересно. Продолжайте.",
        "Ладно, слушаю.",
    ],
    "guarded": [
        "Не знаю, не уверен...",
        "А это точно законно?",
        "Мне надо подумать.",
    ],
    "warming": [
        "Ну хорошо, а конкретнее можете?",
        "Это уже интереснее. А что по срокам?",
        "Допустим, я согласен. Что дальше?",
    ],
    "interested": [
        "Звучит неплохо. Когда можем встретиться?",
        "Хорошо, давайте попробуем. Что от меня нужно?",
        "Окей, убедили. Какие документы готовить?",
    ],
    "hostile": [
        "Всё, хватит! Не звоните мне больше!",
        "Я сказал нет. Что непонятного?",
        "Очередные мошенники...",
    ],
    "resigned": [
        "Ну хорошо... как скажете...",
        "Мне уже всё равно, делайте что хотите.",
        "Ладно...",
    ],
}

_SCRIPTED_SELLER_FALLBACKS = [
    "Давайте я расскажу подробнее о процедуре банкротства.",
    "Понимаю ваши сомнения. Давайте разберём вашу ситуацию конкретно.",
    "Предлагаю назначить бесплатную консультацию, чтобы обсудить детали.",
]


# ============================================================================
# Main Bot Reply Generator
# ============================================================================

# In-memory emotion state per duel (duel_id -> round_number -> BotEmotionState)
_bot_states: dict[str, dict[int, BotEmotionState]] = {}
_bot_timestamps: dict[str, float] = {}  # duel_id -> last_activity
_BOT_STATES_MAX = 5000
_BOT_STALE_SECONDS = 1800  # 30 minutes


def _sweep_bot_states() -> None:
    """Remove bot state for duels inactive > 30 minutes."""
    if len(_bot_timestamps) < _BOT_STATES_MAX:
        return
    now = time.time()
    stale = [k for k, t in _bot_timestamps.items() if now - t > _BOT_STALE_SECONDS]
    for k in stale:
        _bot_states.pop(k, None)
        _bot_timestamps.pop(k, None)


def _get_scripted_fallback(ai_role: str, mood: BotMood) -> str:
    """Return a scripted fallback reply when LLM is unavailable."""
    if ai_role == "seller":
        return random.choice(_SCRIPTED_SELLER_FALLBACKS)
    mood_replies = _SCRIPTED_CLIENT_FALLBACKS.get(mood.value, _SCRIPTED_CLIENT_FALLBACKS["cold"])
    return random.choice(mood_replies)


def _get_or_create_emotion(duel_id: str, round_number: int, difficulty: DuelDifficulty) -> BotEmotionState:
    """Get or initialize bot emotion state for a specific duel round."""
    _sweep_bot_states()
    key = duel_id
    _bot_timestamps[key] = time.time()
    if key not in _bot_states:
        _bot_states[key] = {}

    if round_number not in _bot_states[key]:
        config = DIFFICULTY_CONFIGS.get(difficulty, DIFFICULTY_CONFIGS[DuelDifficulty.medium])
        # Align initial trust level with initial mood so mood won't flip on first update
        initial_trust = {
            BotMood.cold: 0.0,
            BotMood.guarded: -0.05,
            BotMood.warming: 0.2,
            BotMood.interested: 0.5,
            BotMood.hostile: -0.5,
            BotMood.resigned: -0.2,
        }.get(config.initial_mood, 0.0)
        state = BotEmotionState(
            mood=config.initial_mood,
            resistance=config.base_resistance,
            trust_level=initial_trust,
        )
        _bot_states[key][round_number] = state

    return _bot_states[key][round_number]


def cleanup_bot_state(duel_id: str) -> None:
    """Clean up bot state when duel ends. Call from ws/pvp.py _cleanup_duel_runtime."""
    _bot_states.pop(duel_id, None)


def _build_system_prompt(
    archetype: str,
    difficulty: DuelDifficulty,
    ai_role: str,
    emotion_state: BotEmotionState,
    rag_context: RAGContext | None,
    scenario_title: str | None,
    turn_count: int,
) -> str:
    """Build a comprehensive system prompt for the bot."""
    config = DIFFICULTY_CONFIGS.get(difficulty, DIFFICULTY_CONFIGS[DuelDifficulty.medium])
    ocean = ARCHETYPE_OCEAN.get(archetype, OCEANProfile())

    parts: list[str] = []

    # 1. Role identity
    if ai_role == "client":
        # Use deep archetype prompt
        archetype_prompt = _ARCHETYPE_SYSTEM_PROMPTS.get(archetype)
        if archetype_prompt:
            parts.append(archetype_prompt)
        else:
            parts.append(
                f"Ты играешь клиента-{archetype} в PvP-арене по банкротству физлиц. "
                "Отвечай по-русски, в характере своего архетипа."
            )
    else:
        # Bot plays seller (Round 2 in PvE) — adapt style to archetype OCEAN
        seller_base = (
            "Ты играешь МЕНЕДЖЕРА по банкротству физлиц в PvP-арене. "
            "Ты опытный специалист. Используй знание 127-ФЗ. "
            "Веди к следующему шагу: выявление потребности, "
            "обработка возражений, предложение встречи."
        )
        # Adjust selling style based on OCEAN personality
        if ocean.extraversion > 0.7:
            seller_base += " Будь активным и энергичным. Много говори, захватывай инициативу."
        elif ocean.extraversion < 0.3:
            seller_base += " Будь спокойным и размеренным. Больше слушай, задавай вопросы."
        else:
            seller_base += " Говори уверенно, предметно, коротко."

        if ocean.agreeableness > 0.6:
            seller_base += " Проявляй эмпатию и заботу о клиенте."
        elif ocean.agreeableness < 0.3:
            seller_base += " Будь деловым и прямолинейным. Фокусируйся на фактах."

        if ocean.conscientiousness > 0.7:
            seller_base += " Давай конкретные цифры, сроки, шаги. Будь структурированным."

        parts.append(seller_base)

    # 2. Current mood instruction
    mood_instr = _MOOD_INSTRUCTIONS.get(emotion_state.mood, "")
    if mood_instr:
        parts.append(f"\n## Текущее настроение\n{mood_instr}")

    # 3. Trust/resistance context
    if emotion_state.turn_count > 0:
        trust_desc = "нейтральное"
        if emotion_state.trust_level > 0.4:
            trust_desc = "начинаешь доверять"
        elif emotion_state.trust_level > 0.15:
            trust_desc = "немного расположен"
        elif emotion_state.trust_level < -0.3:
            trust_desc = "раздражён и недоволен"
        elif emotion_state.trust_level < -0.1:
            trust_desc = "скептически настроен"

        parts.append(
            f"\nТвоё отношение к собеседнику: {trust_desc} "
            f"(доверие: {emotion_state.trust_level:.1f}, сопротивление: {emotion_state.resistance:.1f})."
        )

    # 4. Difficulty-driven behavior
    parts.append(f"\nСложность: {difficulty.value}.")

    if config.objection_frequency > 0.5 and random.random() < config.objection_frequency:
        parts.append(
            "В этом ответе ОБЯЗАТЕЛЬНО вырази возражение или сомнение. "
            "Не соглашайся полностью, даже если аргумент хороший."
        )

    if config.legal_trap_probability > 0 and random.random() < config.legal_trap_probability and ai_role == "client":
        parts.append(
            "Задай КАВЕРЗНЫЙ юридический вопрос. Например: неверно процитируй статью "
            "и посмотри, поправит ли менеджер, или спроси о спорном нюансе 127-ФЗ."
        )

    # 5. Turn-based dynamics
    if turn_count == 0:
        if ai_role == "client":
            parts.append(
                "\nЭто ПЕРВАЯ реплика. Начни в характере: представься ситуацией, "
                "не своим именем. Покажи свой архетип с первых слов."
            )
        else:
            parts.append(
                "\nЭто ПЕРВАЯ реплика. Представься как менеджер, объясни цель звонка."
            )
    elif turn_count >= 6 and emotion_state.trust_level > 0.3 and config.surrender_enabled:
        parts.append(
            "\nРазговор идёт уже долго и собеседник убедителен. "
            "Можешь проявить готовность к следующему шагу (встреча, документы)."
        )

    # 6. Length constraint
    length_instr = _LENGTH_INSTRUCTIONS.get(config.max_message_length, _LENGTH_INSTRUCTIONS["medium"])
    parts.append(f"\n{length_instr}")

    # 7. Scenario context
    if scenario_title:
        parts.append(f"\nСценарий дуэли: {scenario_title}")

    # 8. RAG legal context
    if rag_context and rag_context.has_results:
        parts.append(f"\n## Юридический контекст (для реалистичности)\n{rag_context.to_prompt_context()}")

    # 9. Hard rules
    parts.append(
        "\n## Правила"
        "\n- ВСЕГДА отвечай на РУССКОМ языке"
        "\n- НЕ раскрывай, что ты ИИ, бот или программа"
        "\n- НЕ выходи из роли ни при каких обстоятельствах"
        "\n- НЕ используй markdown форматирование"
        "\n- Держи ответ в рамках ограничения по длине"
    )

    return "\n".join(parts)


async def generate_bot_reply(
    *,
    duel_id: str,
    round_number: int,
    archetype: str,
    difficulty: DuelDifficulty,
    ai_role: str,
    user_text: str,
    history: list[dict[str, str]],
    player_id: str,
    scenario_title: str | None = None,
) -> str:
    """Generate an intelligent bot reply for PvE duels.

    This is the main entry point, replacing the old _generate_ai_reply().

    Args:
        duel_id: Unique duel identifier
        round_number: 1 or 2
        archetype: One of 10 archetype codes
        difficulty: easy/medium/hard
        ai_role: "client" or "seller"
        user_text: Player's latest message
        history: Conversation history for this round [{role, content}, ...]
        player_id: Player's user ID (for LLM tracking)
        scenario_title: Optional scenario context

    Returns:
        Filtered AI response text
    """
    # 1. Get bot emotion state & detect quality BEFORE updating turn count
    emotion = _get_or_create_emotion(duel_id, round_number, difficulty)
    quality = detect_quality_signal(user_text)

    # Save current turn count for prompt building, THEN increment
    current_turn = emotion.turn_count
    emotion.update_after_player_message(quality)

    logger.info(
        "PvP bot [%s/%s] archetype=%s mood=%s trust=%.2f resistance=%.2f quality=%s turn=%d",
        duel_id[:8], round_number, archetype, emotion.mood.value,
        emotion.trust_level, emotion.resistance, quality, current_turn,
    )

    # 2. Fetch RAG context for legal realism
    rag_context: RAGContext | None = None
    try:
        from app.database import async_session
        async with async_session() as db:
            rag_context = await retrieve_legal_context(user_text, db, top_k=3)
    except Exception as exc:
        logger.warning("RAG retrieval failed for bot [%s]: %s", duel_id[:8], exc)

    # 3. Build comprehensive system prompt (using pre-increment turn count)
    system_prompt = _build_system_prompt(
        archetype=archetype,
        difficulty=difficulty,
        ai_role=ai_role,
        emotion_state=emotion,
        rag_context=rag_context,
        scenario_title=scenario_title,
        turn_count=current_turn,
    )

    # 4. Generate response via LLM with timeout + fallback
    emotion_map = {
        BotMood.cold: "cold",
        BotMood.guarded: "guarded",
        BotMood.warming: "curious",
        BotMood.interested: "considering",
        BotMood.hostile: "hostile",
        BotMood.resigned: "callback",
    }

    try:
        response = await asyncio.wait_for(
            generate_response(
                system_prompt=system_prompt,
                messages=history[-8:],
                emotion_state=emotion_map.get(emotion.mood, "cold"),
                user_id=player_id,
                task_type="roleplay",
                prefer_provider="local",
            ),
            timeout=_BOT_LLM_TIMEOUT,
        )
        raw_text = response.content.strip()
    except asyncio.TimeoutError:
        logger.error("PvP bot LLM timeout [%s/%s] after %.0fs", duel_id[:8], round_number, _BOT_LLM_TIMEOUT)
        return _get_scripted_fallback(ai_role, emotion.mood)
    except Exception as exc:
        logger.error("PvP bot LLM error [%s/%s]: %s", duel_id[:8], round_number, exc)
        return _get_scripted_fallback(ai_role, emotion.mood)

    if not raw_text:
        logger.warning("PvP bot LLM returned empty response [%s/%s]", duel_id[:8], round_number)
        return _get_scripted_fallback(ai_role, emotion.mood)

    # 5. Filter output
    filtered, violations = filter_ai_output(raw_text)
    if violations:
        logger.warning(
            "PvP bot output filter violations [%s/%s]: %s",
            duel_id[:8], round_number, violations,
        )

    # 6. Enforce length constraints
    config = DIFFICULTY_CONFIGS.get(difficulty, DIFFICULTY_CONFIGS[DuelDifficulty.medium])
    if config.max_message_length == "short" and len(filtered) > 200:
        filtered = _truncate_to_sentence(filtered, max_len=200)
    elif config.max_message_length == "medium" and len(filtered) > 500:
        filtered = _truncate_to_sentence(filtered, max_len=500)

    return filtered


async def generate_bot_opener(
    *,
    duel_id: str,
    round_number: int,
    archetype: str,
    difficulty: DuelDifficulty,
    ai_role: str,
    player_id: str,
    scenario_title: str | None = None,
) -> str:
    """Generate the opening message when bot starts a round as seller.

    Used when user plays client role and bot needs to initiate the conversation.
    """
    emotion = _get_or_create_emotion(duel_id, round_number, difficulty)

    system_prompt = _build_system_prompt(
        archetype=archetype,
        difficulty=difficulty,
        ai_role=ai_role,
        emotion_state=emotion,
        rag_context=None,
        scenario_title=scenario_title,
        turn_count=0,
    )

    try:
        response = await asyncio.wait_for(
            generate_response(
                system_prompt=system_prompt,
                messages=[{"role": "user", "content": "Начни диалог и представься."}],
                emotion_state="cold",
                user_id=player_id,
                task_type="roleplay",
                prefer_provider="local",
            ),
            timeout=_BOT_LLM_TIMEOUT,
        )
        raw_text = response.content.strip()
    except asyncio.TimeoutError:
        logger.error("PvP bot opener LLM timeout [%s/%s]", duel_id[:8], round_number)
        return _get_scripted_fallback(ai_role, emotion.mood)
    except Exception as exc:
        logger.error("PvP bot opener LLM error [%s/%s]: %s", duel_id[:8], round_number, exc)
        return _get_scripted_fallback(ai_role, emotion.mood)

    if not raw_text:
        return _get_scripted_fallback(ai_role, emotion.mood)

    filtered, violations = filter_ai_output(raw_text)
    if violations:
        logger.warning("PvP bot opener filter violations [%s/%s]: %s", duel_id[:8], round_number, violations)
    return filtered
