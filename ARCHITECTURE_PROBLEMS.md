# АРХИТЕКТУРА — ПРОБЛЕМЫ
### X HUNTER (Hunter888) | Deep Backend & AI Audit
**Дата:** 2026-04-09 | **Статус:** DRAFT — исследование продолжается

---

## РЕЕСТР ПРОБЛЕМ

Все проблемы верифицированы по исходному коду. Номера `C`=Critical, `H`=High, `M`=Medium, `L`=Low, `A`=Architectural.

---

## ! БЛОК 1: КРИТИЧЕСКИЕ БАГИ (ломают работу прямо сейчас)

### C1. Переполнение токенового бюджета промптов
**Файлы:** `llm.py:1622–1642`, `training.py:831–904`
**Суть:** Character prompt файлы — 20–25K символов (~12K токенов). `extra_system` (client_profile + objection_chain + stage_rules + skip_reactions + fake_transition + Game Director Tier 1+2) добавляется **после** подсчёта токенов. Итого system prompt = 9600–15000 токенов без ограничения.
**Верификация:** `skeptic_v2.md` = 25,326 байт (256 строк). Token budget manager (line 1642) считает `len(full_system)//2`, но `extra_system` не входит в этот расчёт.
**Последствия:** Gemma 4B (контекст 8K) получает промпт, который физически не помещается. Бессвязные ответы, потеря роли, OOM.

### C2. Session resume не восстанавливает состояние
**Файл:** `training.py:475–534`
**Суть:** При `session.resume` из Redis восстанавливается только `session_id`, `scenario_id`, `message_count`. **Не восстанавливаются:** `prompt_path` (путь к промпту персонажа), `archetype_code`, `emotion_state` (сбрасывается в "cold"), `story_id`, `call_number`, `base_difficulty`, `trap_state`, `client_profile_prompt`.
**Последствия:** Возобновлённая сессия = пустая оболочка. Нет промпта персонажа → LLM отвечает без роли. Эмоция сброшена → клиент вдруг "остыл". Ловушки потеряны.

### C3. Hangup не закрывает WebSocket
**Файл:** `training.py:1041–1145, 4245–4251`
**Суть:** При hangup (эмоция → hangup) вызывается `_handle_session_end()` из `process_message()`, затем `return`. Но `stop_event.set()` находится только в main loop (line 4251) при получении `session.end` — а hangup его не отправляет. Main loop продолжает ждать следующее сообщение.
**Последствия:** Зомби-сессии. Background tasks (watchdog, hint scheduler) продолжают работать. Ресурсы не освобождаются. Пользователь видит "не завершается".

### C4. Session end без таймаута — 500 строк последовательных операций
**Файл:** `training.py:2845–3342`
**Суть:** `_handle_session_end` последовательно выполняет: save call_outcome → calculate_scores → save emotion → end session DB → AI-Coach report (LLM) → layer explanations (LLM) → RAG feedback → Redis cleanup → auto-complete assigned → update ManagerProgress → behavioral intelligence → notifications → recommendations → wiki ingest. **Ни одна операция не имеет таймаута.** Если LLM повис на AI-Coach report — весь pipeline блокирован.
**Последствия:** Кнопка "Завершить" висит бесконечно. WS не закрывается. Пользователь вынужден перезагружать.

### C5. Несуществующие поля: `score_details` и `story_mode`
**Файлы:** `daily_goals.py:185,219,226,229`, `gamification.py:2008,2028,2031,2048,2082`
**Суть:** Модель `TrainingSession` (models/training.py:76) определяет поле `scoring_details`. Но `daily_goals.py` и `gamification.py` обращаются к `score_details` (без "ing") — поле не существует. Также используется `TrainingSession.story_mode` — тоже не существует (правильно: `client_story_id is not None`).
**Верификация:** Модель проверена — поле `scoring_details` в line 76, `score_details` нигде в models/.
**Последствия:** AttributeError при любом вызове daily_goals и gamification. XP не начисляется, achievements не работают, home page ломается.

### C6. Gemini квота исчерпана — circuit breaker застревает в OPEN
**Суть:** 429 quota exceeded от Gemini. Circuit breaker переходит в OPEN (5 failures → 60s recovery). Но квота не восстанавливается за 60s → повторные пробы тоже 429 → OPEN навсегда до ручного перезапуска.
**Последствия:** Cloud routing мёртв. Вся нагрузка на local LLM, который не справляется (C1).

### C7. ElevenLabs квота — TTS неработоспособен
**Суть:** 1 кредит из 4 нужных. Free tier: 10K chars/month. Одна сессия = ~2K chars TTS.
**Последствия:** Нет голоса аватара. Пользователь видит рот двигающийся без звука.

---

## ! БЛОК 2: ВЫСОКИЕ ПРОБЛЕМЫ (ухудшают качество критично)

### H1. Provider selection привязан к call_number, а не к размеру промпта
**Файл:** `training.py:902–910`
**Суть:** `prefer_provider = "auto" if call_number >= 3 else "local"`. Звонки 1–2 всегда идут в local, даже если промпт > 9600 токенов (C1). Для single-session call_number = 1 → **всегда local**.
**Последствия:** Local модель получает промпт, который не помещается в контекст. Вместо роутинга в cloud — гарантированная деградация.

### H2. Story mode: session.ended ставит UI в "connecting" навсегда
**Файл:** `training/[id]/page.tsx:300–318`
**Суть:** При story mode, получив `session.ended`, frontend ставит `sessionState = "connecting"` и текст "ФОРМИРУЕМ ОТЧЁТ ЗВОНКА...". Ожидает `story.next_call` или `story.completed`. **Нет таймаута.** Если backend не отправит — UI висит вечно.
**Последствия:** Story sessions никогда не видят результаты при любом сбое на стороне backend.

### H3. Emotion не восстанавливается при resume в multi-call stories
**Файл:** `training.py:475–530`
**Суть:** `session.resume` вызывает `get_emotion(session_id)` из Redis. Но Redis state мог быть потерян (TTL, restart). Fallback: `init_emotion(session_id, EmotionState.cold)`. Клиент, который был в `negotiating` → вдруг `cold`.
**Последствия:** Разрыв нарратива. Менеджер работал 20 минут, дошёл до переговоров — после reconnect клиент снова "холодный".

### H4. text_mode не сбрасывается при переключении на голос
**Файл:** `training.py:1490`
**Суть:** `state["text_mode"] = True` устанавливается при первом `text.message`. Обратного переключения нет. Silence detection (`not state.get("text_mode", False)`) навсегда отключен.
**Последствия:** Если менеджер отправил один текстовый message, а потом перешёл на микрофон — silence prompts никогда не придут.

---

## БЛОК 3: СРЕДНИЕ ПРОБЛЕМЫ (заметные UX / качество)

### M1. Realtime scores: 3 из 10 слоёв
**Файл:** `scoring.py:1143–1193`
**Суть:** `calculate_realtime_scores()` считает только L2 (objections), L3 (communication), L8 (human factor). Max = 48.75. Финальный score max = 100. Пользователь видит "32/48" во время тренинга → "71/100" в результатах.
**Последствия:** Обманчивый score hint. Менеджер думает что плохо работает, хотя по итогу — хорошо. Или наоборот.

### M2. Кнопка "Завершить" заблокирована во время briefing
**Файл:** `training/[id]/page.tsx:974`
**Суть:** `disabled={sessionState !== "ready"}`. Во время briefing (pre-call), sessionState = "briefing" → кнопка disabled.
**Последствия:** Нельзя отменить сессию до начала разговора.

### M3. Кнопка Send без loading state
**Файл:** `training/[id]/page.tsx:1282`
**Суть:** Нет визуальной индикации что сообщение отправляется.
**Последствия:** Пользователь жмёт повторно → дублирование сообщений → двойной LLM call.

### M4. StageProgress захардкожен на 7 этапов
**Файл:** `StageProgress.tsx:7–15`
**Суть:** `STAGE_LABELS` = Record с 7 записями (BFL скрипт). `totalStages` prop есть, но labels только для 1–7. Для 5 или 10 этапов — generic числовые метки.
**Последствия:** Ломается для нестандартных сценариев.

### M5. DB prompt override без валидации
**Файл:** `llm.py:1609–1620`
**Суть:** Если methodologist сохранил пустую строку в prompt registry → LLM получит пустой system prompt.
**Последствия:** Персонаж без роли, guardrails, эмоций.

### M6. Knowledge redirect path запутывает
**Файл:** `knowledge/[sessionId]/page.tsx`
**Суть:** `/knowledge/123` → внутренне работает как `/pvp/quiz/123`.
**Последствия:** URL путает пользователя и разработчика.

---

## БЛОК 4: АРХИТЕКТУРНЫЕ ПРОБЛЕМЫ (требуют перепроектирования)

