# Hunter888 — AI-платформа тренировки менеджеров по банкротству

Голосовые симуляции звонков с AI-клиентами, RAG по 127-ФЗ + курируемая база судебной практики, 10-слойная оценка каждой сессии, PvP-арена с сезонами и лигами.

**Одна сессия:** менеджер ↔ AI-клиент (один из 100 архетипов) → диалог на русском → судья оценивает по 10 метрикам → разбор с цитатами из 127-ФЗ и идеальной репликой.

---

## 🗺️ Карта платформы

```
Hunter888
├── 👤 Роли (UserRole)                     ├── 💰 Подписки (PlanType)
│   ├── manager          (обычный продажник)    │   ├── scout     бесплатный / 14д триал
│   ├── rop              (team lead)            │   ├── ranger    базовый платный
│   ├── methodologist    (контент-автор)        │   ├── hunter    pro
│   └── admin            (система)              │   └── master    enterprise  ← auto для admin/rop/methodologist
│
├── 📱 Фронтенд (apps/web) — Next.js 15 App Router
│   ├── (landing)/          публичное (pricing, лендинги)
│   ├── login, register, auth, onboarding
│   ├── home                дашборд пользователя
│   ├── training            roleplay-сессии (tabs: Сценарии/Назначения/Конструктор)
│   │   ├── [id]/           активная сессия (chat + voice call)
│   │   └── crm/[storyId]/  multi-call history by client
│   ├── pvp                 лобби Арены (League/Teams/Mistakes/Tournament/Tutorial)
│   │   ├── duel/[id]       1×1 PvP
│   │   ├── rapid-fire      серия коротких раундов
│   │   ├── gauntlet        PvE лестница
│   │   ├── tournament      турнир bracket
│   │   ├── team/[teamId]   2×2 командный
│   │   ├── quiz/[sessId]   knowledge quiz
│   │   ├── spectate/[mid]  наблюдение за матчем
│   │   ├── league          недельная лига Duolingo-style
│   │   ├── teams           B2B команды офисов
│   │   ├── mistakes        SM-2 + Leitner повтор ошибок
│   │   ├── tutorial        3-раундовый walkthrough для новичков
│   │   └── leaderboard     arena-specific ranking
│   ├── history             персональная история (сохраняется НАВСЕГДА)
│   ├── leaderboard         глобальный лидерборд (Hunter score)
│   ├── clients             CRM клиентов (scope зависит от роли)
│   ├── dashboard           Team Dashboard для ROP/admin
│   ├── dashboard/          team dashboard (ROP/admin)
│   │   ├── (overview)      обзор / heatmap / weak-links / ROI / benchmark
│   │   ├── methodology/    Сценарии · Контент Арены · Скоринг · Wiki · Reviews · Качество AI
│   │   ├── activity/       AuditLogPanel · Attachment uploads (TZ-4 D7.7b)
│   │   └── system/         только admin: Пользователи · Client Domain · Runtime Metrics
│   ├── results/[id]        пост-матч разбор
│   ├── stories/[storyId]   deep-dive сессии
│   ├── wiki                Manager Wiki (автогенерируется)
│   ├── profile, settings, notifications, pricing
│
├── 🔧 Бэкенд (apps/api) — FastAPI + SQLAlchemy 2 async
│   ├── app/main.py         ← entry, 41 routers / 331+ routes зарегистрировано
│   ├── app/api/            HTTP endpoints (по доменам)
│   │   ├── auth.py, users.py, training.py, knowledge.py
│   │   ├── pvp.py, tournament.py, subscription.py
│   │   ├── arena_lifelines.py  ← hint/skip/fifty (Phase A)
│   │   ├── arena_powerups.py   ← ×2 XP (Phase C)
│   │   ├── tutorial.py         ← первый-матч gate (Phase C)
│   │   ├── gamification.py     ← league/streak/leaderboard
│   │   └── ...
│   ├── app/ws/             WebSocket endpoints
│   │   ├── training.py         roleplay chat + voice
│   │   ├── pvp.py              5 PvP режимов (duel/rapid/gauntlet/team)
│   │   ├── knowledge.py        solo + PvP quiz
│   │   └── notifications.py
│   ├── app/services/       бизнес-логика (~60 файлов)
│   │   ├── llm.py              LLM gateway (Gemini + Claude + OpenAI fallback)
│   │   ├── pvp_judge.py        10-слойный судья для PvP
│   │   ├── entitlement.py      plan limits + ELEVATED_ROLES exemption
│   │   ├── weekly_league.py    Monday form / Sunday finalize
│   │   ├── spaced_repetition.py SM-2 + Leitner boxes
│   │   ├── scheduler.py        cron all background jobs
│   │   ├── arena/
│   │   │   ├── lifelines.py        hint/skip/50-50 Redis state
│   │   │   ├── powerups.py         ×2 XP active modifier
│   │   │   └── audio.py            TTS для Arena
│   │   └── quiz_v2/             knowledge quiz pipeline
│   ├── app/models/         SQLAlchemy models (50+ таблиц после TZ-1..TZ-4)
│   │   ├── user.py             User, Team, UserConsent, UserFriendship
│   │   ├── training.py         TrainingSession, Message, CallRecord
│   │   ├── pvp.py              PvPDuel, PvPRating, RapidFireMatch, GauntletRun
│   │   ├── knowledge.py        KnowledgeQuizSession, UserAnswerHistory
│   │   ├── subscription.py     UserSubscription, PlanType
│   │   ├── roleplay.py         ArchetypeCode, ClientProfile, EpisodicMemory
│   │   └── ...
│   ├── app/mcp/            MCP tools для AI-клиента
│   │   └── tools/              generate_image, geolocation, fetch_archetype
│   ├── app/archetypes/     100 архетипов (catalog + registry)
│   └── alembic/versions/   миграции БД (20260427_004 на head — TZ-4 B1)
│
├── 📚 RAG corpus
│   ├── 127-ФЗ              полный текст + судебная практика
│   ├── legal_knowledge_chunks  curated fact-cards
│   ├── legal_document      hierarchical law (chapter→article→item)
│   └── UserAnswerHistory   SRS индекс для повтора
│
└── 🗂️ Data preservation contract
    История пользователя НАВСЕГДА сохраняется независимо от подписки.
    Триал закончился → юзер становится scout → данные НЕ удаляются.
    См. комментарии на TrainingSession и KnowledgeQuizSession моделях.
```

