# ТЗ-6 — Pre-pilot performance optimization

> **Статус:** проектируется. Дата: 2026-04-29.
> **Триггер:** пользователь сообщил «policy/persona slot lock подлагивает иногда тупит» в живом звонке.
>
> ⚠️ **Важно (rev. 2 от 2026-04-29 после deep audit):** первая редакция этого ТЗ (commit 7c4eb8e) ошибочно атрибутировала задержку к `conversation_audit_hook` (предполагая sync LLM call) и `lock_slot` (предполагая SELECT FOR UPDATE). **Аудит кода показал что это НЕ так:**
>
> - `conversation_audit_hook` — **только regex/CPU**, ни одного LLM-вызова, latency ~10-20ms
> - `lock_slot` — **optimistic concurrency** через `version` column, БЕЗ pessimistic locks, latency 1-2 SQL queries
>
> Реальный источник задержки — другой. Эта rev. 2 переписана с правильным root cause.

## 1. Что реально тормозит — confirmed by audit

### 1.1 `detect_triggers` — sync LLM call в hot path

`apps/api/app/ws/training.py:1677-1685` — на **каждой** реплике AI делается `await detect_triggers(...)`. Это LLM-вызов классификатора (определяет триггеры эмоций: empathy/facts/pressure/...).

Сам комментарий в коде ([ws/training.py:1673-1675](apps/api/app/ws/training.py:1673)) предупреждает:
```python
# Skip LLM-based trigger detection when using local provider (single-concurrent)
# to avoid 60+s latency per message (character response + trigger + trap = 3 serial LLM calls)
_skip_llm_detection = settings.local_llm_enabled and not llm_result.is_fallback
```

То есть **в коде уже есть знание про 3 serial LLM calls = 60+ секунд latency**. Только обходится через `local_llm_enabled` флаг (Mac Mini), что подходит для dev, но в проде с Gemini/Claude/GPT — `_skip_llm_detection = False`, и пользователь получает блокирующий LLM-вызов на каждой реплике.

**Стек блокирующих LLM-вызовов на один turn:**
1. `generate_response()` — основная генерация ответа AI (~1-3 сек)
2. `detect_triggers()` — классификатор триггеров (~0.8-2 сек)  ← **этот**
3. `trap_engine` (опционально) — если активен trap-сценарий (~0.5-1 сек)

Итого 2.3-6 секунд последовательно, прежде чем reply дойдёт до фронта.

### 1.2 `runtime_metrics` — in-memory only

`apps/api/app/services/runtime_metrics.py:38-58`:
```python
_blocked_starts: dict[...] = defaultdict(int)
_finalize: dict[...] = defaultdict(int)
_followup_gap: dict[...] = defaultdict(int)
```

Сбрасывается на рестарт api-контейнера. Endpoint `apps/api/app/api/client_domain_ops.py:270-326` (`GET /admin/runtime/metrics`) рендерит Prometheus text format напрямую из in-memory dict. Если Prometheus scraper стоит (`/api/metrics` → Prometheus → Grafana) — счётчики агрегируются на уровне Prometheus и переживают рестарт. Если FE дашборд `/dashboard/system` читает endpoint **напрямую** (без Prometheus middleware) — счётчики «врут» после каждого деплоя.

**Проверить:** реально ли `/dashboard/system/RuntimeMetricsPanel` ходит на `GET /admin/runtime/metrics` напрямую или есть Prometheus-aggregation между ними.

### 1.3 `conversation_audit_hook` — НЕ источник задержки (опровергнуто)

Аудит показал: hook делает только 2 SELECT (snapshot + persona) + regex pattern matching + опциональный INSERT в domain_events + WS enqueue. Реальный latency ~10-20ms. **Не приоритет.**

### 1.4 `lock_slot` — НЕ источник задержки (опровергнуто)

Аудит показал: optimistic concurrency через `expected_version` check, без `for_update()`. Caller загружает persona отдельно, `lock_slot` только flush+UPDATE+emit_domain_event. Latency 5-15ms. **Не приоритет.**

## 2. Решение (rev. 2)

### 2.1 Async detect_triggers (главная победа)

Сейчас `await detect_triggers(...)` блокирует поток. Триггеры нужны для:
- Обновления emotion FSM (используется в **следующей** реплике AI)
- Логирования