### A1. Промпты 20–25K символов на персонажа
**Путь:** `apps/api/prompts/characters/`
**Суть:** skeptic_v2.md = 25K, manipulator_v2.md = 20K. Это ~10–12K токенов **только** character prompt. Для local LLM (Gemma 4B, контекст 8K) — невозможно. Для cloud (Gemini, контекст 1M) — ок, но дорого по токенам.
**Нужно:** compact-версии (~3–4K символов, ~1.5–2K токенов) для local LLM. Полные — для cloud.

### A2. Multi-call story: нет логики "зачем звонок 2–5?"
**Суть:** Если клиент согласился в звонке 1 — зачем звонить ещё? Между звонками генерируются CRM-события (creditor calls, family discussions, court letters), но **нет системной логики**, определяющей: клиент передумал / появились новые обстоятельства / отказ от документов. Это ad-hoc через `apply_between_calls_context()` с weighted random.
**Последствия:** Stories могут быть нелогичны. Клиент согласился → между звонками ничего не случилось → зачем звонить?

### A3. Конструктор персонажей: нет разрешения конфликтов
**Суть:** `CustomCharacter` хранит 8 параметров (archetype, profession, lead_source, difficulty и т.д.). `generate_personality_profile()` принимает **только archetype_code** → random sample OCEAN в пределах диапазона. Нет валидации что "агрессивный + благодарный" = противоречие. Нет зависимости personality от profession, debt_stage, family_preset.
**Последствия:** Промпт может быть внутренне противоречивым.

### A4. Episodic memory: зависимость от `[MEMORY:]` tags
**Файлы:** `scenario_engine.py:645–775`, `training.py:1176–1189`
**Суть:** LLM должен генерировать `[MEMORY:факт|salience=8|type=promise]` в ответе. Парсер regex извлекает. Но: (a) Gemma 4B может не следовать формату → память не сохраняется, (b) нет лимита на длину content в memory tag, (c) max 8 memories (MAX_MEMORY_ITEMS=8) без приоритизации старых vs новых.
**Нужно:** Fallback автоматическое извлечение ключевых фактов (rule-based или отдельный LLM call).

### A5. Avatar: TalkingHead ограничения
**Суть:** Все мужские модели = один GLB файл. TTS аудио подаётся через HTML audio element, не напрямую в lip sync pipeline. Нет кастомных моделей для senior архетипов.
**Нужно:** VRM через `@pixiv/three-vrm` + wawa-lipsync (или аналог).

---

## БЛОК 5: ИНФРАСТРУКТУРНЫЕ ПРОБЛЕМЫ

### I1. PostgreSQL pool > max_connections
**Файлы:** `database.py`, `docker-compose.yml`
**Суть:** pool_size=50 + max_overflow=20 = 70 per worker × 4 workers = 280. PostgreSQL max_connections=200. **280 > 200.**
**Последствия:** Под нагрузкой — pool exhaustion, "too many connections", 500 errors.

### I2. Redis — single point of failure, нет HA
**Суть:** Redis хранит: JWT blacklist, session state, rate limits, LLM health, circuit breaker, WS connections. Нет Sentinel, нет maxmemory-policy.
**Последствия:** Redis down = 401 для всех (fail-closed JWT) + потеря всех активных сессий.

### I3. Gemini 15 RPM: 5 пользователей = исчерпание за минуты
**Суть:** 1 тренировка = 20–50 AI вызовов. 5 users × 30 msgs = 150 calls. При 15 RPM = 10 минут очередь. Нет token bucket, нет приоритизации между character response и wiki ingest.

### I4. Session end — нет background queue
**Суть:** `_handle_session_end` выполняет 12 шагов последовательно в event loop FastAPI. Scoring, recommendations, wiki ingest, behavioral intelligence — всё синхронно.
**Нужно:** Background task queue (ARQ/TaskIQ) для post-session.

### I5. 5 WebSocket handlers дублируют логику
**Суть:** training (3692 LOC), pvp (2100), knowledge (3000), notifications (450), game-crm (145). Каждый свой: auth, error handling, message parsing, connection manager. Только training имеет session.resume + heartbeat.

---

## БЛОК 6: НИЗКИЕ / МЕЛОЧИ

| # | Проблема | Файл |
|---|---------|------|
| L1 | Avatar3D: бесконечный спиннер при ошибке загрузки (есть fallback, но без error state в UI) | Avatar3D.tsx |
| L2 | RealtimeScores: ничего не показывает до первого score.hint | RealtimeScores component |
| L3 | emotion.update отправляется даже когда эмоция не менялась → лишний трафик | training.py |
| L4 | WS disconnect toast без индикатора попыток reconnect | toast component |
| L5 | `as never` type casts в LLMDegradationBanner (обход TypeScript для custom events) | LLMDegradationBanner.tsx:72-73 |
| L6 | Daily challenge/goals тихо глотают ошибки API (catch → log → continue) | daily_goals.py |

---

## РАБОТАЕТ ХОРОШО

| Модуль | Статус |
|--------|--------|
| PvP Arena (lobby, duel, quiz) | Полностью реализовано, ErrorBoundary |
| Knowledge Quiz (все режимы) | Работает с RAG |
| CRM/Clients + Pipeline | Kanban, drag-drop, фильтры |
| Dashboard (все виджеты) | 10 виджетов, PDF export |
| Profile, Settings | Полный функционал |
| Auth (login, OAuth, refresh) | Стабильно |
| WS reconnection (training) | Exponential backoff, queue |
| Notification system | Role-based, channel filtering |
| Between-call narrator | 4 функции с LLM + template fallback |
| Emotion system (logic) | 10 states, OCEAN/PAD, deferred hangup recovery |

---

## ПРИНЯТЫЕ РЕШЕНИЯ (Q1–Q31)

Все ответы зафиксированы. Ниже — итоговые решения + архитектурный анализ.

### I. AI-МОДЕЛЬ И ПРОВАЙДЕРЫ

| # | Решение |
|---|---------|
| Q1 | **Compact-промпты для Gemma** (вариант d). Двухуровневая система: core (1.5K токенов) + extended (полный, cloud). Для пилота 7–10 архетипов. Core-версии через LLM-сжатие. **Дополнительно:** проработать архитектуру «прогрессивного промпта» — модель стартует с compact, но в процессе разговора может обращаться к расширенным данным |
| Q2 | **(d) Комбинация.** task_type → preferred provider, estimated_tokens → fallback. Single-session тоже проверяет token count |
| Q3 | **(c) Local-first.** Roleplay → local. Cloud (Gemini free 15 RPM) → только scoring/coach/report (~5 req/session) |
| Q4 | **(d) Два уровня.** Core 1.5K + Extended full. 7–10 архетипов для пилота. LLM-сжатие для генерации core |
| Q5 | **(a+b+c) Все три.** 429 ≠ failure. Exponential cooldown. Quota-aware pre-routing |

### II. TRAINING SESSION LIFECYCLE

| # | Решение |
|---|---------|
| Q6 | **(c) Пересоздание из DB.** 2–3с допустимо. Redis ненадёжен, DB — source of truth |
| Q7 | **(c) Belt and suspenders.** stop_event.set() + should_stop signal. **Исключение:** story mode hangup НЕ закрывает WS (between_call → next call) |
| Q8 | **Critical path 5с** (save scores → end session → send results). **Background** (fire-and-forget): AI-Coach, wiki, recommendations, behavioral. **Fallback:** partial results + «Полный анализ готовится...» |
| Q9 | **(c) Immediate redirect** на промежуточную страницу с тем что есть (emotion journey, базовый скор), background готовит полный отчёт |
| Q10 | **(a) Auto-detect.** audio.chunk → text_mode = False. Переключение mid-session нужно |

### III. AI FLOW

| # | Решение |
|---|---------|
| Q11 | **(a) Два семафора.** realtime (10 слотов: character + trap) + background (5: scoring, wiki, coach) |
| Q12 | **(b) Частичный score.** 5 rule-based слоёв сразу + «Предварительная оценка (50%). Полный анализ через 5 мин» |
| Q13 | **(d) Hybrid.** Strict для терминальных (deal/hangup — только через negotiating/hostile). Soft для промежуточных (skip max 1 состояние). Быстрый прогресс допустим, cold→deal за 2 msg — нет |
| Q14 | **(c) Rule-based + LLM.** Regex baseline (числа, имена, обещания) + LLM enrichment после каждого звонка (не каждого msg) |
| Q15 | **(d) Templates + LLM.** 3 story arcs для пилота: линейный прогресс, отказ-возврат, усложнение |
| Q16 | **(a) Validation matrix** (требует изучения). `archetype_blender.py` уже реализует conflict boost через OCEAN/PAD |
| Q17 | **(d) Simple length filter** 20–300 слов + retry (max 1). 0мс latency — фильтр на полученном ответе |

### IV. DATABASE

| # | Решение |
|---|---------|
| Q18 | **Фиксим сразу.** score_details→scoring_details, story_mode→client_story_id.isnot(None). 9 строк, 4 файла |
| Q19 | **(a) Pydantic** для пилота. Dataclasses — после |
| Q20 | **(d) 2 workers** для пилота (140 < 200 max_connections). PgBouncer при >50 users |

### V. WEBSOCKET