---

## 👤 Кто что видит (role-aware navigation)

**Нав-меню = функция(role)** — нет единого плоского списка. Каждая роль получает свой набор пунктов.

| Роль | Top-nav |
|---|---|
| **manager** | Центр · Тренировка · Арена · История · Лидерборд · Мои клиенты |
| **rop** | Центр · **Команда** · Тренировка · Арена · Лидерборд · Клиенты · История · **Дашборд** (с вкладками методолога) |
| **admin** | Центр · Команда · Тренировка · Арена · Лидерборд · Клиенты · **Дашборд** (включая Систему/Аудит) |

> Роль `methodologist` была удалена в апреле 2026 — все методологические функции (Сценарии, Контент Арены, Скоринг, Wiki, Reviews, Качество AI) теперь живут внутри `/dashboard` под вкладкой **Методология** и доступны ROP/admin. См. PR #46-48.

**PlanChip** (индикатор плана) — отображается только у `manager` (у elevated ролей всегда master).

Реализовано в: [apps/web/src/components/layout/Header.tsx](apps/web/src/components/layout/Header.tsx) — функция `buildNavForRole()`.

---

## 💰 Подписки и лимиты

| План | Сессий/день | PvP/день | RAG/день | AI Coach | Export | Team | Voice clone |
|---|---|---|---|---|---|---|---|
| **scout** (free, 14д триал) | 3 | 2 | 5 | ❌ | ❌ | ❌ | ❌ |
| **ranger** | 10 | 10 | 50 | ✅ | ❌ | ❌ | ❌ |
| **hunter** (pro) | ∞ | ∞ | 500 | ✅ | ✅ | ✅ | ❌ |
| **master** (enterprise) | ∞ | ∞ | ∞ | ✅ | ✅ | ✅ | ✅ |