**Идея:** перенести вызов `detect_triggers` в `asyncio.create_task(...)` ПОСЛЕ того как reply ушёл клиенту по WebSocket'у. Триггеры применятся к следующему turn'у — это семантически корректно (current turn уже завершён).

**Изменение:** [`apps/api/app/ws/training.py:1677`](apps/api/app/ws/training.py:1677):
```python
# Было: блокирует reply
trigger_result = await detect_triggers(...)
emotion_engine.apply_triggers(trigger_result.triggers)

# Станет: reply уходит сразу, триггеры применятся для NEXT reply
await ws.send_json({"type": "character.response", "data": {...}})
asyncio.create_task(_apply_triggers_async(session_id, ...))
```

**Эффект:** 1-2 секунды latency убираются с каждого turn. Звонок становится плавным.

**Риск:** триггеры применяются с лагом одного turn — это может изменить динамику эмоций (раньше было «реактивно тут же»). Митигация: A/B тест с 5 пилотными — оценить не ломается ли тренировка.

### 2.2 Persistent runtime metrics — only if needed

**Сначала проверить** через grep что `RuntimeMetricsPanel.tsx` действительно ходит напрямую на API. Если он использует `/api/metrics` через Prometheus aggregator — задача отсутствует. Если напрямую — мигрировать на Redis HINCRBY + 30-day TTL ИЛИ читать из `domain_events` агрегатом за 24h.

**Эффект:** дашборд показывает реальные числа после рестарта api.

### 2.3 ~~Async write-behind audit_hook~~ — отменено

Первая редакция предлагала это решение. Отменяется как решение несуществующей проблемы.

### 2.4 Background task patterns — что уже есть

В коде уже массово используется `asyncio.create_task()` (event_bus.py:184, scheduler.py:68, RAG, arena audio). Inf для async-task'ов готова — не надо вводить celery/arq.

## 3. Acceptance criteria (rev. 2)

- [ ] AI-reply latency p95 ≤ 1500ms (сейчас, с sync detect_triggers, ~3-5s) — измерять Prometheus histogram перед фиксом и после
- [ ] Voice mode subjectively плавный на 5 пилотных — нет ощущения «AI зависает»
- [ ] Emotion FSM продолжает корректно реагировать (триггеры применяются с задержкой ≤ 1 turn) — проверять через test_emotion_engine.py
- [ ] **Только если нужно:** RuntimeMetricsPanel показывает correct числа после рестарта api

## 4. Тесты (rev. 2)

- `test_detect_triggers_async.py` — триггеры применяются на NEXT turn, не блокируют CURRENT
- `test_emotion_fsm_with_async_triggers.py` — FSM не ломается от lag в 1 turn
- Load test: 50 RPS на /ws/training/{session_id}, p95 ≤ 1500ms

## 5. Migration

Phase 1 (1 неделя): feature flag `async_trigger_detection=false` (default). Включаем для 5 пилотных.
Phase 2 (1 неделя): A/B измерение, если эмоции не ломаются — `async_trigger_detection=true` для всех.
Phase 3: удаление sync code path.

## 6. Объём работы (rev. 2)

- Backend (1 файл `ws/training.py`, 1 файл `_apply_triggers_async`): **0.5 дня**
- Tests + load test: **1 день**
- A/B обкатка: **1-2 недели**

Итого: **~2 дня кода + 2 недели обкатки**. **Намного меньше чем rev. 1 предполагала.**

## 7. Связь с другими ТЗ

- TZ-4.5 (persona memory): добавит **ещё один** sync LLM call (fact extraction). Тоже async, чтобы не складывать задержки.
- Voice-mode (sprint «не звучи как AI»): plata через async pipeline становится возможной.

## 8. Что НЕ делаем

- ~~Redis-streams worker для audit_hook~~ — atтакует несуществующую проблему
- ~~Batch lock_slot UPDATE~~ — в проде нет contention'а

## 9. Что узнал из этого аудита (lesson learned)

**Никогда не доверять spec'у без проверки кода.** Первая редакция TZ-6 базировалась на моих предположениях о том «как обычно тормозят real-time системы», без открытия `conversation_audit_hook.py`. Это привело к 5-недельному плану, атакующему 2 несуществующие проблемы. После реального чтения файла — план сжался до 2 дней.

Применять этот же принцип ко всем будущим spec'ам: **сначала grep + read**, потом план.