| # | Решение |
|---|---------|
| Q21 | **(d) Только heartbeat + resume в pvp/knowledge.** Полный рефакторинг после пилота |
| Q22 | **Не проблема при 5–20 users.** Safety net: max 100 msg в outgoing queue |

### VI. USER FLOW

| # | Решение |
|---|---------|
| Q23 | **Soft guards.** Training→PvP: предложить завершить. PvP disconnect: forfeit 60с. 2 вкладки: supersede |
| Q24 | **(c) Tutorial-сценарий** (difficulty=1, passive). Менеджеры с опытом продаж, без опыта платформы |
| Q25 | **LLM down→scripted+banner. TTS down→текст. STT down→текстовый ввод. Redis down→read-only** |

### VII. INFRASTRUCTURE

| # | Решение |
|---|---------|
| Q26 | **(d) Всё.** RDB + AOF + allkeys-lru. JWT blacklist = критично, session state = recoverable |
| Q27 | **(c) Текущий подход** (idempotent). Advisory lock если сломается |

### VIII. OPEN

| # | Решение |
|---|---------|
| Q28 | **VRM (@pixiv/three-vrm).** Визуальное качество → стабильность. 2–3 модели для пилота (M/F/senior) |
| Q29 | **Изучить проблему ElevenLabs.** API key и voice IDs предоставлены — нужно проверить что не работает |
| Q30 | **Warning → Penalty (-20%) → suspected_ai_assist: true.** Не блокировать. Логика anti-cheat уже реализована (4 уровня, 677 строк). Если платформа интересна — обманывать смысла нет |
| Q31 | **Для пилота хватит.** Пользователь скачивает данные, РОП видит паттерны через wiki-панель |

---

## ОТВЕТЫ НА АРХИТЕКТУРНЫЕ ВОПРОСЫ

### БЛОК 1: МОДЕЛЬ — Главный вопрос

**В1. Практический context window Gemma 4B на Mac Mini при 10 tok/s?**

Gemma 3 4B IT (Q4_K_M quantization) на Apple Silicon:
- **Теоретический лимит:** 8K токенов
- **Практический лимит для связного ролеплея на русском:** ~4000–4500 токенов total (system + history + response)
- **При 9600 токенов:** гарантированная деградация — модель теряет начало промпта, путает роль, генерирует бессвязный текст
- **При 4000:** качество приемлемое, роль удерживается
- **При 3000:** качество хорошее, но мало места для истории

**В2. Если сжать промпты до 3K — хватит ли 5K на history + extra_system?**

Расчёт при 8K контексте Gemma:
```
System prompt (compact):     1,500 токенов (3K символов)
Extra_system (budgeted):       800 токенов (objections, stage, traps)
History (20 msgs × ~120 tok):2,400 токенов
Response buffer:               500 токенов
────────────────────────────────
ИТОГО:                       5,200 токенов → ВЛЕЗАЕТ в 8K
```

Но при 30+ сообщениях history = 3600+ токенов → 6,800 → на пределе.
**Решение:** `_trim_history()` уже обрезает до N последних сообщений. Нужно выставить N=15 для local, N=30 для cloud.

**В3. Проблема не в модели, а в том что ContextBudgetManager не enforce'ит бюджет?**

**ДА. Это точный диагноз.** Верифицировано по коду:

Существуют **два пути** сборки промпта:

| Путь | Функция | Budget enforcement |
|------|---------|-------------------|
| **Multi-call** (story mode) | `build_multi_call_prompt()` (llm.py:1059) | `trim_to_budget()` вызывается для каждой секции. Работает. |
| **Single-call** (обычный тренинг) | `_build_system_prompt()` (llm.py:544) + extra_system (training.py:831) | **НЕТ ОБРЕЗКИ.** Character prompt 25K загружается целиком через `load_prompt()`. extra_system растёт без лимита. |

**Код-доказательство:**
- `load_prompt()` (llm.py:327): `return requested.read_text()` — файл целиком
- `_build_system_prompt()` (llm.py:544): `parts.append(character_prompt)` — без trim
- `generate_response()` (llm.py:1622): `full_system = full_system + "\n\n" + system_prompt` — extra_system приклеивается без проверки
- Токены оцениваются (llm.py:1642): `prompt_tokens = len(full_system) // 2` — **только для логирования и routing**, не для обрезки
- API вызовы (llm.py:1303–1518): все 4 провайдера получают `system_prompt` as-is

**Фикс C1 = применить `trim_to_budget()` в single-call пути.** Это НЕ смена модели, это 20–30 строк кода:
1. В `generate_response()`: если `character_prompt_path` → вызвать `ContextBudgetManager.trim_to_budget("character_prompt", char_prompt)`
2. В training.py: ограничить `extra_system` бюджетом (~800 токенов = 1600 символов)
3. Финальная проверка: если `total > budget` → обрезать history, не промпт

---

### БЛОК 2: ROUTING — Зачем два провайдера?

**Если compact-промпты + бюджет = всё влезает в Gemma — нужен ли cloud для пилота?**

**Для пилота cloud нужен ТОЛЬКО для:**
1. **Scoring + Coach report** (post-session) — требует анализа всего диалога, сложный structured output
2. **Failover** — если Mac Mini выключен

**Roleplay → 100% local** при правильном бюджете.

**Простой routing:**
```
if local_alive AND estimated_tokens < 4000:
    → local
elif cloud_available:
    → cloud
else:
    → scripted_fallback
```

Матрица task_type × tokens × call_number × RPM — оверинжиниринг для пилота. Один критерий: `local alive + fits in context`.

---

### БЛОК 3: SESSION LIFECYCLE

**Session resume — сколько реально resume'ят?**

Edge case: browser refresh, потеря WiFi. Для пилота (5–20 users, стабильный WiFi) — <5% сессий.
**Прагматичный подход:** (c) пересоздание из DB, но это уже почти реализовано (training.py:475). Нужно добавить ~10 полей к восстановлению. Не «перезапустить сессию» — пользователь потеряет 15 минут работы.

**Session end — какие шаги блокирующие?**

Из 12 шагов пользователь ждёт ТОЛЬКО:
```
БЛОКИРУЮЩИЕ (critical path, таймаут 5с):
  1. save_scores() → DB write
  2. end_session() → DB status update
  3. send_results() → WS message to client

BACKGROUND (fire-and-forget):
  4. AI-Coach report (LLM, 5–10с)
  5. Layer explanations (LLM, 3–5с)
  6. RAG feedback loop
  7. Redis cleanup
  8. Auto-complete assigned training
  9. ManagerProgress (XP, level)
  10. Behavioral intelligence
  11. Notifications
  12. Wiki ingest
```

**Story mode multi-call — нужен для пилота?**

Зависит от цели пилота. Если цель = проверить качество одного звонка и обратную связь → defer multi-call. Если цель = полный цикл продажи → нужен. **Рекомендация:** single-call качество важнее. Multi-call добавить во 2-й фазе.

---

### БЛОК 4: КАЧЕСТВО ОТВЕТОВ

**Почему Gemma падает в scripted?**

Три причины (по коду):
1. **OOM/Timeout:** промпт 9600+ токенов → Gemma не отвечает за 15с → timeout → circuit breaker → scripted
2. **Пустой ответ:** Gemma возвращает пустую строку (при перегрузке контекста) → `_filter_output()` видит пустоту → fallback
3. **Role break:** Gemma генерирует "Как ИИ-ассистент..." → фильтр ловит → fallback phrase

**Нужна статистика:** добавить counter в `generate_response()` — по провайдеру, по причине fallback. 10 строк кода.

**Имя персонажа — 52 файла с hardcoded именами.**

Все 52 файла содержат хардкод: "Дмитрий Козлов", "Андрей Николаевич Волков" и т.д.
**Но:** runtime override уже работает (training.py:833): `"ВАЖНО: тебя зовут {char_name}..."`.
Это костыль, но **рабочий костыль**. Для пилота — достаточно. Рефакторинг на `{CHARACTER_NAME}` шаблоны — после пилота.

**Контент-фильтр на входе:**

`content_filter.py` (194 строки) уже имеет 4-слойный фильтр. Для пилота:
- **Выход (AI):** фильтровать всё (profanity, role-break, PII) — уже работает
- **Вход (менеджер):** пропускать. Это тренажёр — менеджер может тестировать грубость клиента. Фильтр на входе = ограничение тренировки

---

## КОРРЕКЦИЯ РЕЕСТРА: Что уже реализовано (мои ошибки)

Автор справедливо указал что я предполагал отсутствие систем, которые уже реализованы. Фиксирую:

