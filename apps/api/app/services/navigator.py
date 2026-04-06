"""Navigator — curated quote library with 6-hour rotation.

Logic (stateless, no DB required):
  slot       = utc_hour // 6                     → 0, 1, 2, 3
  day_number = unix_timestamp_utc // 86400        → days since epoch
  index      = (day_number * 4 + slot) % TOTAL   → deterministic quote index

This guarantees every user sees the exact same quote in the same 6-hour window
worldwide, and the sequence cycles through the full library over ~19 days.
"""

from datetime import datetime, timezone
from typing import TypedDict

# ─── Category labels (Russian) ────────────────────────────────────────────────
CATEGORY_LABELS: dict[str, str] = {
    "negotiations":    "Переговоры и влияние",
    "sales":           "Продажи и убеждение",
    "psychology":      "Психология влияния",
    "strategy":        "Стратегическое мышление",
    "leadership":      "Лидерство",
    "law":             "Право и аргументация",
    "discipline":      "Дисциплина и продуктивность",
    "money":           "Деньги, капитал, власть",
    "mindset":         "Психология успеха",
    "communication":   "Коммуникация и присутствие",
    "extreme":         "Экстремальный контекст",
}


class Quote(TypedDict):
    text:     str
    author:   str
    source:   str   # book/origin, or "" if none
    category: str   # key from CATEGORY_LABELS


