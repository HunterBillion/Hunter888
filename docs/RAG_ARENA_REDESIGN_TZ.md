# ТЗ: Переработка RAG-логики Арены квизов
**Дата**: 2026-04-18
**Автор**: audit review
**Статус**: ПРОЕКТ — требует одобрения user'а перед реализацией

---

## 0. Контекст

Пользовательский фидбек по `/pvp` → вкладка «Знания 127-ФЗ»:
1. **Странные вопросы** — нет связи с реальной практикой коллектора/юриста
2. **Лоялная оценка** ("привет" → ✓ Верно) — ✅ **УЖЕ ЗАКРЫТО** garbage-detector'ом (2026-04-18)
3. **Нет прогрессии сложности** — одинаковые вопросы от начала до конца
4. **Нет сюжетной связки** — каждый вопрос изолирован
5. **Сухая подача** — просто текст, без драматургии и погружения

Цель: превратить «квиз с вопросами» в **игровой опыт расследования**, где каждый вопрос — шаг в деле.

---

## 1. Текущая архитектура (что уже есть)

```
[knowledge_quiz.py]
    │
    ├─ generate_question() ───► Strategy chain:
    │     1. BlitzQuestionPool (0 LLM, fast)
    │     2. question_templates from RAG chunk (0 LLM)
    │     3. LLM + RAG context (2-5s)
    │     4. Hardcoded fallback
    │
    ├─ evaluate_answer() ─────► 
    │     0. Garbage detector (NEW 2026-04-18) ✅
    │     1. Blitz keyword match
    │     2. common_errors pre-check
    │     3. LLM judge + RAG
    │     4. Cross-check (anti-hallucination)
    │
    └─ AI_EXAMINER_PROMPT — общий system-prompt
```

**Сильные стороны**:
- RAG уже работает (4378 legal_document + 375 chunks с 100% эмбеддинг-покрытием)
- BlitzQuestionPool быстр (<5ms)
- Anti-hallucination cross-check через common_errors уже реализован
- 10 категорий + 2 personality (Профессор / Следопыт)

**Что сломано**:
- `generate_question` не помнит контекст предыдущих — каждый вопрос как первый
- Нет **нарратива дела** — нет персонажа-должника, нет обстоятельств
- `difficulty` растёт линейно по номеру вопроса, но сам контент не усложняется
- LLM пишет generic "Сгенерируй вопрос по 127-ФЗ" — отсюда сухость

---

## 2. Предлагаемая архитектура (5 модулей)

### 2.1. Модуль A: CaseGenerator — нарратив дела
**Файл**: `apps/api/app/services/quiz_case_generator.py` (НОВЫЙ)

При старте сессии (`themed` или `free_dialog` mode) генерирует **дело-контекст** один раз:

```python
@dataclass
class QuizCase:
    case_id: str                      # "CASE-2026-0042"
    debtor_name: str                  # "Иван Петрович Крылов, 47 лет"
    debtor_occupation: str            # "бывший ИП, салон красоты"
    debt_amount: int                  # 820_000
    creditors: list[str]              # ["Сбербанк", "МТС-банк", "2 микрозайма"]
    trigger_event: str                # "закрытие бизнеса в пандемию"
    complicating_factors: list[str]   # ["брачный договор", "квартира в залоге"]
    case_difficulty: str              # "simple" | "tangled" | "adversarial"
    narrative_hook: str               # "Кредиторы готовят оспаривание сделок..."
```

Это **один раз** делается LLM-запросом в начале (или берётся из 50-100 заготовленных кейсов в БД — ещё быстрее). Кейс передаётся во все следующие `generate_question` и `evaluate_answer`.

**Эффект для user'а**:
- **Первое сообщение**: «Дело №2026-0042. Должник — Иван Крылов, 47 лет, бывший владелец салона красоты, долг 820 000₽. Кредиторы: Сбербанк, МТС, 2 МФО. Триггер — пандемия. Есть осложнение: брачный договор...»
- Каждый следующий вопрос связан с этим делом.

