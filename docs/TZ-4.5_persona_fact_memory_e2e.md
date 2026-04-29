# ТЗ-4.5 — Persona Memory: end-to-end factual memory

> **Статус:** проектируется. Последователь TZ-4 §9 (D3).
> **Дата создания:** 2026-04-29. Rev. 2: 2026-04-29 после deep code audit.
> **Зависимости:** TZ-4 D3 (persona_memory сервис уже есть), TZ-1 §15.1 (correlation_id NOT NULL).
> **Триггер:** аудит 2026-04-29 показал что AI не помнит что менеджер ему сказал между звонками.

## 1. Контекст и проблема (rev. 2 — точные данные из audit)

TZ-4 D3 заложил **больше чем я первоначально думал**. Вот что **уже** работает:

| Слой | Реализовано | File:line |
|---|---|---|
| ORM-схема `confirmed_facts JSONB` | ✅ | `models/persona.py:121` |
| Writer-функция `lock_slot()` (полная, с optimistic concurrency, идемпотентная) | ✅ **НО dead-code** | `services/persona_memory.py:411-504` |
| Юнит-тесты `lock_slot` | ✅ | `tests/test_persona_memory.py:386,411,433,440` |
| AST-guard «никто не пишет confirmed_facts вне persona_memory» | ✅ | `tests/test_persona_invariants.py` |
| API view `GET /persona/{lead_client_id}` отдаёт facts наружу | ✅ | `api/persona_view.py:139` |
| Pseudo-registry slot codes (14 штук) | ✅ **но не shared** | `services/conversation_policy_engine.py:316-331` |
| Reactive guard `asked_known_slot_again` (постфактум ловит переспросы) | ✅ | `services/conversation_policy_engine.py:291-339` |
| Counter `record_conflict_attempt` (identity drift) | ✅ | `services/persona_memory.py` |

Что **НЕ реализовано** (критичные gaps):

| Слой | Статус | Что нужно |
|---|---|---|
| **Caller** для `lock_slot()` в runtime | ❌ | Вся writer-функция dead-code; никто её не зовёт после реплик |
| **Fact extraction** из conversation | ❌ | Нет LLM-классификатора, нет regex-extractor, нет session-end hook |
| **Reader** `confirmed_facts` в `_build_system_prompt` | ❌ | Сигнатура `_build_system_prompt(character_prompt, guardrails, emotion_state, scenario_prompt)` не имеет persona-параметра. Нет placeholder `{persona_facts}` в шаблонах |
| **Shared slot registry** | ❌ | Реестр размазан в одной локальной переменной `triggers` |
| **Forget mechanism** | ❌ | Нет timestamp на фактах, нет TTL, нет API `unlock_slot` |
| **End-to-end test** «session 1 пишет → session 2 читает» | ❌ | Нет |

**Готовность:** 25-30%. Фундамент D3 прочный, недостающий слой — **верх пирамиды** (extractor + prompt-injector + shared registry).

Поэтому AI каждый раз начинает с чистого листа, даже если 5 минут назад менеджер сказал «меня зовут Дмитрий, у меня компания Альфа».

## 2. Цели

1. **Записывать** факты о менеджере **из** диалога: имя, регион, тип бизнеса, оборот, кол-во сотрудников, ключевые "болевые точки" — то что менеджер сам озвучил.
2. **Читать** их в системном промпте AI следующего звонка к тому же `lead_client_id`, чтобы AI вёл себя как **знакомый** собеседник, не переспрашивал заново.
3. **Защитить** от ложных фактов (manager сболтнул в шутку → не запоминать).
4. **Защитить** от устаревания (факт записали полгода назад → пометить уверенность ↓).

## 3. Архитектурный план

### 3.1 Fact extraction layer (новый)

Файл: `app/services/persona_fact_extractor.py`

- После каждой реплики менеджера → асинхронный LLM-вызов (Haiku, дешёвый и быстрый).
- Вход: последние 4 реплики (сliding window) + текущий `confirmed_facts` (чтобы не дублировать).
- Выход: `list[Fact]` где `Fact = {slot_key: str, value: str, confidence: float, justification: str}`.
- **Не блокирует** ответ AI — пишется в фоне после `await ws.send_json(...)`.

### 3.2 Fact validation gate

Перед записью:
- `confidence >= 0.7` обязательно
- `justification` должен **процитировать** реплику менеджера (грубая защита от галлюцинаций)
- Уже зафиксированный slot не перезаписывается без `confidence >= 0.9` (anti-flip-flop)

