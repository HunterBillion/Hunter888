# ТЗ-6 — Pre-pilot performance optimization

> **Статус:** проектируется. Дата: 2026-04-29.
> **Триггер:** пользователь сообщил что policy/persona slot lock «подлагивает иногда тупит» в живом звонке. Аудит подтвердил: synchronous LLM call per AI message + sync DB writes добавляют 800-1500ms latency на каждый turn.

## 1. Что тормозит — конкретно

### 1.1 conversation_audit_hook

[apps/api/app/services/conversation_audit_hook.py](apps/api/app/services/conversation_audit_hook.py) — **синхронный LLM-вызов** на каждой реплике AI:
1. Классифицирует `policy_violations` (6 типов из TZ-4 §10)
2. Записывает violations через `lock_slot` / `record_conflict_attempt`
3. Эмитит `DomainEvent` через canonical writer

Время: 500-1000ms LLM + 200-500ms DB. Блокирует ответ AI пока не закончится.

### 1.2 runtime_metrics in-memory

[apps/api/app/services/runtime_metrics.py](apps/api/app/services/runtime_metrics.py) — `defaultdict(int)` в памяти процесса. Сбрасывается на каждом рестарте api. Дашборд /dashboard/system/runtime-metrics показывает «последние N с момента старта пода», что вводит в заблуждение оператора.

### 1.3 persona_memory.lock_slot

При каждом совпадении slot'а (TZ-4 §9):
- `SELECT FOR UPDATE` на `memory_personas`
- `UPDATE confirmed_facts SET ... version=version+1`
- `INSERT INTO domain_events ...`

Сейчас всё синхронно в одной транзакции. Под нагрузкой 5+ параллельных сессий вызывает row-level lock contention.

## 2. Решение

### 2.1 Async write-behind для audit_hook

Файл: `app/services/audit_hook_queue.py` (новый)

- В call-flow `conversation_audit_hook.process_reply(...)` **больше не делает LLM-вызов**
- Вместо этого: добавляет `(session_id, message_id, reply_text)` в Redis stream `audit_hook:queue`
- Worker `app/workers/audit_hook_worker.py` (новый процесс или внутри scheduler) читает stream, делает LLM-классификацию и запись
- WS-канал получает live-update когда обработка закончена (~1-2 сек спустя ответа AI)

**Эффект:** AI-ответ не блокируется audit hook'ом. Пользователь видит violation badge с задержкой 1-2 сек, но это **намного** лучше чем задержка ответа AI на 1 сек.

### 2.2 Persistent runtime metrics

Файл: `app/services/runtime_metrics_redis.py` (replacement)

- `defaultdict(int)` → Redis `HINCRBY` с TTL 30 дней
- Backfill при старте процесса не нужен (счётчики живут в Redis независимо от api пода)
- Дашборд читает напрямую из Redis (один HGETALL per panel)

**Plus:** добавить **persistent counter** из `domain_events` агрегата за последние 24h — реальный «сколько всего сегодня» рядом с «сколько с момента старта процесса».

### 2.3 lock_slot deferred

Большая часть `lock_slot` вызовов происходит из audit_hook (через `record_conflict_attempt`). С async audit hook (2.1) они автоматически уходят из критического пути.

Оставшиеся синхронные вызовы (в момент обнаружения нового факта) — оптимизировать batched commit: накопить несколько `lock_slot` за turn, сбросить одним UPDATE.

## 3. Acceptance criteria

- [ ] AI-reply latency ≤ 200ms median (без conversation_audit_hook на критическом пути) — измерять через Prometheus histogram
- [ ] Violation badge на FE появляется ≤ 2 секунды после AI-reply
- [ ] Дашборд `/dashboard/system/runtime-metrics` показывает корректные числа после рестарта api контейнера (Redis-backed)
- [ ] 10 параллельных сессий не вызывают row-level lock contention в `memory_personas` (тест с `asyncio.gather`)

## 4. Тесты

- `test_audit_hook_queue.py` — async enqueue/dequeue, no message loss, ordering preserved per session
- `test_runtime_metrics_redis.py` — counters survive process restart
- `test_lock_slot_concurrent.py` — 10 parallel writers → version monotonic, no lost updates
- Load test: 50 RPS на /ws/training/{session_id}, p95 reply latency ≤ 500ms

## 5. Migration

- Phase 1 (1 неделя): развернуть Redis-metrics параллельно с in-memory; дашборд показывает оба числа; собираем сравнение.
- Phase 2 (1 неделя): переключить дашборд на Redis-only; in-memory оставить как backup.
- Phase 3 (1 неделя): развернуть audit_hook worker; conversation_audit_hook переключается с sync на async по feature flag.
- Phase 4: feature flag → on by default. Удалить sync code path.

## 6. Риски

1. **Redis недоступен** → metrics дашборд пуст. Митигируется: fallback на in-memory + alert в /dashboard/system.
2. **Worker отстаёт** от очереди → violation badges с большим delay. Митигируется: scaling worker (multiple consumer instances on same Redis stream).
3. **Lost messages** при downscale worker'а → используем Redis Streams (consumer groups, ACK).

## 7. Объём работы

- Backend: 4-5 дней (Redis metrics + audit worker + tests)
- Прод-обкатка по фазам: 4 недели
- Итого до полного перехода: **~5 недель**

## 8. Какой эффект ожидается на пилоте

До TZ-6:
- AI отвечает за 2-3 секунды
- Часто voice mode «затыкается» при детектировании violation
- Дашборд показывает `Finalize=2` вне зависимости от прошедших дней

После TZ-6:
- AI отвечает за 0.6-1.0 секунды
- Voice mode плавный
- Дашборд показывает корректные числа за последние 24h