# ─── 77 quotes ────────────────────────────────────────────────────────────────
QUOTES: list[Quote] = [

    # ── I. ПЕРЕГОВОРЫ И ВЛИЯНИЕ (8) ──────────────────────────────────────────
    {
        "text":     "Никогда не позволяйте другой стороне знать, что вам нужна сделка. "
                    "Тот, кто больше нуждается — проигрывает.",
        "author":   "Джим Кэмп",
        "source":   "Сначала скажите НЕТ",
        "category": "negotiations",
    },
    {
        "text":     "Самая мощная позиция на переговорах — готовность уйти.",
        "author":   "Роджер Доусон",
        "source":   "",
        "category": "negotiations",
    },
    {
        "text":     "Тот, кто контролирует повестку — контролирует исход.",
        "author":   "Генри Киссинджер",
        "source":   "",
        "category": "negotiations",
    },
    {
        "text":     "Переговоры — это не соревнование. Это совместное решение проблемы, "
                    "в котором у вас разные интересы.",
        "author":   "Роджер Фишер",
        "source":   "Путь к согласию",
        "category": "negotiations",
    },
    {
        "text":     "Молчание — самый мощный инструмент переговорщика. "
                    "Большинство людей не выносят паузы и заполняют её уступками.",
        "author":   "Крис Восс",
        "source":   "Никаких компромиссов",
        "category": "negotiations",
    },
    {
        "text":     "Никогда не делайте предложение первым, если не знаете диапазон противника.",
        "author":   "Крис Восс",
        "source":   "",
        "category": "negotiations",
    },
    {
        "text":     "Люди не покупают логику. Они покупают эмоцию и обосновывают её логикой.",
        "author":   "Зиг Зиглар",
        "source":   "",
        "category": "negotiations",
    },
    {
        "text":     "Позвольте другой стороне говорить. Информация — это власть.",
        "author":   "Дэниел Канеман",
        "source":   "",
        "category": "negotiations",
    },

    # ── II. ПРОДАЖИ И УБЕЖДЕНИЕ (8) ──────────────────────────────────────────
    {
        "text":     "Продажа происходит, когда клиент убеждает себя сам. "
                    "Ваша задача — задать правильные вопросы.",
        "author":   "Нил Рэкхэм",
        "source":   "СПИН-продажи",
        "category": "sales",
    },
    {
        "text":     "Возражение — это не отказ. Это запрос на дополнительную информацию.",
        "author":   "Брайан Трейси",
        "source":   "",
        "category": "sales",
    },
    {
        "text":     "Люди покупают у тех, кому доверяют. "
                    "Доверие строится медленно, разрушается мгновенно.",
        "author":   "Уоррен Баффет",
        "source":   "",
        "category": "sales",
    },
    {
        "text":     "Ценность — это не то, что вы предлагаете. "
                    "Это то, что клиент считает ценным.",
        "author":   "Нил Рэкхэм",
        "source":   "",
        "category": "sales",
    },
    {
        "text":     "Единственный способ влиять на людей — говорить им о том, "
                    "чего они хотят, и показывать, как это получить.",
        "author":   "Дейл Карнеги",
        "source":   "Как завоёвывать друзей",
        "category": "sales",
    },
    {
        "text":     "Прежде чем продавать — продайте себя.",
        "author":   "Наполеон Хилл",
        "source":   "",
        "category": "sales",
    },
    {
        "text":     "Цена никогда не является реальным возражением. "
                    "За ней всегда скрывается отсутствие воспринимаемой ценности.",
        "author":   "Брайан Трейси",
        "source":   "",
        "category": "sales",
    },
    {
        "text":     "Самый опасный момент в продаже — когда вы думаете, что уже победили.",
        "author":   "Дэвид Сэндлер",
        "source":   "",
        "category": "sales",
    },

    # ── III. ПСИХОЛОГИЯ ВЛИЯНИЯ (8) ───────────────────────────────────────────
    {
        "text":     "Человек, которому сделали одолжение, с большей вероятностью "
                    "сделает одолжение в ответ, чем тот, кому помогли.",
        "author":   "Бенджамин Франклин",
        "source":   "Эффект Франклина",
        "category": "psychology",
    },
    {
        "text":     "Последовательность — это тюрьма, в которую большинство людей "
                    "заходят добровольно.",
        "author":   "Роберт Чалдини",
        "source":   "Психология влияния",
        "category": "psychology",
    },
    {
        "text":     "Люди следуют за авторитетом. Сначала продемонстрируйте экспертность — "
                    "потом делайте запрос.",
        "author":   "Роберт Чалдини",
        "source":   "",
        "category": "psychology",
    },
    {
        "text":     "Дефицит создаёт ценность. Всё, что редко — желанно.",
        "author":   "Роберт Чалдини",
        "source":   "",
        "category": "psychology",
    },
    {
        "text":     "Никто не принимает решения на основе фактов. "
                    "Все принимают решения на основе чувств и ищут факты в подтверждение.",
        "author":   "Антонио Дамасио",
        "source":   "Ошибка Декарта",
        "category": "psychology",
    },
    {
        "text":     "Фрейминг важнее содержания. Одно и то же можно подать как потерю "
                    "или как выгоду — реакция будет полностью разной.",
        "author":   "Даниэль Канеман",
        "source":   "Думай медленно, решай быстро",
        "category": "psychology",
    },
    {
        "text":     "Люди в 2,5 раза сильнее мотивированы избежать потери, "
                    "чем получить эквивалентную выгоду.",
        "author":   "Даниэль Канеман / Амос Тверски",
        "source":   "Теория перспектив",
        "category": "psychology",
    },
    {
        "text":     "Якорение работает всегда. Первое названное число формирует "
                    "всё последующее восприятие диапазона.",
        "author":   "Даниэль Канеман",
        "source":   "",
        "category": "psychology",
    },

    # ── IV. СТРАТЕГИЧЕСКОЕ МЫШЛЕНИЕ (8) ──────────────────────────────────────
    {
        "text":     "Если вы знаете врага и знаете себя — вам не нужно бояться "
                    "результата ста сражений.",
        "author":   "Сунь-цзы",
        "source":   "Искусство войны",
        "category": "strategy",
    },
    {
        "text":     "Лучшая победа — та, в которой не нужно сражаться.",
        "author":   "Сунь-цзы",
        "source":   "Искусство войны",
        "category": "strategy",
    },
    {
        "text":     "Стратегия без тактики — самый медленный путь к победе. "
                    "Тактика без стратегии — шум перед поражением.",
        "author":   "Сунь-цзы",
        "source":   "",
        "category": "strategy",
    },
    {
        "text":     "Не реагируйте на ситуацию — формируйте её заранее.",
        "author":   "Никколо Макиавелли",
        "source":   "Государь",
        "category": "strategy",
    },
    {
        "text":     "Тот, кто умеет предвидеть трудности и устранять их заблаговременно, "
                    "непобедим.",
        "author":   "Никколо Макиавелли",
        "source":   "",
        "category": "strategy",
    },
    {
        "text":     "В игре без правил побеждает тот, кто сам устанавливает правила.",
        "author":   "Роберт Грин",
        "source":   "48 законов власти",
        "category": "strategy",
    },
    {
        "text":     "Никогда не демонстрируйте всё своё мастерство сразу. "
                    "Всегда оставляйте что-то, чего о вас не знают.",
        "author":   "Роберт Грин",
        "source":   "48 законов власти",
        "category": "strategy",
    },
    {
        "text":     "Делайте работу, оставаясь в тени, и управляйте теми, кто на виду.",
        "author":   "Роберт Грин",
        "source":   "",
        "category": "strategy",
    },

    # ── V. ЛИДЕРСТВО И КОМАНДНАЯ РАБОТА (7) ──────────────────────────────────
    {
        "text":     "Скорость лидера определяет скорость группы.",
        "author":   "Мэри Кэй Эш",
        "source":   "",
        "category": "leadership",
    },
    {
        "text":     "Управлять — значит работать через других, а не вместо них.",
        "author":   "Питер Друкер",
        "source":   "",
        "category": "leadership",
    },
    {
        "text":     "Великие лидеры не производят последователей. "
                    "Они производят других лидеров.",
        "author":   "Том Питерс",
        "source":   "",
        "category": "leadership",
    },
    {
        "text":     "Разница между менеджером и лидером: менеджер делает вещи правильно, "
                    "лидер делает правильные вещи.",
        "author":   "Питер Друкер",
        "source":   "",
        "category": "leadership",
    },
    {
        "text":     "Ваша задача как лидера — не быть правым. "
                    "Ваша задача — получить правильный результат.",
        "author":   "Джек Уэлч",
        "source":   "",
        "category": "leadership",
    },
    {
        "text":     "Окружайте себя теми, кто лучше вас в конкретных задачах. "
                    "Это и есть сила, не слабость.",
        "author":   "Эндрю Карнеги",
        "source":   "",
        "category": "leadership",
    },
    {
        "text":     "Люди уходят не из компаний. Они уходят от руководителей.",
        "author":   "Маркус Бакингем",
        "source":   "",
        "category": "leadership",
    },

    # ── VI. ПРАВО, АРГУМЕНТАЦИЯ, ЛОГИКА (8) ──────────────────────────────────
    {
        "text":     "Закон без зубов — это просто совет.",
        "author":   "Афоризм англосаксонской школы права",
        "source":   "",
        "category": "law",
    },
    {
        "text":     "Тот, кто определяет термины — выигрывает спор.",
        "author":   "Аристотель",
        "source":   "",
        "category": "law",
    },
    {
        "text":     "Слабый аргумент, произнесённый уверенно, часто побеждает сильный аргумент, "
                    "произнесённый с колебанием.",
        "author":   "Цицерон",
        "source":   "",
        "category": "law",
    },
    {
        "text":     "Судите о намерениях по действиям, не по словам.",
        "author":   "Цицерон",
        "source":   "",
        "category": "law",
    },
    {
        "text":     "Закон — это разум без страсти.",
        "author":   "Аристотель",
        "source":   "",
        "category": "law",
    },
    {
        "text":     "Истина редко бывает чистой и никогда простой.",
        "author":   "Оскар Уайльд",
        "source":   "",
        "category": "law",
    },
    {
        "text":     "Дайте мне шесть строчек, написанных рукой самого честного человека, "
                    "и я найду в них что-нибудь, за что его можно повесить.",
        "author":   "Кардинал Ришельё",
        "source":   "",
        "category": "law",
    },
    {
        "text":     "В суде побеждает не тот, кто прав. Побеждает тот, кто лучше подготовлен.",
        "author":   "Афоризм американской юридической практики",
        "source":   "",
        "category": "law",
    },

    # ── VII. ДИСЦИПЛИНА И ПРОИЗВОДИТЕЛЬНОСТЬ (8) ─────────────────────────────
    {
        "text":     "Мотивация — это то, что вас запускает. "
                    "Привычка — то, что вас движет.",
        "author":   "Джим Рон",
        "source":   "",
        "category": "discipline",
    },
    {
        "text":     "Не ищите мотивацию. Создайте систему, которая работает без неё.",
        "author":   "Джеймс Клир",
        "source":   "Атомные привычки",
        "category": "discipline",
    },
    {
        "text":     "Вы не поднимаетесь до уровня своих целей. "
                    "Вы опускаетесь до уровня своих систем.",
        "author":   "Джеймс Клир",
        "source":   "Атомные привычки",
        "category": "discipline",
    },
    {
        "text":     "Дисциплина — это мост между целями и достижениями.",
        "author":   "Джим Рон",
        "source":   "",
        "category": "discipline",
    },
    {
        "text":     "Труднее всего начать действовать. "
                    "Всё остальное зависит только от настойчивости.",
        "author":   "Амелия Эрхарт",
        "source":   "",
        "category": "discipline",
    },
    {
        "text":     "Средний человек работает достаточно, чтобы не быть уволенным. "
                    "Средняя компания платит достаточно, чтобы сотрудник не уволился.",
        "author":   "Джордж Карлин",
        "source":   "",
        "category": "discipline",
    },
    {
        "text":     "Чем больше я тренируюсь, тем удачливее становлюсь.",
        "author":   "Гэри Плейер",
        "source":   "",
        "category": "discipline",
    },
    {
        "text":     "Профессионал — это любитель, который не бросил.",
        "author":   "Ричард Бах",
        "source":   "",
        "category": "discipline",
    },

    # ── VIII. ДЕНЬГИ, КАПИТАЛ, ВЛАСТЬ (6) ────────────────────────────────────
    {
        "text":     "Правило номер один: никогда не теряй деньги. "
                    "Правило номер два: никогда не забывай правило номер один.",
        "author":   "Уоррен Баффет",
        "source":   "",
        "category": "money",
    },
    {
        "text":     "Время — более ценный ресурс, чем деньги. "
                    "Потерянные деньги можно вернуть, потерянное время — нет.",
        "author":   "Майкл Лебёф",
        "source":   "",
        "category": "money",
    },
    {
        "text":     "Богатые люди строят сети. Все остальные ищут работу.",
        "author":   "Роберт Кийосаки",
        "source":   "",
        "category": "money",
    },
    {
        "text":     "Деньги — это просто инструмент. Они приведут вас туда, куда вы хотите, "
                    "но не заменят вас в качестве водителя.",
        "author":   "Айн Рэнд",
        "source":   "",
        "category": "money",
    },
    {
        "text":     "Власть — это не то, что вам дают. Это то, что у вас забирают.",
        "author":   "Мао Цзэдун",
        "source":   "",
        "category": "money",
    },
    {
        "text":     "Тот, кто контролирует информацию, контролирует власть.",
        "author":   "Фрэнсис Бэкон",
        "source":   "Знание — сила",
        "category": "money",
    },

    # ── IX. ПСИХОЛОГИЯ УСПЕХА И МЫШЛЕНИЕ (8) ─────────────────────────────────
    {
        "text":     "Вы не можете изменить то, с чем не готовы встретиться лицом к лицу.",
        "author":   "Джеймс Болдуин",
        "source":   "",
        "category": "mindset",
    },
    {
        "text":     "Если вы думаете, что справитесь — вы правы. "
                    "Если думаете, что не справитесь — вы тоже правы.",
        "author":   "Генри Форд",
        "source":   "",
        "category": "mindset",
    },
    {
        "text":     "Разум — это всё. Вы становитесь тем, о чём думаете.",
        "author":   "Будда",
        "source":   "",
        "category": "mindset",
    },
    {
        "text":     "Проблема не в проблеме. Проблема в вашем отношении к проблеме.",
        "author":   "Карл Юнг",
        "source":   "",
        "category": "mindset",
    },
    {
        "text":     "Человек, у которого есть «зачем», выдержит почти любое «как».",
        "author":   "Фридрих Ницше",
        "source":   "",
        "category": "mindset",
    },
    {
        "text":     "Самая большая тюрьма, в которой живут люди — "
                    "это страх того, что думают другие.",
        "author":   "Дэвид Айк",
        "source":   "",
        "category": "mindset",
    },
    {
        "text":     "Боль временна. Сдаться длится вечно.",
        "author":   "Лэнс Армстронг",
        "source":   "",
        "category": "mindset",
    },
    {
        "text":     "Не жалуйтесь на то, что происходит. "
                    "Это отнимает энергию от изменений.",
        "author":   "Тони Роббинс",
        "source":   "",
        "category": "mindset",
    },

    # ── X. КОММУНИКАЦИЯ И ПРИСУТСТВИЕ (8) ────────────────────────────────────
    {
        "text":     "Самое важное в коммуникации — услышать то, что не было сказано.",
        "author":   "Питер Друкер",
        "source":   "",
        "category": "communication",
    },
    {
        "text":     "Говорите только тогда, когда это улучшает тишину.",
        "author":   "Марк Твен",
        "source":   "",
        "category": "communication",
    },
    {
        "text":     "Речь — серебро, молчание — золото, "
                    "в переговорах же молчание — бриллиант.",
        "author":   "Томас Карлейль",
        "source":   "Адаптация",
        "category": "communication",
    },
    {
        "text":     "Тот, кто слушает — управляет разговором.",
        "author":   "Афоризм переговорной школы",
        "source":   "",
        "category": "communication",
    },
    {
        "text":     "Простота — высшая степень сложности.",
        "author":   "Леонардо да Винчи",
        "source":   "",
        "category": "communication",
    },
    {
        "text":     "Если вы не можете объяснить это просто — "
                    "вы не понимаете это достаточно хорошо.",
        "author":   "Альберт Эйнштейн",
        "source":   "",
        "category": "communication",
    },
    {
        "text":     "Слова имеют вес только тогда, когда за ними стоят действия.",
        "author":   "Конфуций",
        "source":   "",
        "category": "communication",
    },
    {
        "text":     "Человека можно убедить только тогда, когда он чувствует, "
                    "что его поняли.",
        "author":   "Карл Роджерс",
        "source":   "",
        "category": "communication",
    },

    # ── XI. ЭКСТРЕМАЛЬНЫЕ И БОЕВЫЕ КОНТЕКСТЫ (7) ─────────────────────────────
    {
        "text":     "Под давлением вы не поднимаетесь до своих ожиданий — "
                    "вы падаете до своего уровня подготовки.",
        "author":   "Navy SEALs",
        "source":   "Стандарт спецназа ВМС США",
        "category": "extreme",
    },
    {
        "text":     "Кто не рискует — тот не пьёт шампанского.",
        "author":   "Русская поговорка",
        "source":   "",
        "category": "extreme",
    },
    {
        "text":     "Атакуй когда враг не ожидает, появись там, где тебя не ждут.",
        "author":   "Сунь-цзы",
        "source":   "Искусство войны",
        "category": "extreme",
    },
    {
        "text":     "Если противник превосходит тебя в силе — измотай его. "
                    "Если равен — избегай прямого столкновения.",
        "author":   "Сунь-цзы",
        "source":   "",
        "category": "extreme",
    },
    {
        "text":     "Удача благоволит подготовленным.",
        "author":   "Луи Пастер",
        "source":   "",
        "category": "extreme",
    },
    {
        "text":     "Я не проиграл 10 000 раз. Я нашёл 10 000 способов, которые не работают.",
        "author":   "Томас Эдисон",
        "source":   "",
        "category": "extreme",
    },
    {
        "text":     "Либо найди путь, либо создай его.",
        "author":   "Ганнибал Барка",
        "source":   "",
        "category": "extreme",
    },
]

