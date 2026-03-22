"""Seed voice profiles, emotion modifiers, and pause configs (ТЗ-04).

Run: python -m scripts.seed_voices
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select, text
from app.database import async_session, engine, Base
from app.models.voice import VoiceProfile, EmotionVoiceModifier, PauseConfig

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 18 Voice Profiles (9M + 9F) — все voice_id реальные ElevenLabs ID.
# 14 основных + 4 дополнительных для вариативности голосов между пользователями.
# Дополнительные профили пересекаются по archetype_codes с основными,
# чтобы система могла назначать разные голоса одному архетипу для разных юзеров.
# ---------------------------------------------------------------------------

VOICE_PROFILES = [
    # --- MALE ---
    {
        "voice_id": "m0OQuJtWCw1V23P0pQmG",
        "voice_name": "Алексей — баритон",
        "voice_code": "aleksey_baritone",
        "gender": "male",
        "base_stability": 0.60,
        "base_similarity_boost": 0.80,
        "base_style": 0.20,
        "base_speed": 1.00,
        "archetype_codes": ["skeptic", "paranoid", "know_it_all", "overwhelmed", "pragmatic"],
        "age_range": "middle",
        "voice_type": "firm",
        "description": "Уверенный мужской баритон. Чёткая дикция, ровная подача. Звучит как профессионал — оценивающий, скептичный тон.",
    },
    {
        "voice_id": "0ArNnoIAWKlT4WweaVMY",
        "voice_name": "Дмитрий — бас",
        "voice_code": "dmitry_bass",
        "gender": "male",
        "base_stability": 0.30,
        "base_similarity_boost": 0.70,
        "base_style": 0.45,
        "base_speed": 1.10,
        "archetype_codes": ["aggressive", "hostile", "blamer", "rushed"],
        "age_range": "middle",
        "voice_type": "aggressive",
        "description": "Низкий грубоватый бас с хрипотцой. Напористый, прямолинейный. Хорошо передаёт агрессию при понижении stability.",
    },
    {
        "voice_id": "pmBaSTYT1W9R6YCJq6o2",
        "voice_name": "Сергей — усталый",
        "voice_code": "sergey_tired",
        "gender": "male",
        "base_stability": 0.70,
        "base_similarity_boost": 0.65,
        "base_style": 0.10,
        "base_speed": 0.85,
        "archetype_codes": ["delegator", "passive", "returner", "avoidant"],
        "age_range": "senior",
        "voice_type": "neutral",
        "description": "Спокойный усталый баритон пожилого мужчины. Монотонный, размеренный. 'Повидал всё' — не удивляется.",
    },
    {
        "voice_id": "mOTbMAOniC3yoEvgo4bi",
        "voice_name": "Андрей — деловой",
        "voice_code": "andrey_business",
        "gender": "male",
        "base_stability": 0.55,
        "base_similarity_boost": 0.80,
        "base_style": 0.30,
        "base_speed": 1.05,
        "archetype_codes": ["pragmatic", "negotiator", "grateful", "lawyer_client"],
        "age_range": "young",
        "voice_type": "warm",
        "description": "Энергичный деловой тенор молодого мужчины. Уверенный, открытый. Хорошо модулируется от дружелюбного до напористого.",
    },
    {
        "voice_id": "WOY6pnQ1WCg0mrOZ54lM",
        "voice_name": "Виктор — тихий",
        "voice_code": "viktor_quiet",
        "gender": "male",
        "base_stability": 0.30,
        "base_similarity_boost": 0.65,
        "base_style": 0.30,
        "base_speed": 0.90,
        "archetype_codes": ["desperate", "ashamed", "crying", "anxious"],
        "age_range": "senior",
        "voice_type": "soft",
        "description": "Тихий неуверенный тенор пожилого мужчины. Голос дрожит при низкой stability. Просительная интонация.",
    },
    {
        "voice_id": "FnNYfPjyvZwLwb043Kl1",
        "voice_name": "Максим — ироничный",
        "voice_code": "maxim_ironic",
        "gender": "male",
        "base_stability": 0.50,
        "base_similarity_boost": 0.75,
        "base_style": 0.50,
        "base_speed": 1.05,
        "archetype_codes": ["sarcastic", "shopper", "rushed"],
        "age_range": "young",
        "voice_type": "firm",
        "description": "Быстрый ироничный баритон молодого мужчины. Уверенный с лёгким цинизмом. Отлично передаёт сарказм.",
    },
    {
        "voice_id": "pM78bgjPVk0JXtaEnFoj",
        "voice_name": "Игорь — нейтральный",
        "voice_code": "igor_neutral",
        "gender": "male",
        "base_stability": 0.55,
        "base_similarity_boost": 0.75,
        "base_style": 0.20,
        "base_speed": 1.00,
        "archetype_codes": ["avoidant", "returner", "overwhelmed", "couple"],
        "age_range": "middle",
        "voice_type": "neutral",
        "description": "Нейтральный мужской баритон среднего возраста. Универсальный fallback-голос. Хорошо модулируется в любую сторону.",
    },
    # --- FEMALE ---
    {
        "voice_id": "RLRdvNFwJJct2XZOgfzy",
        "voice_name": "Елена — уверенная",
        "voice_code": "elena_confident",
        "gender": "female",
        "base_stability": 0.60,
        "base_similarity_boost": 0.80,
        "base_style": 0.25,
        "base_speed": 1.05,
        "archetype_codes": ["skeptic", "know_it_all", "shopper", "pragmatic", "lawyer_client"],
        "age_range": "middle",
        "voice_type": "firm",
        "description": "Уверенное женское меццо-сопрано. Деловая, чёткая дикция. Звучит как руководитель — привыкла к переговорам.",
    },
    {
        "voice_id": "VD1if7jDVYtAKs4P0FIY",
        "voice_name": "Марина — обаятельная",
        "voice_code": "marina_charming",
        "gender": "female",
        "base_stability": 0.50,
        "base_similarity_boost": 0.75,
        "base_style": 0.40,
        "base_speed": 0.95,
        "archetype_codes": ["manipulator", "grateful", "negotiator"],
        "age_range": "middle",
        "voice_type": "warm",
        "description": "Мягкое обаятельное женское меццо-сопрано. Располагающая интонация. Идеальна для давления на жалость.",
    },
    {
        "voice_id": "goT3UYdM9bhm0n2lmKQx",
        "voice_name": "Ольга — резкая",
        "voice_code": "olga_sharp",
        "gender": "female",
        "base_stability": 0.30,
        "base_similarity_boost": 0.65,
        "base_style": 0.45,
        "base_speed": 1.10,
        "archetype_codes": ["aggressive", "hostile", "blamer", "couple"],
        "age_range": "middle",
        "voice_type": "aggressive",
        "description": "Резкое эмоциональное женское сопрано. Визгливые интонации при агрессии. Хорошо передаёт ярость.",
    },
    {
        "voice_id": "6sFKzaJr574YWVu4UuJF",
        "voice_name": "Светлана — робкая",
        "voice_code": "svetlana_timid",
        "gender": "female",
        "base_stability": 0.40,
        "base_similarity_boost": 0.60,
        "base_style": 0.10,
        "base_speed": 0.85,
        "archetype_codes": ["anxious", "passive", "desperate", "ashamed", "crying"],
        "age_range": "senior",
        "voice_type": "soft",
        "description": "Тихое робкое женское меццо-сопрано пожилой женщины. Неуверенный, стеснительный голос.",
    },
    {
        "voice_id": "cgLpYGyXZhkyalKZ0xeZ",
        "voice_name": "Наталья — отстранённая",
        "voice_code": "natalya_detached",
        "gender": "female",
        "base_stability": 0.60,
        "base_similarity_boost": 0.70,
        "base_style": 0.15,
        "base_speed": 0.95,
        "archetype_codes": ["delegator", "avoidant", "couple", "returner", "overwhelmed"],
        "age_range": "middle",
        "voice_type": "neutral",
        "description": "Спокойное отстранённое женское меццо-сопрано. Нейтральная интонация. Как будто обсуждает чужие проблемы.",
    },
    {
        "voice_id": "2vubyVoGjNJ5HPga4SkV",
        "voice_name": "Анна — дружелюбная",
        "voice_code": "anna_friendly",
        "gender": "female",
        "base_stability": 0.55,
        "base_similarity_boost": 0.80,
        "base_style": 0.35,
        "base_speed": 1.00,
        "archetype_codes": ["negotiator", "pragmatic", "grateful", "referred"],
        "age_range": "young",
        "voice_type": "warm",
        "description": "Дружелюбное молодое женское сопрано. Энергичная, деловая, но тёплая. Хорошо передаёт интерес и радость.",
    },
    {
        "voice_id": "lUCNYQh2kqW2wiie85Qk",
        "voice_name": "Татьяна — стеснительная",
        "voice_code": "tatyana_shy",
        "gender": "female",
        "base_stability": 0.35,
        "base_similarity_boost": 0.60,
        "base_style": 0.15,
        "base_speed": 0.85,
        "archetype_codes": ["anxious", "ashamed", "crying", "desperate"],
        "age_range": "young",
        "voice_type": "soft",
        "description": "Тихое стеснительное женское сопрано молодой девушки. Хезитации звучат натурально. Голос 'впервые столкнулась с проблемой'.",
    },
    # --- EXTRA MALE (variety — overlapping archetypes) ---
    {
        "voice_id": "kVBPcEMsUF1nsAO1oNWw",
        "voice_name": "Роман — напористый",
        "voice_code": "roman_pushy",
        "gender": "male",
        "base_stability": 0.40,
        "base_similarity_boost": 0.75,
        "base_style": 0.35,
        "base_speed": 1.10,
        "archetype_codes": ["aggressive", "skeptic", "rushed", "hostile", "blamer"],
        "age_range": "young",
        "voice_type": "aggressive",
        "description": "Напористый молодой мужской голос. Альтернатива Дмитрию для агрессивных архетипов — моложе, резче, быстрее.",
    },
    {
        "voice_id": "6A9D8WSMm4rFsg2DWFeE",
        "voice_name": "Павел — рассудительный",
        "voice_code": "pavel_thoughtful",
        "gender": "male",
        "base_stability": 0.65,
        "base_similarity_boost": 0.70,
        "base_style": 0.15,
        "base_speed": 0.90,
        "archetype_codes": ["pragmatic", "negotiator", "know_it_all", "delegator", "lawyer_client"],
        "age_range": "middle",
        "voice_type": "neutral",
        "description": "Рассудительный мужской баритон среднего возраста. Альтернатива Андрею/Алексею — спокойнее, вдумчивее.",
    },
    # --- EXTRA FEMALE (variety — overlapping archetypes) ---
    {
        "voice_id": "TPIitICAZ8CqlGZ81AKm",
        "voice_name": "Ирина — эмоциональная",
        "voice_code": "irina_emotional",
        "gender": "female",
        "base_stability": 0.35,
        "base_similarity_boost": 0.70,
        "base_style": 0.40,
        "base_speed": 0.95,
        "archetype_codes": ["desperate", "crying", "anxious", "ashamed", "manipulator"],
        "age_range": "middle",
        "voice_type": "soft",
        "description": "Эмоциональное женское меццо-сопрано. Альтернатива Светлане — моложе, больше надрыва, слёзы в голосе.",
    },
    {
        "voice_id": "YKrm0N1EAM9Bw27j8kuD",
        "voice_name": "Дарья — деловая",
        "voice_code": "darya_business",
        "gender": "female",
        "base_stability": 0.55,
        "base_similarity_boost": 0.80,
        "base_style": 0.30,
        "base_speed": 1.05,
        "archetype_codes": ["skeptic", "know_it_all", "pragmatic", "shopper", "negotiator"],
        "age_range": "young",
        "voice_type": "firm",
        "description": "Деловое молодое женское сопрано. Альтернатива Елене — моложе, энергичнее, конкурентный тон.",
    },
]

# ---------------------------------------------------------------------------
# 10 Emotion Voice Modifiers (from ТЗ-04 spec)
# ---------------------------------------------------------------------------

EMOTION_MODIFIERS = [
    {
        "emotion_state": "cold",
        "stability_delta": +0.20,
        "similarity_delta": +0.05,
        "style_delta": -0.20,
        "speed_delta": +0.05,
        "description": "Ровный, сдержанный, чуть быстрее. Без интереса к разговору.",
        "instant_transition": False,
    },
    {
        "emotion_state": "guarded",
        "stability_delta": +0.10,
        "similarity_delta": 0.00,
        "style_delta": -0.10,
        "speed_delta": 0.00,
        "description": "Настороженный, контролируемый. Слушает, но не доверяет.",
        "instant_transition": False,
    },
    {
        "emotion_state": "curious",
        "stability_delta": -0.05,
        "similarity_delta": 0.00,
        "style_delta": +0.10,
        "speed_delta": -0.05,
        "description": "Более живой, чуть медленнее. Искренний интерес.",
        "instant_transition": False,
    },
    {
        "emotion_state": "considering",
        "stability_delta": +0.05,
        "similarity_delta": 0.00,
        "style_delta": 0.00,
        "speed_delta": -0.10,
        "description": "Задумчивый, медленнее. Взвешивает аргументы.",
        "instant_transition": False,
    },
    {
        "emotion_state": "negotiating",
        "stability_delta": -0.10,
        "similarity_delta": +0.05,
        "style_delta": +0.15,
        "speed_delta": +0.05,
        "description": "Деловой, чуть быстрее, экспрессивнее. Активные переговоры.",
        "instant_transition": False,
    },
    {
        "emotion_state": "deal",
        "stability_delta": -0.15,
        "similarity_delta": 0.00,
        "style_delta": +0.20,
        "speed_delta": -0.05,
        "description": "Позитивный, расслабленный, открытый. Решение принято.",
        "instant_transition": False,
    },
    {
        "emotion_state": "testing",
        "stability_delta": +0.15,
        "similarity_delta": +0.05,
        "style_delta": 0.00,
        "speed_delta": +0.10,
        "description": "Чёткий, быстрый, оценивающий. Провокационный тон.",
        "instant_transition": False,
    },
    {
        "emotion_state": "callback",
        "stability_delta": +0.10,
        "similarity_delta": 0.00,
        "style_delta": -0.10,
        "speed_delta": 0.00,
        "description": "Ровный, закрывающий разговор. Нейтральный тон.",
        "instant_transition": False,
    },
    {
        "emotion_state": "hostile",
        "stability_delta": -0.30,
        "similarity_delta": -0.10,
        "style_delta": +0.30,
        "speed_delta": +0.15,
        "description": "Нестабильный, экспрессивный, быстрый. Крик и ярость.",
        "instant_transition": True,  # instant — anger is sudden
    },
    {
        "emotion_state": "hangup",
        "stability_delta": +0.20,
        "similarity_delta": 0.00,
        "style_delta": -0.15,
        "speed_delta": +0.10,
        "description": "Резкий, отстранённый, финальный. Разговор окончен.",
        "instant_transition": True,  # instant — hangs up abruptly
    },
]

# ---------------------------------------------------------------------------
# 10 Pause Configs (from ТЗ-04 Block В)
# ---------------------------------------------------------------------------

PAUSE_CONFIGS = [
    {
        "emotion_state": "cold",
        "after_period_ms": 200,
        "before_conjunction_ms": 100,
        "after_comma_ms": 100,
        "hesitation_probability": 0.05,
        "hesitation_pool": [],
        "max_hesitations_per_phrase": 0,
        "dramatic_pause_ms": 0,
        "breath_probability": 0.10,
        "description": "Короткие сухие паузы. Хочет закончить разговор быстрее.",
    },
    {
        "emotion_state": "guarded",
        "after_period_ms": 500,
        "before_conjunction_ms": 400,
        "after_comma_ms": 250,
        "hesitation_probability": 0.25,
        "hesitation_pool": ["ну...", "это...", "как бы..."],
        "max_hesitations_per_phrase": 2,
        "dramatic_pause_ms": 300,
        "breath_probability": 0.20,
        "description": "Длинные паузы, хезитации. Обдумывает каждое слово.",
    },
    {
        "emotion_state": "curious",
        "after_period_ms": 200,
        "before_conjunction_ms": 150,
        "after_comma_ms": 100,
        "hesitation_probability": 0.05,
        "hesitation_pool": [],
        "max_hesitations_per_phrase": 0,
        "dramatic_pause_ms": 200,
        "breath_probability": 0.15,
        "description": "Короткие паузы, увлечён. Речь льётся.",
    },
    {
        "emotion_state": "considering",
        "after_period_ms": 800,
        "before_conjunction_ms": 600,
        "after_comma_ms": 400,
        "hesitation_probability": 0.30,
        "hesitation_pool": ["хм...", "ну...", "вот...", "значит...", "то есть..."],
        "max_hesitations_per_phrase": 3,
        "dramatic_pause_ms": 500,
        "breath_probability": 0.25,
        "description": "Очень длинные паузы, глубоко думает. Самый задумчивый режим.",
    },
    {
        "emotion_state": "negotiating",
        "after_period_ms": 300,
        "before_conjunction_ms": 250,
        "after_comma_ms": 150,
        "hesitation_probability": 0.10,
        "hesitation_pool": ["так..."],
        "max_hesitations_per_phrase": 1,
        "dramatic_pause_ms": 400,
        "breath_probability": 0.15,
        "description": "Средние деловые паузы. Тактические паузы перед ценой.",
    },
    {
        "emotion_state": "deal",
        "after_period_ms": 400,
        "before_conjunction_ms": 200,
        "after_comma_ms": 200,
        "hesitation_probability": 0.05,
        "hesitation_pool": [],
        "max_hesitations_per_phrase": 0,
        "dramatic_pause_ms": 300,
        "breath_probability": 0.15,
        "description": "Средние расслабленные паузы. Позитивные, нет колебаний.",
    },
    {
        "emotion_state": "testing",
        "after_period_ms": 300,
        "before_conjunction_ms": 200,
        "after_comma_ms": 150,
        "hesitation_probability": 0.05,
        "hesitation_pool": [],
        "max_hesitations_per_phrase": 0,
        "dramatic_pause_ms": 500,
        "breath_probability": 0.10,
        "description": "Средние оценивающие паузы. Драматические паузы перед подвохом.",
    },
    {
        "emotion_state": "callback",
        "after_period_ms": 500,
        "before_conjunction_ms": 300,
        "after_comma_ms": 250,
        "hesitation_probability": 0.15,
        "hesitation_pool": ["ну...", "давайте..."],
        "max_hesitations_per_phrase": 2,
        "dramatic_pause_ms": 0,
        "breath_probability": 0.20,
        "description": "Средне-длинные паузы. Закрывает разговор, не торопится.",
    },
    {
        "emotion_state": "hostile",
        "after_period_ms": 100,
        "before_conjunction_ms": 50,
        "after_comma_ms": 50,
        "hesitation_probability": 0.0,
        "hesitation_pool": [],
        "max_hesitations_per_phrase": 0,
        "dramatic_pause_ms": 0,
        "breath_probability": 0.30,
        "description": "Минимальные паузы — поток агрессии. Только резкие вдохи.",
    },
    {
        "emotion_state": "hangup",
        "after_period_ms": 200,
        "before_conjunction_ms": 0,
        "after_comma_ms": 100,
        "hesitation_probability": 0.0,
        "hesitation_pool": [],
        "max_hesitations_per_phrase": 0,
        "dramatic_pause_ms": 300,
        "breath_probability": 0.05,
        "description": "Короткие финальные паузы. Одна драматическая перед 'до свидания'.",
    },
]


# ---------------------------------------------------------------------------
# Seed functions
# ---------------------------------------------------------------------------

async def _seed_voice_profiles(session) -> int:
    """Insert voice profiles, skip existing."""
    count = 0
    for vp_data in VOICE_PROFILES:
        existing = await session.execute(
            select(VoiceProfile).where(VoiceProfile.voice_code == vp_data["voice_code"])
        )
        if existing.scalar_one_or_none():
            continue
        session.add(VoiceProfile(**vp_data))
        count += 1
    return count


async def _seed_emotion_modifiers(session) -> int:
    """Insert emotion voice modifiers, skip existing."""
    count = 0
    for em_data in EMOTION_MODIFIERS:
        existing = await session.execute(
            select(EmotionVoiceModifier).where(
                EmotionVoiceModifier.emotion_state == em_data["emotion_state"]
            )
        )
        if existing.scalar_one_or_none():
            continue
        session.add(EmotionVoiceModifier(**em_data))
        count += 1
    return count


async def _seed_pause_configs(session) -> int:
    """Insert pause configs, skip existing."""
    count = 0
    for pc_data in PAUSE_CONFIGS:
        existing = await session.execute(
            select(PauseConfig).where(PauseConfig.emotion_state == pc_data["emotion_state"])
        )
        if existing.scalar_one_or_none():
            continue
        session.add(PauseConfig(**pc_data))
        count += 1
    return count


async def seed_all():
    """Run all voice seed functions."""
    # Create tables if they don't exist
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session() as session:
        vp_count = await _seed_voice_profiles(session)
        em_count = await _seed_emotion_modifiers(session)
        pc_count = await _seed_pause_configs(session)
        await session.commit()

        print(f"[seed_voices] Voice profiles: {vp_count} inserted")
        print(f"[seed_voices] Emotion modifiers: {em_count} inserted")
        print(f"[seed_voices] Pause configs: {pc_count} inserted")
        print(f"[seed_voices] Done! Total: {vp_count + em_count + pc_count} rows")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(seed_all())