- `admin` / `rop` / `methodologist` → **автоматически master** (ELEVATED_ROLES exemption).
- 429 на лимите возвращает structured body `{feature, plan, limit, used, message}` → глобальный `PlanLimitModal` показывает upsell вместо generic toast.
- Реализовано: [apps/api/app/services/entitlement.py](apps/api/app/services/entitlement.py), [apps/api/app/core/deps.py](apps/api/app/core/deps.py).

---

## 🏛️ Ключевые сценарии использования

### 1. Новый менеджер — первая сессия

```
/register → /onboarding → /home
                           ↓
                   Сценарии / Назначенные / Конструктор
                           ↓
                   /training/[sessionId]  (chat + voice optional)
                           ↓
                   /results/[sessionId]   (10-слойный разбор)
```

### 2. Первый заход в Арену

```
/pvp → welcome-экран "Добро пожаловать"
        ↓
   [Пройти тренировку]           [Пропустить → на матч]
        ↓                                    ↓
   /pvp/tutorial (3 раунда)           matchmaking
        ↓                                    ↓
   POST /tutorial/arena/complete      /pvp/duel/[id]
        ↓                                    ↓
   /pvp  (lobby с sub-nav tiles)     /results + CTA
```

### 3. ROP смотрит команду

```
/home → nav «Команда» → /dashboard
                            ↓
              Обзор / Heatmap / Weak-links / ROI / Benchmark
                            ↓
              клик на участника → его /profile + training history
```

### 4. ROP ведёт контент и качество (раньше — методолог)

```
/dashboard → таб «Методология»
                     ↓
   Сценарии · Контент Арены · Скоринг · Wiki · Reviews · Качество AI
                                                              ↓
                                            (TZ-4 D7.7a — агрегаты по командам:
                                             persona conflicts / policy violations)
```

### 5. Admin проверяет 152-ФЗ compliance + работу AI

```
/dashboard → табы «Активность» (audit-log)  и  «Система» (admin-only)
                ↓                                ↓
   AuditLogPanel — фильтр       Пользователи · Client Domain · Runtime Metrics
   по attachment uploads        (Phase 0 hotfixes / TZ-2 §18 observability)
   (TZ-4 D7.7b)
```

---

## 🎮 Арена — 5 режимов + sub-surfaces

| Режим | Файл | Формат | Rating |
|---|---|---|---|
| **Duel 1×1** | `/pvp/duel/[id]` | Roleplay chat (2 раунда) | Glicko-2, PvP ELO |
| **Rapid-Fire** | `/pvp/rapid-fire/[matchId]` | 5 раундов × разные архетипы | Glicko-2 |
| **Gauntlet (PvE)** | `/pvp/gauntlet/[runId]` | Серия дуэлей до 2 проигрышей | PvE рейтинг |
| **Tournament** | `/pvp/tournament` | Bracket плей-офф | Titled события |
| **Team 2×2** | `/pvp/team/[teamId]` | Two sellers vs two clients | Team ELO |
| **Arena Quiz** | `/pvp/quiz/[sessionId]` | Knowledge Q&A (1-8 players) | Solo/PvP |

Каждый режим использует unified компоненты: **CountdownOverlay** (3..2..1) · **CoachingCard** (идеальная реплика + статьи 127-ФЗ) · **CelebrationBurst** · **WrongShake** · **ArenaAudioPlayer** (TTS) · **sfx pack**.

Lifelines (Hint / Skip / 50-50) + Power-ups (×2 XP) работают в Arena Quiz + Rapid / PvE (по конфигу квоты).

---

## 🛠️ Технологический стек

**Frontend:** Next.js 15 (App Router) + TypeScript + Tailwind + Zustand + Framer Motion + Radix UI + Sonner (toasts) + lucide-react

**Backend:** FastAPI + SQLAlchemy 2 async + PostgreSQL + pgvector + Redis + Alembic

**LLM:** Gemini 2.5 (primary) / Claude Opus (судья) / GPT-4o (fallback) / локальный Gemma 3 4B на Mac Mini