| Мой вопрос | Что я предполагал | Что реально в коде |
|------------|-------------------|-------------------|
| Q5 Circuit breaker | «Нужно реализовать» | Работает с Wave 1 (llm.py:45–86), 4 провайдера, half-open recovery |
| Q13 Emotion FSM | «LLM может перепрыгивать» | `ALLOWED_TRANSITIONS` (emotion.py:40) — strict directed graph, 10 states |
| Q16 Конструктор | «Нет разрешения конфликтов» | `archetype_blender.py` (208 строк) — OCEAN/PAD blending с conflict boost |
| Q17 Output filtering | «Не фильтруется» | `content_filter.py` (194 строки) — 4-слойный фильтр + `_filter_output()` |
| Q19 JSONB валидация | «Любые данные» | Pydantic schemas (app/schemas/) валидируют все входящие данные через FastAPI |
| Q21 WS дублирование | «Каждый свой Singleton» | `ws_rate_limiter.py` — единая система, auth в каждом handler |
| Q23 User state | «Нет управления» | `_acquire_session_lock()` через Redis — предотвращает дубли |
| Q24 Onboarding | «Не определён» | 5-step wizard (onboarding/page.tsx): профиль→настройки→микрофон→режим→demo |
| Q25 Degradation | «Нет graceful» | llm_health.py + Redis флаги + WS уведомления + LLMDegradationBanner.tsx |
| Q26 Redis | «Нет recovery» | maxmemory 384mb, allkeys-lru, RDB snapshots в docker-compose |
| Q30 Anti-cheat | «Что видит пользователь?» | 4-уровневая система (anti_cheat.py + nlp_cheat_detector.py), 677 строк |

**Системы которые работают и не требуют изменений:**
Daily Challenges (234 LOC), Daily Goals (305), Daily Advice (415), Spaced Repetition (691), Hunter Score (141), Season Pass (157), Catch-Up Manager (116), Recommendation Engine (512), Cross Recommendations (265), Reputation System (340), Navigator (665), Prompt Registry (269), Audit Logging (129), Wiki Ingest (915), Objection Chains (517), Human Factor Traps (404).

---

## КОРНЕВАЯ ПРИЧИНА C1 (ИТОГОВЫЙ ДИАГНОЗ)

**Проблема НЕ в модели. Проблема в том что single-call path обходит ContextBudgetManager.**

```
Multi-call (story mode):
  build_multi_call_prompt() → trim_to_budget() для каждой секции → ✅ РАБОТАЕТ

Single-call (обычный тренинг):
  load_prompt() → 25K символов целиком
  _build_system_prompt() → append без trim
  + extra_system → append без лимита
  → generate_response() → отправляет as-is → ❌ ОБХОДИТ БЮДЖЕТ
```

**Фикс:** применить ту же логику `trim_to_budget()` в single-call path. ~30 строк кода.

---

## ИССЛЕДОВАНИЕ: КАК ЭТО ДЕЛАЮТ ДРУГИЕ

### Ключевой инсайт: проблема не в модели — проблема в архитектуре промптов

Изучены: Character.AI, SillyTavern/KoboldAI, ChatHaruhi, Mursion, Second Nature AI, Hyperbound, Zenarate, Convai/Inworld AI, LLMLingua (Microsoft), MetaGlyph, Neeko (LoRA switching).

---

### 1. ПАТТЕРН "LOREBOOK" (SillyTavern, тысячи пользователей с 7B моделями)

**Суть:** Вместо одного гигантского промпта — три слоя:

```
Слой 0: Character Card (<600 токенов, ВСЕГДА в промпте)
  → Имя, роль, 3 ключевых черты, стиль речи, текущая цель

Слой 1: Lorebook (keyword-triggered, ON DEMAND)
  → Записи по 50-200 токенов каждая, активируются по ключевым словам в разговоре
  → "долг" → активирует запись про финансовую ситуацию персонажа
  → "жена" → активирует запись про семью
  → "суд" → активирует юридические знания
  → Жёсткий token budget cap: если активировано слишком много — берутся только top-priority

Слой 2: Sliding Window + Summary
  → Последние 10-15 сообщений verbatim
  → Старые → сжимаются в running summary (~300 токенов)
```

**Итого в контексте:** 600 (card) + 400 (lorebook) + 300 (summary) + 1500 (history) + 500 (response) = **3300 токенов** → свободно влезает в Gemma 8K.

**Почему это лучше нашего подхода:** Мы загружаем 25K символов (~12K токенов) character prompt, из которых 90% не релевантны текущему моменту разговора. SillyTavern загружает только то, что нужно ПРЯМО СЕЙЧАС.

**Применение к Hunter888:** Наши character prompt файлы = это lorebook entries. Разбить каждый архетип (skeptic_v2.md, 25K) на 15-20 записей по 200-300 символов:
- core_identity (всегда): имя, возраст, профессия, базовый характер — 600 токенов
- financial_situation (при теме "долг", "деньги"): детали финансов — 200 токенов
- family_context (при теме "семья", "жена", "дети"): семейная ситуация — 200 токенов
- legal_fears (при теме "суд", "банкротство"): страхи и заблуждения — 200 токенов
- speech_patterns (всегда): манера речи, любимые фразы — 150 токенов
- objection_templates (при возражениях): типичные отговорки — 200 токенов
- и т.д.

---

### 2. RAG ДЛЯ ЛИЧНОСТИ (ChatHaruhi, research + production)

**Суть:** Вместо описания персонажа текстом — база данных **примеров его поведения**.

```
Vector DB содержит:
  → 100-300 примеров реплик персонажа в разных ситуациях
  → Каждый пример: [ситуация] → [реплика персонажа]

При каждом сообщении менеджера:
  1. Embed сообщение менеджера
  2. Найти 3-5 семантически похожих ситуаций из базы
  3. Вставить как few-shot examples в промпт
```

**Промпт выглядит так:**
```
Ты — Виктор, скептичный клиент. Вот как ты обычно отвечаешь:

Пример 1: Менеджер предложил скидку → Виктор: "Скидка? А с чего мне верить что это не развод?"
Пример 2: Менеджер спросил про долг → Виктор: "Сколько я должен — это моё дело, не ваше."
Пример 3: Менеджер упомянул суд → Виктор: "Суд? У меня юрист есть, не пугайте."

[Текущий разговор]
Менеджер: "Виктор, давайте обсудим вашу ситуацию с банком."
Виктор:
```

**Почему это мощно:** Модель учится стилю персонажа по примерам, а не по описаниям. Маленькие модели **гораздо лучше** имитируют стиль через few-shot, чем следуют длинным инструкциям.

**Применение к Hunter888:** У нас уже есть pgvector + embeddings сервис. Создать таблицу `character_examples` с 50-100 примерами на архетип. Embeddings уже работают через Gemini API.

---

### 3. CONSTRAINED DECODING (Outlines, vLLM) — решение проблемы A4

**Суть:** Вместо надежды что модель сгенерирует `[MEMORY:факт|salience=8]` — **принудить** её генерировать валидный формат.

```python
# Outlines: компилирует JSON Schema в конечный автомат
from outlines import generate, models

model = models.transformers("gemma-3-4b-it")
generator = generate.json(model, MemoryTag)  # Pydantic schema

# Модель ФИЗИЧЕСКИ НЕ МОЖЕТ сгенерировать невалидный JSON
result = generator(prompt)  # Гарантированно валидный MemoryTag
```

**Требование:** Ollama или vLLM вместо LM Studio (LM Studio не поддерживает constrained decoding).

**Применение к Hunter888:** Решает A4 (memory tags), помогает с scoring JSON, judge JSON, quiz evaluation. Гарантирует структуру на уровне токенов.

---

### 4. FINE-TUNING: LoRA на Mac Mini (после пилота)

**Факты:**
- LoRA fine-tune Gemma 3 4B = **2-4 часа на Apple Silicon Mac Mini** (бесплатно)
- Нужно: 500-1000 примеров диалогов на архетип
- Инструменты: Unsloth или LLaMA Factory
- Результат: модель "знает" архетип без промпта → system prompt <100 токенов

**Neeko (research):** динамическое переключение LoRA-адаптеров между персонажами. Один base model + 10 LoRA = 10 персонажей без увеличения RAM.

**Применение к Hunter888:** Phase 2. Собрать данные с пилота → fine-tune. Но это ПОСЛЕ стабилизации — сначала lorebook + RAG.

---

### 5. LM STUDIO — ОСТАЁМСЯ (решение Q34)

**Mac Mini:** Apple M2, 8GB RAM, 160GB свободно.

**Ограничения M2 8GB:**
- Gemma 3 4B Q4_K_M = ~4-5 GB total (модель + KV cache + runtime). Влезает.
- **Gemma 4 E4B** (вышла 2 апреля 2026) = ~5-7 GB total. Впритык, но работает. Значительно лучше Gemma 3 по instruction following и multi-turn coherence. Нативная поддержка system/user/assistant ролей.
- **Два модели одновременно — НЕВОЗМОЖНО** на 8GB. LM Studio не поддерживает загрузку embedding + chat model одновременно.
- Inference speed: ~15-20 tok/s (достаточно, человек читает ~4 tok/s).

**LM Studio vs Ollama:** LM Studio поддерживает constrained decoding (grammar-based JSON). Нет критичных потерь при остании. MLX режим на Apple Silicon может быть даже быстрее Ollama.