### 2.2. Модуль B: StoryBeats — прогрессия сюжета
**Файл**: `apps/api/app/services/quiz_story_beats.py` (НОВЫЙ)

Каждое «дело» проходит через **фазы-биты**:

```python
BEATS = [
    ("intake", 1, 2),        # Вопросы 1-2: приём заявления
    ("documents", 3, 4),     # 3-4: проверка документов
    ("obstacles", 5, 6),     # 5-6: возражения кредиторов / осложнения
    ("property", 7, 8),      # 7-8: судьба имущества
    ("outcome", 9, 10),      # 9-10: последствия / план реструктуризации
]
```

`generate_question` получает текущий `beat` → вопрос тематически соответствует фазе:
- Бит 1 (intake): *"Какие два обязательных документа должник подаёт вместе с заявлением в суд?"*
- Бит 3 (documents): *"Сбербанк прислал копию кредитного договора с подделанной подписью супруги. Как это меняет ход дела?"*
- Бит 7 (property): *"У должника есть доля в квартире (50%) и старый автомобиль. Что из этого будет реализовано?"*

**Эффект**: вопросы **следуют друг за другом логически**, user погружается в дело.

### 2.3. Модуль C: DifficultyRamp — реальная прогрессия
**Файл**: `apps/api/app/services/quiz_difficulty_ramp.py` (НОВЫЙ)

Прогрессия не по `question_number`, а по **типу вопроса**:

```python
LADDER = [
    ("factoid",   1, "Назови порог суммы долга для банкротства физлица"),      # 500K
    ("procedure", 2, "Какая статья 127-ФЗ вводит фигуру финуправляющего?"),     # 213.9
    ("edge_case", 3, "Должник получил наследство после подачи — что будет?"),
    ("multi",     4, "Назови 3 условия оспаривания сделок должника"),
    ("strategic", 5, "Суд отказал в списании. Какие у должника есть пути?"),
]
```

Тип вопроса влияет на LLM-prompt, скоринг, объяснение в feedback.

**Эффект**: сложность нарастает **концептуально**, не просто «тот же уровень, но дольше».

### 2.4. Модуль D: PresentationLayer — драматургия
**Файл**: `apps/api/app/services/quiz_presentation.py` (НОВЫЙ)

Каждый вопрос оборачивается в **story-beat frame** в зависимости от personality:

```python
def wrap_question(
    q: QuizQuestion,
    case: QuizCase,
    personality: Literal["professor", "detective", "blitz"],
) -> str:
    if personality == "detective":
        return (
            f"🔍 ДЕЛО-{case.case_id}, ДЕНЬ {q.question_number}\n\n"
            f"{case.debtor_name}. Сидит напротив, держится напряжённо. "
            f"В папке — кредитный договор Сбербанка, копия, {case.debt_amount}₽.\n\n"
            f"Улика №{q.question_number}: {q.question_text}\n\n"
            f"💭 Что это нам даёт?"
        )
    elif personality == "professor":
        return (
            f"📚 КАЗУС №{q.question_number}\n\n"
            f"Дано: {case.debtor_name}, долг {case.debt_amount}₽, "
            f"триггер — {case.trigger_event}.\n\n"
            f"Задача: {q.question_text}"
        )
    else:  # blitz
        return f"⚡ {q.question_number}/{q.total}  {q.question_text}"
```

**Эффект**: сухой вопрос *«Назови статью про финуправляющего»* превращается в:
> 🔍 ДЕЛО-2026-0042, ДЕНЬ 3
> Иван Крылов сидит напротив, держится напряжённо. В папке — кредитный договор Сбербанка, копия, 820 000₽.
> Улика №3: без кого ни одна процедура банкротства физлица через суд не обходится?
> 💭 Назови эту ключевую фигуру и статью закона.