**TTS / STT:** ElevenLabs + navy.api (nano-banana-2 для изображений) + Web Speech API (ru-RU) в браузере

**Payment:** YooKassa + Stripe webhooks

---

## 🚀 Как запустить локально

### Требования
- Node.js 20+ с npm
- Python 3.13 + venv
- PostgreSQL 15+ с pgvector
- Redis 7+
- `.env` в `apps/api/` с ключами LLM / payment / DB

### Frontend
```bash
cd apps/web
npm install
npm run dev          # → http://localhost:3000
npm run types:check  # TS compile
```

### Backend
```bash
cd apps/api
source .venv/bin/activate
alembic upgrade head   # миграции
uvicorn app.main:app --reload   # → http://localhost:8000
```

### Всё разом через Docker
```bash
make dev      # поднять всё (web + api + db + redis)
make test     # тесты обеих сторон
make lint     # линт
make migrate  # alembic upgrade head
make seed     # dev-данные (seed users + archetypes)
```

---

## 📦 Ключевые файлы (где искать)

| Хочешь изменить | Смотри |
|---|---|
| Добавить пункт в nav | `apps/web/src/components/layout/Header.tsx` → `buildNavForRole()` |
| Поменять лимиты плана | `apps/api/app/services/entitlement.py` → `PLAN_LIMITS` |
| Судья PvP | `apps/api/app/services/pvp_judge.py` → `JUDGE_SYSTEM_PROMPT` |
| Добавить архетип | `apps/api/app/archetypes/catalog/` + `scripts/archetypes/generate_catalog.py` |
| Новый lifeline/power-up | `apps/api/app/services/arena/{lifelines,powerups}.py` + фронт hook |
| Новый WS event | `apps/api/app/ws/{training,pvp,knowledge}.py` — receive loop + emit; добавить в `ALLOWED_EVENT_TYPES` (TZ-4 D1.1) |
| Добавить scheduler job | `apps/api/app/services/scheduler.py` → новый `_check_*` метод |
| Миграция БД | `apps/api/alembic/versions/` + update модель в `app/models/` |
| Записать `ClientInteraction` или `DomainEvent` | НИКОГДА напрямую — только через `app.services.client_domain.*` (TZ-1) |
| Загрузить attachment | только `attachment_pipeline.upload_for_session` → 11-state machine + `domain_event_id NOT NULL` (TZ-4 §7) |
| Изменить персону клиента | только `persona_memory.upsert_for_lead` / `lock_slot` / `capture_for_session` (TZ-4 §9) |
| Опубликовать knowledge chunk | `knowledge_review_policy.{publish,dispute,mark_outdated}` (TZ-4 §8) |
| Завершить training-сессию | `ConversationCompletionPolicy.finalize_training_session` — все 7 терминальных путей (TZ-1 §3) |

---

## 🧱 Domain architecture (TZ-1...TZ-4)

С апреля 2026 платформа работает на четырёх связанных доменных контрактах. Каждый закрыт **AST-гардом** в `tests/` — любой PR, который пытается обойти каноничного писателя, падает в CI **до** ревью.

### TZ-1 — Unified Client Domain Events
> [docs/TZ-1_unified_client_domain_events.md](docs/TZ-1_unified_client_domain_events.md) · [docs/clients_domain_architecture.md](docs/clients_domain_architecture.md)

Единый event-log на `lead_clients`. Четыре runtime-инварианта (см. §3 [CLAUDE.md](CLAUDE.md)):

1. **`ClientInteraction`** пишется только через `app.services.client_domain.create_crm_interaction_with_event`.
2. **`DomainEvent(lead_client_id=...)`** конструируется только в `client_domain.emit_domain_event`.
3. **Завершение сессии** — единственный путь через `ConversationCompletionPolicy.finalize_*` (7 терминальных путей сведены к одному writer).
4. **`correlation_id` NOT NULL** на всех `DomainEvent` — иначе ломаются join'ы в timeline (§15.1).

Реализация: [apps/api/app/services/client_domain.py](apps/api/app/services/client_domain.py), [apps/api/app/services/conversation_completion_policy.py](apps/api/app/services/conversation_completion_policy.py). Гарды: [tests/test_client_domain_invariants.py](apps/api/tests/test_client_domain_invariants.py).