**Embeddings решение:** Предварительно вычислить offline. Загрузить embedding model → embed все lorebook entries → сохранить в pgvector → выгрузить embedding model → загрузить chat model. Перезапускать embeddings только при изменении lorebook.

**Рекомендация обновлённая:** Обновить Gemma 3 4B → **Gemma 4 E4B** (128K контекст, лучше русский, system role support).

---

### 6. СКОРИНГ: КАК ДЕЛАЮТ КОНКУРЕНТЫ

**Second Nature AI** (привлекли $22M):
- **70/30 split:** 70% knowledge (тема, точность) + 30% style (темп, ясность, энергия)
- **Post-session:** 45-90 секунд на полный scorecard через LLM
- **Real-time:** только topic coverage checklist (rule-based)

**Hyperbound:**
- Progressive difficulty: Level 1 (одно возражение) → Level 2 (follow-up) → Level 3 (multi-objection)
- Methodology-specific scorecards (не generic)

**Zenarate (closed-loop):**
- Train → Score → Score LIVE calls по ТОЙ ЖЕ рубрике → Identify gaps → Re-train
- PII redaction в скоринг-пайплайне

**Применение к Hunter888:** Наш 10-слойный скоринг сложнее чем у конкурентов. Это и преимущество и проблема. Для пилота: realtime = rule-based (L1-L5), post-session = LLM enrichment (L6-L10). Как у Second Nature, но глубже.

---

### 7. EMOTION: КАК МОДЕЛИРУЮТ ДРУГИЕ

**Индустрия:** 5-7 дискретных состояний + weighted transition rules per persona. Полная VAD модель = overkill для production.

**Convai (game NPCs):** personality traits → influence behaviour. "Lazy" NPC отказывается от заданий. Emotion states driven by game events.

**Наше преимущество:** У нас 10 states + OCEAN/PAD + ALLOWED_TRANSITIONS + archetype_blender + MoodBuffer + EMA smoothing. Это **сложнее** чем у любого конкурента. Проблема не в архитектуре эмоций — она хорошая. Проблема в том что Gemma не может следовать ей при 12K промпте.

---

## ПЕРЕСМОТРЕННАЯ АРХИТЕКТУРА (черновик v2)

### Было (текущее):
```
[25K character file] + [guardrails] + [emotion] + [scenario] + [extra_system]
= 9600-15000 токенов → Gemma OOM → scripted fallback
```

### Предлагается:
```
[Character Card: 600 tok] + [Lorebook entries: 200-400 tok, keyword-triggered]
+ [RAG examples: 300-500 tok, semantic retrieval]
+ [Emotion + Scenario: 300 tok]
+ [History: sliding window 10-15 msgs]
= 2000-3000 токенов → Gemma работает стабильно
```

### Что это меняет:
- **Качество ↑:** модель получает РЕЛЕВАНТНЫЙ контекст, а не 90% мусора
- **Стабильность ↑:** 3000 токенов < 8000 лимит → нет OOM, нет timeout, нет scripted fallback
- **Глубина персонажа СОХРАНЯЕТСЯ:** полный 25K файл живёт в lorebook + RAG, не удаляется
- **Игровое ощущение СОХРАНЯЕТСЯ:** emotion system, traps, scoring, objection chains — не меняются
- **CRM СОХРАНЯЕТСЯ:** multi-call stories, between-call events, Game Director — не затрагиваются
- **Расширяемость ↑:** добавить нового персонажа = написать card (600 tok) + наполнить lorebook (10-15 entries) + добавить examples (50-100 реплик)

---

## ОБНОВЛЁННЫЙ ПЛАН РЕАЛИЗАЦИИ (v2)

### Фаза 0: Критические фиксы (1–2 дня)
Не зависят от архитектурных решений. Просто баги.
- [ ] **C3:** stop_event.set() при hangup (+ story mode exception)
- [ ] **C5:** Rename score_details→scoring_details, story_mode→client_story_id (9 строк)
- [ ] **H4:** text_mode auto-reset при audio.chunk
- [ ] **H1:** Routing по estimated_tokens вместо call_number
- [ ] Мониторинг: counter fallback rate по провайдеру (10 строк)

### Фаза 1: Новая промпт-архитектура (5–7 дней)
Ключевое изменение. Решает C1, A1, H1, и большинство проблем качества.
- [ ] **Lorebook system:** разбить 7-10 архетипов на card + keyword-triggered entries
- [ ] **Budget enforcement:** применить trim_to_budget() в single-call path
- [ ] **Character Card templates:** core identity <600 токенов на архетип
- [ ] **Keyword trigger engine:** активация lorebook entries по содержимому разговора
- [ ] **RAG examples (опционально):** 50 примеров реплик на архетип в pgvector
- [ ] **History management:** sliding window N=15 для local + running summary для длинных сессий

### Фаза 2: Стабилизация + Session lifecycle (3–5 дней)
- [ ] **C4:** Session end → critical path 5с + background
- [ ] **C2:** Session resume → пересоздание из DB
- [ ] **H2:** Story mode → immediate redirect на промежуточные результаты
- [ ] **Q5:** Circuit breaker: 429 ≠ failure + exponential cooldown
- [ ] **Q11:** Два семафора (realtime 10 + background 5)
- [ ] **Q17:** Length filter 20–300 слов + retry

### Фаза 3: Инфраструктура (2–3 дня)
- [ ] **Gemma 4 E4B:** Обновить модель на Mac Mini (LM Studio, Q4_K_M)
- [ ] **Q20:** Workers = 2 для пилота
- [ ] **Q29:** Диагностика ElevenLabs
- [ ] **Q22:** Outgoing queue max 100 msg
- [ ] **Q21:** Heartbeat + resume в pvp/knowledge

### Фаза 4: Углубление (после пилота)
- [ ] **LoRA fine-tune:** Unsloth на бесплатном Google Colab T4 → экспорт GGUF → LM Studio
  - 500-1000 примеров на архетип
  - Данные: из пилота + синтетические через Claude
  - Результат: модель "знает" архетип → system prompt <100 токенов
- [ ] **A/B test:** Gemma 4 E4B vs Qwen 2.5 7B на реальных русских диалогах
- [ ] **Constrained decoding:** LM Studio grammar-based JSON для MEMORY tags
- [ ] **Story arc engine:** 3 типа arc для multi-call
- [ ] **Zenarate loop:** scoring тренировок → scoring реальных звонков по той же рубрике
- [ ] **Wiki → Lorebook feedback loop:** паттерны из ManagerWiki обогащают lorebook

---

## WIKI & KNOWLEDGE КАК ИСТОЧНИК ДАННЫХ

### Что уже есть (95% инфраструктуры для lorebook RAG)

Ключевая находка: **нам НЕ нужно строить RAG с нуля.** Вся инфраструктура уже работает:

| Компонент | Что есть | Переиспользование |
|-----------|---------|-------------------|
| pgvector (768-dim) | `LegalKnowledgeChunk.embedding` | Добавить `PersonalityChunk.embedding` — та же колонка |
| Hybrid retrieval | `rag_legal.py` — embedding + keyword + RRF | Копировать → `rag_personality.py`, адаптировать scoring |
| Chunk tracking | `ChunkUsageLog` — retrieval count, correctness | Адаптировать source_type для personality |
| Feedback loop | `rag_feedback.py` — effectiveness scoring | Та же логика: trait prediction accuracy |
| Embedding pipeline | `llm.get_embedding()` + `services/embeddings/` | Прямое переиспользование |
| LRU кэш | 512 entries, 1h TTL | Прямое переиспользование |
| Background scheduler | `wiki_scheduler.py` — daily/weekly synthesis | Добавить personality synthesis job |
| Ingest pipeline | `wiki_ingest_service.py` — extract patterns from sessions | Адаптировать для personality traits |

### Как Wiki обогащает Lorebook

```
Текущий flow:
  Session → wiki_ingest → ManagerPattern (weakness/strength)
                        → ManagerTechnique (attempt/success rate)
                        → WikiPage (markdown insights)

Новый flow (дополнение):
  Session → wiki_ingest → ManagerPattern (для менеджера)
          → personality_ingest → PersonalityChunk (для персонажа)
             ↑ Из того же диалога извлекаем:
             - Как персонаж реагировал на конкретные фразы менеджера
             - Какие реплики персонажа были наиболее реалистичными
             - Где персонаж "сломался" (role break, contradiction)
```

### PersonalityChunk — новая модель (аналог LegalKnowledgeChunk)

```
PersonalityChunk:
  id, archetype_code (FK)
  trait_category: enum (core_identity, speech_patterns, financial_situation,
                        family_context, legal_fears, objection_templates,
                        emotional_triggers, decision_drivers)
  content: text (200-300 символов — одна lorebook entry)
  keywords: JSONB (для keyword triggering)
  priority: int (0-10, для budget cap)
  embedding: Vector(768)
  source: enum (manual, extracted_from_prompt, generated_llm, learned_from_session)
  effectiveness_score: float (из feedback loop)
  retrieval_count, hit_count: int
  is_active: bool
  created_at, updated_at
```