### 2.5. Модуль E: SessionMemory — связность
**Файл**: `apps/api/app/services/quiz_session_memory.py` (НОВЫЙ)

Redis-хранилище состояния сессии:

```
session:{id}:case       → QuizCase JSON
session:{id}:beat       → "intake" | "documents" | ...
session:{id}:answers    → [{q, a, correct, article}, ...]
session:{id}:ladder_idx → 0-4 (DifficultyRamp position)
```

Каждый `generate_question` читает state, следующий вопрос учитывает:
- Что user УЖЕ ответил правильно (не спрашиваем то же самое)
- На чём споткнулся (усложняем именно это)
- Сколько бит пройдено

---

## 3. План реализации (3 этапа)

### Этап 1 (1 session ≈ 2-3 часа): MVP
- [ ] Создать `QuizCase` + 20 захардкоженных кейсов в JSON (не LLM-generated для старта)
- [ ] `wrap_question` с 2 personality (professor / detective)
- [ ] Встроить в существующий `generate_question` — добавить `case` параметр
- [ ] Redis `session:{id}:case` storage

### Этап 2 (1 session): Прогрессия + Memory
- [ ] `StoryBeats` — 5 фаз-битов, mapping question_number → beat
- [ ] `DifficultyRamp` — 5-step ladder, вместо `question_number / total * 5`
- [ ] `SessionMemory` — tracking ответов, адаптация следующего вопроса под weak-area

### Этап 3 (1 session): LLM-case generation + polish
- [ ] `CaseGenerator` через LLM — 50+ динамических кейсов вместо 20 захардкоженных
- [ ] Edge-case questions (наследство, оспаривание сделок, мошенничество)
- [ ] Integration tests: полный сценарий с 10 вопросами по делу

---

## 4. Ожидаемые метрики

| Метрика | Сейчас | После |
|---|---|---|
| Средняя длина сессии | ~3-5 вопросов (user выходит от скуки) | 10 вопросов (завершённое дело) |
| Engagement (повторные сессии/неделю) | ~1.2 | ~3-4 |
| "Плохое чувство" (user feedback) | ⚠️ высоко | цель: низко |
| Completion rate (10/10 вопросов) | ~15% | цель: 50%+ |

---

## 5. Что НЕ меняем (сохраняем инвестиции)

- ✅ `retrieve_legal_context` — RAG retrieval остаётся
- ✅ `BlitzQuestionPool` — blitz-mode остаётся как есть
- ✅ `common_errors` cross-check — anti-hallucination остаётся
- ✅ Garbage-answer detector (новый) — базовая защита
- ✅ 10 категорий (eligibility, procedure, ...) — остаются, становятся фильтром по БИТУ

---

## 6. Вопросы к user'у перед стартом

1. **Захардкоженные кейсы или LLM-generated с первого дня?** MVP проще с захардкоженными 20 кейсами — быстрее и предсказуемее. LLM-generated можно добавить на этапе 3.
2. **Длина сессии**: 10 вопросов достаточно или тебе нужно **15-20** для полного погружения?
3. **Голос для чтения дела**: подключить ElevenLabs TTS чтобы Следопыт/Профессор **говорил** первое сообщение с делом? Это +engagement, но больше latency.
4. **Жанры personality**: только Следопыт+Профессор или добавить 3-й (например, «Адвокат дьявола» — агрессивный судебный pressure)?

---

## Ссылки

- Текущий код: [knowledge_quiz.py](../apps/api/app/services/knowledge_quiz.py) — 1117 строк
- RAG-источник: [rag_legal_v2.py](../apps/api/app/services/rag_legal_v2.py)
- UI квиза: [pvp/quiz/[sessionId]/page.tsx](../apps/web/src/app/pvp/quiz/[sessionId]/page.tsx)
- Garbage-detector fix (2026-04-18): [knowledge_quiz.py:369-416](../apps/api/app/services/knowledge_quiz.py)