### TZ-2 — Runtime Integrity Guards
> [docs/TZ-2_runtime_integrity_guards_followup.md](docs/TZ-2_runtime_integrity_guards_followup.md)

Канонические колонки `Session.mode` / `runtime_type` (§6.2/6.3) + единый `runtime_finalizer` (REST==WS XP parity, идемпотент). 5 минимальных guards в `runtime_guard_engine` (§7), `TaskFollowUp` dual-write contract, `§18` runtime observability (blocked_starts / finalize / followup_gap метрики). Wired в REST + WS handlers; FE читает canonical fields на call-page.

### TZ-3 — Scenario Lifecycle
> [docs/TZ-3_constructor_scenario_version_contracts.md](docs/TZ-3_constructor_scenario_version_contracts.md)

Сценарий = **template** + immutable **versions**. Workflow `draft → publish` через [scenario_publisher.py](apps/api/app/services/scenario_publisher.py); auto-publish-on-update убран. Runtime resolver выбирает `version`-first (упавший template не ломает live-сессии). Sub-tab «Сценарии» внутри Методологии: list + Publish + version history.

### TZ-4 — Attachments / Knowledge / Persona / Conversation Policy
> [docs/TZ-4_attachments_knowledge_persona_policy.md](docs/TZ-4_attachments_knowledge_persona_policy.md) · [docs/ARCHITECTURE_AUDIT_2026_04_28.md](docs/ARCHITECTURE_AUDIT_2026_04_28.md)

Четыре новых сервиса под единым AST-гардом каждый:

* **`attachment_pipeline`** (§7) — 11-state machine (`uploaded → scanned → ocr_done → classified → linked → ready` + ошибочные ветки), pre-generated UUID + `domain_event_id NOT NULL` через `begin_nested()` savepoint (D7.3 emit-first refactor). 9 канонических событий.
* **`persona_memory`** (§9) — `MemoryPersona` (per-lead identity) + `SessionPersonaSnapshot` (frozen-on-INSERT для §9.2 invariant 1). Single sanctioned writer; `lock_slot` атомарно бампит `version` + эмитит event.
* **`knowledge_review_policy`** (§8) — статусы `published/disputed/needs_review/expired` + admin endpoints. NBA-фильтр `filter_safe_knowledge_refs` исключает `disputed`/`needs_review` из ответов AI-клиента. TTL cron на `expires_at`.
* **`conversation_policy_engine`** (§10) — 6 runtime-проверок реплик AI (unjustified_identity_change, missing_next_step, etc.) в **warn-only** режиме до пилота; live counters пушатся в FE через WS outbox.

**Admin surfaces:** [AI quality dashboard](apps/web/src/app/dashboard/methodology/) (D7.7a, агрегаты по командам), [AuditLogPanel](apps/web/src/components/audit/) с фильтром по attachment-uploads (D7.7b), [ClientMemorySection](apps/web/src/components/persona/) на `/clients/[id]` (D7.7c).

### AST-гарды и канонические писатели

| Домен | Single writer | AST-guard test |
|---|---|---|
| `ClientInteraction` / `DomainEvent` | `client_domain.create_crm_interaction_with_event` / `emit_domain_event` | [test_client_domain_invariants.py](apps/api/tests/test_client_domain_invariants.py) |
| Session completion | `ConversationCompletionPolicy.finalize_*` | (поведенческий: `test_rest_ws_finalize_parity.py`) |
| `Attachment` | `attachment_pipeline` | [test_attachment_invariants.py](apps/api/tests/test_attachment_invariants.py) |
| `MemoryPersona` / `SessionPersonaSnapshot` | `persona_memory` | [test_persona_invariants.py](apps/api/tests/test_persona_invariants.py) |
| `LegalKnowledgeChunk` review fields | `knowledge_review_policy` | [test_knowledge_invariants.py](apps/api/tests/test_knowledge_invariants.py) |
| `GameClientEvent` / arena chunks | (различные) | [test_arena_chunk_invariants.py](apps/api/tests/test_arena_chunk_invariants.py) |