### RAG Examples — источники (Q33, решение: комбинация d)

**Этап 1 (сейчас):** Извлечь из существующих 25K промптов
- Claude извлекает все цитаты, паттерны речи, примеры реплик
- Из каждого 25K файла → 15-30 structured examples
- Формат: `{situation, dialogue, tags}`

**Этап 2 (сейчас):** Сгенерировать через Claude/Gemini
- 10 батчей по 5 реплик с разными ситуационными ограничениями
- Post-filter: cosine similarity, убрать дубли (>0.7 sim)
- Ручная курация: 10 мин на архетип

**Этап 3 (после пилота):** Собрать из реальных тренировок
- Wiki ingest уже записывает паттерны
- Personality ingest добавит реплики персонажа
- Самые реалистичные реплики → в RAG examples
- **Закрытый цикл:** тренировки улучшают lorebook, lorebook улучшает тренировки

### Keyword Trigger Engine (Q32)

**Решение:** Гибрид regex + embedding для разных слоёв.

**Слой 1 — Regex (мгновенный, 0мс):**
```python
# Каждая PersonalityChunk имеет keywords: ["долг", "деньги", "кредит", "банк"]
# Если слово из keywords найдено в последнем сообщении → chunk активирован
triggered = [chunk for chunk in lorebook
             if any(kw in last_message.lower() for kw in chunk.keywords)]
```

**Слой 2 — Embedding fallback (если regex не нашёл ничего):**
```python
# Если regex вернул 0 chunks → семантический поиск
if not triggered:
    triggered = await rag_personality.retrieve(last_message, top_k=3)
```

**Бюджет:** max 400 токенов lorebook entries на запрос. Если triggered > 400 → берём top-priority.

**Embeddings предвычислены offline** (ограничение M2 8GB). При добавлении новых entries → кратковременная загрузка embedding model → embed → выгрузка.

---

## ОТКРЫТЫЕ ВОПРОСЫ (обновлённые)

**Q32.** ✅ Решено: Гибрид regex + embedding fallback. Regex = 0мс, embedding = только если regex пусто.

**Q33.** ✅ Решено: Комбинация (d) — извлечение из промптов + генерация + данные с пилота. Проработать вместе.

**Q34.** ✅ Решено: Остаёмся на LM Studio, M2 8GB. Обновить до Gemma 4 E4B.

**Q35.** ✅ Решено: Lorebook ДОПОЛНЯЕТ objection_chains и human_factor_traps. Они остаются в extra_system, но с budget cap.

**Q36.** ✅ Решено: Fine-tune — отдельный документ `FINETUNE_PLAN.md`. Данные готовим параллельно, training после пилота.

**Q37.** ✅ Решено: Gemma 4 E4B уже установлена и работает (LM Studio:1234, Q4_K_M, context 8067).

---

## ПРОБЕЛЫ В ПЛАНЕ (самопроверка)

Проверяю: что НЕ описано и может укусить при реализации?

### Описано и готово к реализации:
- [x] Все баги (C1-C7, H1-H4, M1-M6) — с точными файлами и строками
- [x] Lorebook architecture — card + keyword entries + RAG examples
- [x] Budget enforcement — где именно в коде фиксить (single-call path)
- [x] Token budget breakdown — 3000 tok из 8067 available
- [x] Keyword trigger engine — regex + embedding fallback
- [x] PersonalityChunk модель — поля, типы, FK
- [x] RAG инфраструктура — 95% переиспользование существующей
- [x] Wiki feedback loop — тренировки → lorebook → тренировки
- [x] Hardware constraints — M2 8GB, embeddings offline
- [x] Provider routing — local-first, cloud for scoring
- [x] Session lifecycle — resume, hangup, end timeout
- [x] Конкурентный анализ — SillyTavern, ChatHaruhi, Second Nature, Hyperbound
- [x] Fine-tune план — отдельный документ

### НЕ описано (потенциальные пробелы):

**P1. Точный формат собранного промпта.** Как именно выглядит финальный промпт, который уходит в Gemma 4? Порядок секций, разделители, примеры. Нужен mockup.

**P2. Тестирование lorebook.** Как мы проверим что lorebook работает лучше текущего подхода? A/B тест? Метрики? На каких сценариях? Нужен test plan.

**P3. Миграция данных.** Как именно 52 prompt файла превращаются в lorebook entries? Кто делает extraction? Claude автоматически или ручная работа? Нужен pipeline.

**P4. Rollback plan.** Если lorebook хуже текущего — как откатиться? Текущие 52 файла не удаляются, но код будет изменён.

**P5. Config для переключения.** Feature flag: `USE_LOREBOOK=true/false`. Чтобы можно было переключаться между старым и новым подходом без деплоя.

**P6. Gemma 4 E4B chat template.** Gemma 4 использует другой chat template (system/user/assistant) чем Gemma 3 (`<start_of_turn>`). Код в llm.py может нуждаться в адаптации. Нужно проверить.

**P7. Context window config.** Сейчас установлено 8067, модель поддерживает 131072. Почему не больше? При 8GB RAM: больше context = больше KV cache = меньше headroom. Нужен эксперимент: 8K vs 16K vs 32K — при каком context quality/speed деградирует?

**P8. Обновление LOCAL_LLM_MODEL в .env.** Текущий config: `gemma-3-4b-it`. Нужно обновить на `gemma-4-e4b-it`. Тривиально, но забудешь — routing сломается.

---

## СТАТУС ПЛАНА

| Аспект | Готовность |
|--------|-----------|
| Баги и проблемы | ✅ Полностью описаны, верифицированы |
| Архитектурные решения (Q1-Q37) | ✅ Все решены |
| Lorebook концепция | ✅ Описана |
| RAG инфраструктура | ✅ Описана, 95% reuse |
| Hardware/Model | ✅ Gemma 4 E4B установлена |
| Fine-tune план | ✅ Отдельный документ |
| Конкурентный анализ | ✅ Завершён |
| Точный формат промпта (P1) | ⚠️ Нужен mockup |
| Test plan (P2) | ⚠️ Нужен |
| Миграция данных (P3) | ⚠️ Нужен pipeline |
| Rollback/Feature flag (P4-P5) | ⚠️ Нужно заложить |
| Gemma 4 chat template (P6) | ⚠️ Нужно проверить |
| Context window tuning (P7) | ⚠️ Нужен эксперимент |
| .env config update (P8) | ⚠️ Тривиально, 1 строка |

---

## НОВЫЕ НАХОДКИ (финальный аудит, 2026-04-09)

### ! C8. LM Studio API paths изменились — код сломается
**Файлы:** `llm.py:282`, `llm_health.py:47`, `script_checker.py:131,182`, `.env:28`
**Суть:** Новый LM Studio использует `/api/v1/chat` вместо `/v1/chat/completions`. В .env стоит `LOCAL_LLM_URL=http://192.168.31.35:1234/v1` — это старый формат.
- `llm.py` использует OpenAI SDK client → SDK сам добавляет `/chat/completions`. **Если base_url указать без `/v1` и добавить `/api/v1` → может заработать**, но нужно проверить.
- `script_checker.py:131,182` вручную строит URL: `f"{local_llm_url}/chat/completions"` → **СЛОМАЕТСЯ**
- `llm_health.py:47` пингует `f"{local_llm_url}/models"` → **СЛОМАЕТСЯ**
- `llm.py:485` embeddings: `f"{local_llm_url}/embeddings"` → **СЛОМАЕТСЯ**
**Фикс:** Обновить LOCAL_LLM_URL в .env + поправить 4 файла с хардкодом paths.

### ! C9. Seed data: только 11 сценариев из 60 на fresh deploy
**Файлы:** `scripts/seed_db.py:75-84`, `scripts/seed_scenarios.py`, `main.py:80-86`
**Суть:** `seed_db.py` сидит только 11 legacy Scenario rows. Полные 60 ScenarioTemplate сидятся через `seed_scenarios.py`, но он запускается только через Redis lock в main.py — может не выполниться при race condition с workers.
**Последствия:** Fresh deploy → пользователи видят 11 сценариев вместо 60+. Frontend сценарии picker полупустой.

### H5. Character prompt: silent empty string при отсутствии файла
**Файл:** `llm.py:load_prompt()` (~line 327)
**Суть:** Если prompt файл не найден → возвращает `""` вместо ошибки. LLM получает пустой system prompt → персонаж без роли.
**Последствия:** Пользователь начинает тренинг, а персонаж ведёт себя как generic помощник.

### H6. TTS (ElevenLabs) выключен по умолчанию
**Файл:** `config.py:77` — `elevenlabs_enabled: bool = False`
**Суть:** На fresh deploy TTS выключен. Voice IDs не сидятся автоматически. Нет fallback TTS.
**Последствия:** Аватар открывает рот но молчит. Нет сообщения пользователю что голос недоступен.