### 3.3 Slot registry (новый файл)

`app/services/persona_slots.py`:

```python
PERSONA_SLOTS = {
    "full_name": {"type": "string", "max_len": 120, "stable": True},
    "city": {"type": "string", "max_len": 80, "stable": True},
    "company_name": {"type": "string", "max_len": 120, "stable": True},
    "company_size": {"type": "enum", "values": ["solo", "small", "mid", "large"], "stable": False},
    "industry": {"type": "string", "stable": True},
    "pain_points": {"type": "list[string]", "max_items": 5, "stable": False},
    # ... ~12-15 слотов
}
```

`stable=True` — слот меняется редко (имя, город). `stable=False` — может эволюционировать (масштаб бизнеса, болевые точки).

### 3.4 Prompt injection

В `_build_system_prompt` ([llm.py:621](apps/api/app/services/llm.py:621)) после `character_prompt` — добавить блок:

```
═══ ЧТО ТЫ УЖЕ ЗНАЕШЬ О СОБЕСЕДНИКЕ (из прошлых звонков) ═══
{rendered_persona_facts}
Веди себя как ЗНАКОМЫЙ — не переспрашивай эти данные. Можно ССЫЛАТЬСЯ
на них естественно ("Помню, ты говорил про Альфу..."), но не пересказывать.
═══════════════════════════════════════════════════════════
```

`rendered_persona_facts` — человекочитаемый формат, не JSON.

### 3.5 Forget mechanism

Если менеджер **поправил** факт (например, "не Альфа, я там больше не работаю — теперь Бета") — extraction должен это распознать и:
- Старый факт пометить `expired: true` (не удалять — нужен audit trail)
- Новый факт добавить с `confidence > 0.8`
- В промпт идёт **только active**

## 4. Acceptance criteria

- [ ] Менеджер говорит «меня зовут Иван» → следующий звонок к тому же `lead_client_id`: AI обращается «Иван».
- [ ] Менеджер не подтверждает имя в первом звонке (никто не назвался) → AI **спрашивает** имя, не пишет ничего в memory.
- [ ] Тестер врёт ("я Стив Джобс") → confidence низкий, slot не записывается.
- [ ] Менеджер исправляется ("я не Иван, я Алексей") → старая запись помечается expired, новая пишется.
- [ ] 10 параллельных сессий с одним и тем же `lead_client_id` → optimistic concurrency не теряет данные (TZ-4 §9.2.5 invariant).
- [ ] Latency added per turn ≤ 200ms (extraction в фоне).

## 5. Тесты

- `test_persona_fact_extractor.py` — извлечение из синтетических диалогов (10+ сценариев)
- `test_persona_slot_registry.py` — slot validation
- `test_persona_prompt_injection.py` — корректный рендеринг facts в промпт
- `test_persona_concurrent_writes.py` — race conditions
- AST-guard расширить: `confirmed_facts` пишется только из `persona_fact_extractor.commit_facts()`

## 6. Migration / data backfill

Новых таблиц не требуется. Колонка `confirmed_facts` уже есть.

Опционально: backfill с момента запуска фичи — пройти по `messages` таблице последних N дней, прогнать через extractor пакетом. Не критично для запуска.

## 7. Риски

1. **Стоимость LLM**: ~10-15 reply turns × Haiku вызов = $0.001-0.005 за звонок. Приемлемо.
2. **Latency на медленной сети**: extraction async, но `lock_slot` синхронный. Нужно тестировать на 4G.
3. **Hallucinations** в extraction: митигируется validation gate (`confidence + justification quote`).
4. **GDPR / 152-ФЗ**: `confirmed_facts` хранит PII. Нужен явный consent flow и право на удаление. Уже есть `audit_log` — добавить «forget all facts about user X» команду.

## 8. Объём работы

- Backend: 4-5 дней (extractor + slot registry + prompt injection + tests + AST guard)
- A/B пилот: 2 дня (10 пилотных пользователей до/после)
- Документация в /dashboard/methodology: 1 день

Итого: **~7 дней** до запуска в warn-only, потом 1-2 недели A/B перед полным включением.

## 9. Связанные изменения

После TZ-4.5 имеет смысл:
- Включить TZ-4 §10 conversation_policy_engine `enforce_active=true` на slot `asked_known_slot_again` (после прогретой памяти это перестаёт быть false-positive).
- Расширить `/clients/[id]/memory` на FE (manager surface, не только admin).