> **Правило для контрибьютора:** видишь `MemoryPersona(...)` где-то кроме `app/services/persona_memory.py` — это уже сломанный билд. Маршрутизируй через канонический сервис; расширение allow-list требует review § того ТЗ, к которому относится сущность.

---

## 📋 Journal изменений (recent)

### TZ-4 D7 + аудит (2026-04-27 → 2026-04-28)
- D7.1 cutover cleanup (PR #64), D7.3 pipeline emit-first + `domain_event_id NOT NULL` (PR #69), D7.6 runtime audit hook + WS push + FE live counters (PR #65)
- D7.7a/b/c — AI quality dashboard / AuditLogPanel / ClientMemorySection (PRs #66-68)
- B1 attachment status enum naming alignment со spec §7.1.1 (PR #73)
- C1 fix: Center button lead_client_required 400 (PR #72), C3 fix: PII в console.log на call page (PR #71)
- Architecture audit 2026-04-28: 9 improvements в одной поставке + spec drift каталог (PRs #75-77)
- Pilot tester guide + operator runbook (PR #74)
- Test cleanup: test_ws_resume + test_api_endpoints (PRs #78-79) — pre-existing advisory failures сведены к 0

### TZ-4 D1-D6 (2026-04-27)
- D1 foundation — alembic migration + 4 новые entities + AST allow-list (PR #57)
- D2 attachment_pipeline canonical writer + 9 events + AST guard (PR #59)
- D3 persona_memory + SessionPersonaSnapshot capture (PR #60)
- D4 knowledge_review_policy + admin endpoints + TTL cron (PR #61)
- D5 conversation_policy_engine — 6 проверок, warn-only mode (PR #62)
- D6 FE uplift — attachments × 11 statuses, knowledge queue, persona/policy badges (PR #63)

### TZ-3 + role consolidation (2026-04-26)
- Methodologist role retired → ROP наследует все права (PRs #46-48)
- Dashboard tabs: Команда / Активность / Методология / Система (PRs #40-43)
- TZ-3 C1-C5 — scenario lifecycle, publisher/validator, runtime resolver, sub-tab MVP, arena chunk schema (PRs #50-54)

### TZ-1 + TZ-2 (2026-04-24..25)
- TZ-1 client_domain foundation, repair, projector, parity, replay tests (181 тест в blocking scope CI)
- TZ-1 §15.1 invariant 4: correlation_id NOT NULL + GameClientEvent AST guard (PR #34)
- TZ-2 phases 0..5 — canonical mode/runtime_type, runtime_finalizer, runtime_guard_engine, TaskFollowUp dual-write, REST==WS finalize parity, FE canonical fields (PRs #19-27)
- TZ-2 §18 runtime observability в Системе/Runtime Metrics (PRs #33, #45)

### Phase D (hardening, 2026-04-20)
- WS idle heartbeat 30s ping + 120s kill на `/ws/pvp` и `/ws/knowledge`
- Composite index `knowledge_answers(session_id, user_id, created_at)` (migration 005)
- Structured 429 body с `{feature, plan, limit, used, message}`
- `fetchWithTimeout` 30s default в api.ts

### Phase C (differentiation + role-aware UX, 2026-04-20)
- **Role-aware navigation** — `buildNavForRole()` вместо плоского NAV_ITEMS
- **PlanChip + PlanLimitModal** — видимость подписки + upsell на 429
- **Power-ups** — активные модификаторы (×2 XP) в Arena Quiz
- **Tutorial match** — `/pvp/tutorial` 3-раундовый walkthrough (migration 004)
- **Teams leaderboard** — `/pvp/teams` B2B офисы продаж
- **Mistake Book** — `/pvp/mistakes` SRS повтор ошибок
- **Arena sub-nav tiles** — 5 карточек на `/pvp` (Лига / Команды / Ошибки / Турнир / Тренировка)
- **/admin hub** — раньше `/admin/audit-log` был orphan
- **Methodologist stub pages** — `/methodologist/scenarios`, `/methodologist/scoring`
- **History preservation contract** — задокументировано на моделях

### Phase B (retention, 2026-04-20)
- **Weekly League** — Duolingo-style cohort (Monday form / Sunday finalize cron)
- **LeagueHeroCard** + полная страница `/pvp/league`
- `/pvp/mistakes` Mistake Book (SM-2 + Leitner) — использует existing `/knowledge/srs/*`

### Phase A (Arena synchronization, 2026-04-20)
- Unified CoachingCard / CountdownOverlay / CelebrationBurst / sfx pack во всех 5 режимах
- Backend: coaching payload (`tip, ideal_reply, key_articles`) во всех PvP judge-эмитах
- Lifelines (Hint/Skip/50-50) — Redis state + REST API для всех режимов
- 7 колонок в миграции 003 (rag_chunk_links, qa_generated_at, difficulty_params_snapshot, pvp_duels analytics, quiz_participants progression, lifelines_usage_log, pvp_duels index)
- Sprint 4 sfx + lifelines + HintBubble + CoachingCard

### Phase 2 (earlier, 2026-04-19)
- Voice mode `/training/[id]/call` + shared WS provider
- Arena audio TTS narration
- Manager name extraction + quote-reply
- 3 MCP tools (generate_image, geolocation, fetch_archetype)

### Phase 1 (foundation, 2026-04-18)
- ArchetypeRegistry + 100 catalog files
- MCP infrastructure (`@tool`, executor, ws_events)
- LLM tool-calling loop
- `messages.media_url` + `messages.quoted_message_id`

---

## 🔐 Data preservation

**Критический business-rule:** история пользователя сохраняется НАВСЕГДА, независимо от подписки.

Если юзер:
- был на hunter-плане,
- отписался,
- откатился в scout,
- не заходил год,
- вернулся через год и подписался снова —

он увидит ВЕСЬ свой прогресс, все сессии, все достижения, все ошибки. Это задокументировано контрактом на моделях `TrainingSession` и `KnowledgeQuizSession`. Не добавляй `expires_at`, retention-cron, или plan-gated `WHERE` фильтры на эти таблицы.

Подтверждено аудитом (2026-04-20): все 19 таблиц истории связаны с `users.id` (CASCADE только на удаление самого User), нет cleanup-jobs, API endpoints истории не фильтруют по плану.

---

## 📚 Документация

**Технические задания (TZ):**
- [docs/TZ-1_unified_client_domain_events.md](docs/TZ-1_unified_client_domain_events.md) — единый event-log на `lead_clients`
- [docs/TZ-2_runtime_integrity_guards_followup.md](docs/TZ-2_runtime_integrity_guards_followup.md) — runtime invariants + finalizer
- [docs/TZ-3_constructor_scenario_version_contracts.md](docs/TZ-3_constructor_scenario_version_contracts.md) — scenario lifecycle (template → version)
- [docs/TZ-4_attachments_knowledge_persona_policy.md](docs/TZ-4_attachments_knowledge_persona_policy.md) — attachments / persona / knowledge / policy

**Архитектура и аудиты:**
- [docs/clients_domain_architecture.md](docs/clients_domain_architecture.md) — домен «Клиенты» (с §16 TZ-4 evolution)
- [docs/ARCHITECTURE_AUDIT_2026_04_28.md](docs/ARCHITECTURE_AUDIT_2026_04_28.md) — последний аудит (8 ranked items, 9 closed)
- [docs/roleplay_system_v2.md](docs/roleplay_system_v2.md) — роль-плей система v2
- [docs/RAG_ARENA_REDESIGN_TZ.md](docs/RAG_ARENA_REDESIGN_TZ.md) — RAG arena редизайн

**Пилот:**
- [docs/PILOT_TESTER_GUIDE.md](docs/PILOT_TESTER_GUIDE.md) — для тестеров
- [docs/PILOT_OPERATOR_RUNBOOK.md](docs/PILOT_OPERATOR_RUNBOOK.md) — для оператора пилота

**Прочее:**
- [docs/FRONTEND_TZ_v2.md](docs/FRONTEND_TZ_v2.md) — фронтенд ТЗ
- [docs/CI_LINT_DEBT.md](docs/CI_LINT_DEBT.md) — lint debt journal
- [CLAUDE.md](CLAUDE.md) — рабочие правила (git discipline, deploy flow, TZ-1 invariants)

---

## 🎯 Product invariants (не нарушать)

1. **История = навсегда** (см. выше)
2. **Навигация = функция(role)** — один источник правды
3. **Elevated роли (admin/rop) → master** — автоматически, не показываем PlanChip
4. **История ≠ подписка** — никаких gate-фильтров на `/history`
5. **Все 5 Arena режимов используют unified компоненты** (CountdownOverlay / CoachingCard / sfx / theme accent)
6. **WS heartbeat** на всех live endpoints — idle-kill 120s
7. **Unified 429 body** — `{feature, plan, limit, used, message}` для всех plan-limit проверок
8. **Lifelines + Power-ups квоты в Redis** с fail-open — никогда не блокирует геймплей при сбое Redis
9. **Domain writers = single source** (TZ-1..TZ-4) — `ClientInteraction`/`DomainEvent`/`Attachment`/`MemoryPersona`/`SessionPersonaSnapshot`/`LegalKnowledgeChunk` review fields. AST guards в CI.
10. **`correlation_id` NOT NULL** на всех `DomainEvent` — иначе `lead_client` timeline `LEFT JOIN` ломается.
11. **Session completion** через `ConversationCompletionPolicy` (7 терминальных путей → один writer).

---

## 🚦 Production readiness

| Слой | Статус |
|---|---|
| Alembic heads = current | ✅ `20260427_004 (head)` — TZ-4 B1 attachment naming |
| TS compile | ✅ 0 ошибок |
| Tests — total / blocking scope | ✅ 1962 collected, 181 в TZ-1 blocking scope (все green) |
| AST guards (canonical writers) | ✅ 6 доменов под гардом — см. таблицу выше |
| Domain events `correlation_id` NOT NULL | ✅ §15.1 invariant 4 enforced на DB-уровне |
| WS session resume + token refresh | ✅ test_ws_resume.py 13/13 |
| Conversation policy engine | ⚠️ warn-only до пилота (live counters работают, enforce_active не блокирует) |
| Knowledge review queue | ✅ admin endpoints + TTL cron + NBA фильтр `disputed`/`needs_review` |
| Attachment pipeline 11-state | ✅ pre-generated UUID + savepoint + emit-first invariant |
| CSRF middleware | ✅ double-submit cookie |
| Rate limits | ✅ все mutation endpoints + LLM-калории |
| WS idle-kill | ✅ все 3 endpoint (training / pvp / knowledge) |
| 429 upsell UX | ✅ PlanLimitModal global |
| Role-aware nav (3 персоны: manager/rop/admin) | ✅ methodologist retired |
| History preservation | ✅ контракт задокументирован |
| Auto-refresh tokens | ✅ mutex-guarded, circuit breaker |
| Pilot guides | ✅ tester guide + operator runbook (PR #74) |

---

## 🤝 Вклад / доступ

Pilot-продукт для ~50 активных менеджеров/день. Доступ — только по приглашению.

Для разработчиков: перед PR — `make lint && make test && alembic upgrade head` должны пройти.


**Тестовые учётные записи (seed):**

| Роль | Email | Пароль |
|---|---|---|
| Админ | `admin@trainer.local` | `Adm1n!2024` |
| РОП команды Sales | `rop1@trainer.local` | `Rop1!pass` |
| РОП команды B2B | `rop2@trainer.local` | `Rop2!pass` |
| Менеджер Иван Петров (Sales) | `manager1@trainer.local` | `Mgr1!pass` |
| Менеджер Мария Сидорова (Sales) | `manager2@trainer.local` | `Mgr2!pass` |
| Менеджер Дмитрий Козлов (B2B) | `manager3@trainer.local` | `Mgr3!pass` |
| Менеджер Ксения Морозова (B2B) | `manager4@trainer.local` | `Mgr4!pass` |

> Бывший методолог `method@trainer.local` мигрирован в ROP в апреле 2026 (PRs #46-48). Если в локальной БД остался — `make seed` пересоздаст актуальный набор.