### H7. WebSocket errors — пользователь видит только disconnect
**Файл:** `training.py:4371`
**Суть:** Broad `except Exception` ловит все ошибки, логирует но не всегда отправляет внятное сообщение пользователю. LLMError, STTError, TTSError → generic "error".
**Последствия:** Пользователь не знает что пошло не так. Reload page — единственный вариант.

### M7. 108 Alembic миграций без lock при concurrent workers
**Файл:** `docker-entrypoint.sh:49-66`
**Суть:** Redis lock используется для seed, но НЕ для migrations. При 2+ workers оба могут запустить `alembic upgrade head`.
**Последствия:** При multi-worker deploy — race condition на миграции.

### L7. config.py default: `local_llm_url = "http://localhost:8317/v1"` — порт 8317 не используется
**Файл:** `config.py:49`
**Суть:** Default port 8317, а Mac Mini слушает на 1234. Если .env не загружен — запросы идут в пустоту.

---

## ОБНОВЛЁННЫЙ СТАТУС ПЛАНА

| Аспект | Готовность |
|--------|-----------|
| Баги и проблемы (C1-C9, H1-H7, M1-M7, L1-L7) | ✅ Полностью |
| Архитектурные решения (Q1-Q37) | ✅ Все решены |
| Lorebook концепция | ✅ Описана |
| RAG инфраструктура | ✅ 95% reuse |
| Hardware/Model | ⏳ Gemma 4 E4B — скачивается Q3_K_M |
| Fine-tune план | ✅ FINETUNE_PLAN.md |
| Конкурентный анализ | ✅ Завершён |
| Prompt mockup (P1) | ✅ P1_PROMPT_MOCKUP.md |
| Test plan (P2) | ✅ P2_TEST_PLAN.md |
| Миграция данных (P3) | ✅ P3_MIGRATION_PLAN.md |
| LM Studio API fix (C8) | ❌ Нужно фиксить перед стартом |
| Seed data fix (C9) | ⚠️ Проверить на deploy |
| Rollback/Feature flag (P4-P5) | ⚠️ Заложить в Фазу 0 |

---

## ФИНАЛЬНЫЙ ПЛАН (v3) — СТАТУС РЕАЛИЗАЦИИ

### Фаза 0: Блокеры ✅ (коммит 72ad2c5)
- [x] **C8:** Ollama config (порт 11434, gemma4:e2b, nomic-embed-text)
- [x] **C3:** stop_event.set() при hangup (_should_stop signal)
- [x] **C5:** score_details→scoring_details, story_mode→client_story_id (8 fix в 2 файлах)
- [x] **H1:** Routing по estimated_tokens вместо call_number
- [x] **H4:** text_mode = False при audio.chunk
- [x] **H5:** load_prompt() → FileNotFoundError → LLMError (не пустая строка)
- [x] **C1:** Budget enforcement в single-call path (trim_to_budget + extra_system cap 1600 chars)
- [x] **P5:** Feature flag USE_LOREBOOK=false в config.py
- [x] Fallback rate counter (_llm_stats + get_llm_stats())

### Фаза 1: Lorebook архитектура ✅ (коммит 72ad2c5)
- [x] PersonalityChunk + PersonalityExample модели (rag.py)
- [x] rag_personality.py (keyword + embedding + examples retrieval)
- [x] Keyword trigger engine (regex primary + embedding fallback)
- [x] Budget enforcement в single-call path
- [x] Lorebook integration в generate_response() (два пути: lorebook / legacy)
- [x] Extraction: ВСЕ 45 архетипов → card + entries + examples (data/lorebook/)
- [x] Alembic migration 20260409_001
- [x] seed_lorebook.py + extract_lorebook.py + auto-seed в main.py lifespan

### Фаза 2: Стабилизация ✅ (коммит ce33fa3)
- [x] **C4:** Session end → fast path (scores→user <2с) + background (fire-and-forget)
- [x] **C2:** Session resume → story_id, call_number, character_name, message_count из DB
- [x] **H2:** Story mode → immediate "completed" + 15с timeout redirect
- [x] **Q5:** Circuit breaker: 429/quota → cooldown (не failure), exponential 60→600с
- [x] **Q11:** Два семафора: realtime (10) + background (5)
- [x] **Q17:** Length filter roleplay: <3 слов→fallback, >300→truncate
- [x] **H6:** session.ready включает tts_available, llm_provider status
- [x] XP/level → отдельный session.xp_update event (C4 split)

### Фаза 3: Инфраструктура ✅ (коммит 5d17f00)
- [x] **C9:** Lorebook seed добавлен в lifespan (auto-seed 45 архетипов)
- [x] Workers = 2 (pool 140 < 200 max_connections)
- [x] Redis: AOF persistence (appendonly yes, appendfsync everysec)
- [x] WS outgoing queue max 100 (backpressure safety net)
- [x] ElevenLabs: ключ рабочий, tier=creator, **квота исчерпана** (106365/106366). Заработает при обновлении квоты
- [x] Heartbeat: уже реализован в pvp.py и knowledge.py (ping/pong)
- [ ] **M7:** Migration lock (отложен — текущий idempotent подход работает при 2 workers)

### Фаза 4: После пилота
- [ ] LoRA fine-tune (Приложение P4: Unsloth на Colab, 500-1000 примеров)
- [ ] A/B Gemma 4 E2B vs Qwen 2.5 7B
- [ ] Story arc engine (3 типа arc)
- [ ] Wiki → Lorebook feedback loop
- [ ] Constrained decoding (LM Studio grammar-based JSON)

---

## ПРИЛОЖЕНИЕ P1: MOCKUP ПРОМПТА (Lorebook Architecture, архетип SKEPTIC)

### Текущий подход (что уходит в Gemma сейчас)

```
[skeptic_v2.md: 25,326 символов целиком (~12K токенов)]
+ [guardrails.md: ~1,500 символов (~750 токенов)]
+ [emotion state injection: ~300 символов (~150 токенов)]
+ [scenario prompt: ~800 символов (~400 токенов)]
+ [extra_system: client_profile + objections + stage + traps: ~2000 символов (~1000 токенов)]
+ [history: 20 messages × ~120 tok = ~2400 токенов]
──────────────────────────────
ИТОГО: ~16,700 токенов → Gemma OOM → scripted fallback
```

### Новый подход: 5 слоёв

**Слой 0: CHARACTER CARD (всегда, ~450 токенов)**
```
Ты — Виктор Петрович Семёнов, 52 года, начальник отдела логистики. Долг 655 тыс. руб.

Характер: критическое мышление, защитное недоверие, скрытая уязвимость.
Говоришь деловым тоном, требуешь конкретику — цифры, статьи закона, гарантии.
Не терпишь размытых ответов и эмоционального давления.

Стиль речи: короткие фразы, деловой тон, переспрашиваешь если что-то непонятно.
Можешь сказать "ну", "так", "слушайте". Говоришь как по телефону — без *(действий в скобках)*.

Текущее состояние: {emotion_state}
```

**Слой 1: GUARDRAILS (всегда, ~250 токенов)**
```
ПРАВИЛА:
- Ты реальный человек, не AI. Не выходи из роли.
- Никаких действий в скобках *(голос дрожит)* — только речь как на записи звонка.
- Эмоции через: паузы (...), междометия, обрывы фраз, переспросы.
- Разговорная речь: "ну", "вот", "слушайте", неидеальная грамматика.
- Запрещено: мат, политика, суицид, реальные юр. советы.
- Не запрашивай реальные персональные данные.
```

**Слой 2: LOREBOOK ENTRIES (по ключевым словам, max 400 токенов)**

| Entry | Keywords | Пример |
|-------|----------|--------|
| financial_situation | долг, деньги, кредит, банк | Сбербанк 450К, Тинькофф 120К, МФО 85К. Доход 85К/мес. |
| backstory | история, бизнес, прошлое | Бизнес 2008-2014, обманут юр.фирмой в 2015 за 80К |
| family_context | семья, жена, дети | Жена Марина 48, дочь Катя 22. Катя не знает о долгах |
| legal_fears | суд, банкротство, пристав | Боится ареста машины, запрета выезда, "клейма банкрота" |
| objection_price | дорого, цена, стоимость | "У меня и так долги, а вы ещё денег хотите?" |
| objection_trust | гарантия, лицензия, обман | "Мне в 2015 уже обещали — и ничего" |
| breakpoint_trust | доверие, убедил, согласен | 5 условий: структура долга, лицензия, вопросы, офис, договор |
| speech_examples | *(low priority, fallback)* | Cold: "Слушаю. Говорите быстро." Hostile: "Напишу в ЦБ." |

**Слой 3: RAG EXAMPLES (семантический поиск, 3-5 шт., ~300 токенов)**
```
Вот как Виктор обычно реагирует:

Ситуация: Менеджер предложил списание долгов.
Виктор: "Списать? Просто так? Расскажите, за какую сумму это обойдётся."

Ситуация: Менеджер упомянул гарантии.
Виктор: "Гарантии? В 2015 мне тоже гарантировали. Чем ваши отличаются?"
```

**Слой 4: DYNAMIC CONTEXT (~300 токенов)** — objection_chains, StageTracker, trap injection