TOTAL_QUOTES = len(QUOTES)  # 78 (77 + 1 bonus communication quote added above)


# ─── Core slot logic ──────────────────────────────────────────────────────────

def get_current_slot_index(now: datetime | None = None) -> int:
    """Return the index of the current 6-hour slot (0-3) based on UTC hour."""
    if now is None:
        now = datetime.now(timezone.utc)
    return now.hour // 6


def get_current_quote_index(now: datetime | None = None) -> int:
    """Return the deterministic quote index for the current 6-hour window."""
    if now is None:
        now = datetime.now(timezone.utc)
    day_number = int(now.timestamp()) // 86400
    slot = now.hour // 6
    return (day_number * 4 + slot) % TOTAL_QUOTES


def get_next_slot_utc(now: datetime | None = None) -> datetime:
    """Return the UTC datetime when the next 6-hour slot starts."""
    if now is None:
        now = datetime.now(timezone.utc)
    current_slot = now.hour // 6
    next_slot_hour = (current_slot + 1) * 6  # 6, 12, 18, or 24 (= 00 next day)
    from datetime import timedelta
    next_dt = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if next_slot_hour < 24:
        next_dt = next_dt.replace(hour=next_slot_hour)
    else:
        next_dt = (next_dt + timedelta(days=1)).replace(hour=0)
    return next_dt


def get_navigator_response(now: datetime | None = None) -> dict:
    """Build the full navigator API response for the current window."""
    if now is None:
        now = datetime.now(timezone.utc)

    idx = get_current_quote_index(now)
    quote = QUOTES[idx]
    next_change = get_next_slot_utc(now)
    seconds_remaining = int((next_change - now).total_seconds())

    return {
        "index":             idx,
        "total":             TOTAL_QUOTES,
        "text":              quote["text"],
        "author":            quote["author"],
        "source":            quote["source"],
        "category":          quote["category"],
        "category_label":    CATEGORY_LABELS.get(quote["category"], quote["category"]),
        "slot":              now.hour // 6,          # 0–3
        "next_change_at":    next_change.isoformat(),
        "seconds_remaining": max(0, seconds_remaining),
    }