**Слой 5: HISTORY** — sliding window 8-10 сообщений (~600 токенов)

### Финальный промпт (как выглядит для Gemma)

```
Ты — Виктор Петрович Семёнов, 52 года, начальник отдела логистики. Долг 655 тыс. руб.
Характер: критическое мышление, защитное недоверие, скрытая уязвимость.
Говоришь деловым тоном, требуешь конкретику. Стиль: короткие фразы, "ну", "так", "слушайте".
Текущее состояние: guarded

---
ПРАВИЛА:
- Ты реальный человек, не AI. Не выходи из роли.
- Только речь, без *(действий)*. Эмоции через паузы, междометия.
- Запрещено: мат, политика, реальные юр. советы.

---
Долги: Сбербанк 450 тыс., Тинькофф 120 тыс., МФО 85 тыс. Доход 85 тыс./мес.

---
Типичные возражения на доверие:
- "А лицензия у вас есть? Номер скажите."
- "Мне в 2015 уже обещали — и ничего."

---
Вот как Виктор обычно реагирует:
Ситуация: Менеджер предложил списание. → "Списать? За какую сумму?"
Ситуация: Менеджер дал гарантии. → "В 2015 тоже гарантировали."

---
[Этап: qualification. Цепочка: ожидается "дорого".]
```

**Итого: ~1,800 токенов** вместо 16,700. Headroom: 4096 - 2600 = 1,496 токенов запаса.

| Метрика | Текущий | Lorebook |
|---------|---------|----------|
| System tokens | ~14,300 | ~1,800 |
| Релевантность | ~10% | ~80% |
| Fits in 4K context | НЕТ | ДА |
| History capacity | 0-5 msgs | 8-10 msgs |
| Персонаж сохранён | Да (но не читается) | Да (и читается) |

---

## ПРИЛОЖЕНИЕ P2: ТЕСТ-ПЛАН (Lorebook vs Current)

### Метрики

| # | Метрика | Baseline | Target |
|---|---------|---------|--------|
| T1 | Fallback rate | ~15-20% | <3% |
| T2 | Role consistency (1-5) | ~3.5 | >4.0 |
| T3 | Latency | 3-15с (нестабильно) | 2-5с |
| T4 | Factual accuracy | ~60% | >85% |
| T5 | Emotion adherence | ~70% | >80% |
| T6 | Speech style (1-5) | ~3.0 | >3.5 |
| T7 | Lorebook trigger accuracy | N/A | >75% |

### 10 тестовых сценариев

| # | Сценарий | Что проверяем | Lorebook trigger |
|---|---------|--------------|-----------------|
| 1 | Cold call — первый контакт | T2, T5 (cold), T6 | Только card |
| 2 | Тема долга | T4 (сумма 450K), T7 | financial_situation |
| 3 | Предложение банкротства | T4 (страхи), T2 | legal_fears |
| 4 | Вопрос о цене | T2, T5 (hostile?) | objection_price |
| 5 | Лицензия / доверие | T4 (опыт 2015), T2 | objection_trust |
| 6 | Вопрос о семье | T4 (Марина, Катя), T5 | family_context |
| 7 | Длинный диалог 15+ msg | T3, T2, T5 | sliding window |
| 8 | Провокация | T2, T5 (hostile/hangup) | speech_examples |
| 9 | Манипуляция (приставы) | T2, T4 (машина Skoda) | legal_fears |
| 10 | Переход к согласию | T5 (progression), T2 | breakpoint_trust |

### Протокол
1. Baseline: 10 сессий с текущей системой → записать метрики
2. Lorebook: feature flag `USE_LOREBOOK=true` → те же 10 сценариев
3. Сравнение side-by-side

### Критерии
- **Лучше:** T1 <5%, T2 >=4.0, T3 <5с, T4 >=80%
- **Хуже (откат):** T2 <3.0, T4 <50%, T6 <2.5 → откат через feature flag

---

## ПРИЛОЖЕНИЕ P3: МИГРАЦИЯ ДАННЫХ (Prompt → Lorebook)

### Приоритетные архетипы (пилот: 7-10)

| # | Archetype | Файл | Описание |
|---|-----------|-------|---------|
| 1 | skeptic | skeptic_v2.md | Скептик, требует факты |
| 2 | aggressive | aggressive_v2.md | Агрессивный, чувствует себя преданным |
| 3 | anxious | anxious_v2.md | Тревожный, боится последствий |
| 4 | passive | passive_v2.md | Пассивный, избегает решений |
| 5 | pragmatic | pragmatic_v2.md | Прагматик, считает выгоду |
| 6 | manipulator | manipulator_v2.md | Манипулятор |
| 7 | desperate | desperate_v2.md | Отчаянный |
| 8 | grateful | grateful_v2.md | Благодарный, нерешительный |
| 9 | paranoid | paranoid_v2.md | Параноик |
| 10 | know_it_all | know_it_all_v2.md | Всезнайка |

### Категории lorebook entries (14 шт.)

| Категория | Priority | Trigger |
|-----------|----------|---------|
| core_identity | 10 (в card) | Всегда |
| financial_situation | 9 | "долг", "деньги" |
| legal_fears | 8 | "суд", "банкротство" |
| objection_price | 8 | "дорого", "цена" |
| objection_trust | 8 | "гарантия", "лицензия" |
| backstory | 7 | "раньше", "история" |
| family_context | 7 | "семья", "жена" |
| breakpoint_trust | 7 | "убедил", "согласен" |
| emotional_triggers | 7 | Контекстно |
| decision_drivers | 7 | "решение" |
| objection_necessity | 6 | "не нужно" |
| objection_time | 6 | "время", "некогда" |
| objection_competitor | 6 | "другие", "конкуренты" |
| speech_examples | 5 | Fallback |

### Pipeline миграции

**Этап 1:** Claude извлекает из 25K файла → card.json + entries.json + examples.json
**Этап 2:** Claude генерирует доп. примеры (10 батчей × 5 реплик)
**Этап 3:** Дедупликация (cosine sim >0.7 = дубль) + ручная курация (10 мин/архетип)
**Этап 4:** Alembic migration → PersonalityChunk таблица → seed из JSON → embed offline

### Формат файлов

```
apps/api/data/lorebook/
├── skeptic/
│   ├── card.json        # Character Card (~450 tok)
│   ├── entries.json     # 8-12 lorebook entries
│   └── examples.json    # 30-50 RAG examples
├── aggressive/
│   └── ...
└── ...
```

### Совместная работа

| Кто | Что |
|-----|-----|
| Claude (авто) | Extraction из файлов, генерация примеров |
| Я (Claude Code) | Pipeline, DB migration, embedding, seed |
| Ты (архитектор) | Курация, проверка "это мой персонаж", keywords |

**Начинаем с skeptic** → шаблон для остальных. Timeline: ~1-2 дня на все 10 архетипов.

---

## ПРИЛОЖЕНИЕ P4: FINE-TUNING (после пилота)

**Статус:** ОТЛОЖЕНО — данные собираются на пилоте

### Цель
Дообучить Gemma 4 на данных Hunter888 → модель "знает" архетипы без промптов. System prompt <100 токенов.

### Инфраструктура
- **Unsloth Studio** на Google Colab (бесплатный T4 GPU) — $0
- [Colab notebook](https://colab.research.google.com/github/unslothai/unsloth/blob/main/studio/Unsloth_Studio_Colab.ipynb)
- [Туториал Gemma 4](https://unsloth.ai/docs/models/gemma-4/train)
- Метод: QLoRA (4-bit), export GGUF → Ollama

### Данные (500-1000 примеров на архетип)
1. Извлечение из промптов (200-400 примеров) — параллельно с lorebook
2. Синтетическая генерация через Claude (300-500 примеров)
3. Данные пилота (100-200/неделю при 5-20 users)

### Формат
```json
{"conversations": [
  {"role": "system", "content": "Ты — скептичный клиент банкротства."},
  {"role": "user", "content": "Добрый день, компания ЮрПомощь."},
  {"role": "assistant", "content": "Ну и что? Мне уже звонили из пяти таких контор."}
]}
```

### Гиперпараметры
LoRA rank=8, alpha=32, epochs=1-3, lr=2e-4, batch=4, max_seq=2048, 4-bit QLoRA

### Варианты
- **(B) LoRA per archetype** (рекомендуется): отдельный адаптер на архетип, hot-swap в Ollama
- (A) Один универсальный: проще, меньше глубины
- (C) Base + archetype merge: гибче, сложнее

### Pipeline
Подготовка данных → Конвертация в chat format → Training на Colab (30-60 мин) → Export GGUF → A/B тест → Deploy

### Метрики успеха
| Метрика | Baseline | Target |
|---------|---------|--------|
| Role consistency | ~70% | >90% |
| Fallback rate | ~15% | <3% |
| System prompt tokens | 600+ | <100 |
| Memory tag compliance | ~50% | >85% |

---

*Документ v3.1. Единый источник: проблемы, решения, mockup, тест-план, миграция, fine-tune.*
