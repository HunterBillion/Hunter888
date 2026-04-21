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
│   ├── methodologist/      методологические инструменты
│   │   ├── scenarios       CRUD сценариев
│   │   ├── arena-content   chunks для квиза
│   │   ├── scoring         L1-L10 веса
│   │   └── sessions        browse всех сессий
│   ├── admin/              системная админка
│   │   └── audit-log       152-ФЗ compliance
│   ├── results/[id]        пост-матч разбор
│   ├── stories/[storyId]   deep-dive сессии
│   ├── wiki                Manager Wiki (автогенерируется)
│   ├── profile, settings, notifications, pricing
│
├── 🔧 Бэкенд (apps/api) — FastAPI + SQLAlchemy 2 async
│   ├── app/main.py         ← entry, 348+ routes зарегистрировано
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
│   ├── app/models/         SQLAlchemy models (40+ таблиц)
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
│   └── alembic/versions/   миграции БД (20260420_005 на head)
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
| **rop** | Центр · **Команда** · Тренировка · Арена · Лидерборд · Клиенты · История |
| **methodologist** | Центр · Сценарии · Контент Арены · Скоринг · Сессии · Wiki |
| **admin** | Центр · Команда · Тренировка · Арена · Лидерборд · Клиенты · **Админка** · **Аудит** |

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

### 4. Методолог ведёт контент

```
/methodologist → hub с 4 карточками
                     ↓
     Сценарии     Контент Арены     Скоринг      Сессии
     CRUD          chunks            L1-L10       browse всех
                                                  ↓
                                          Можно ревьюить любую сессию юзера
```

### 5. Admin проверяет 152-ФЗ compliance

```
/admin → hub всех admin-surfaces
            ↓
   Аудит    Health    Промпты    + все surfaces методолога
   (живой) (скоро)    (скоро)
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
| Новый WS event | `apps/api/app/ws/{training,pvp,knowledge}.py` — receive loop + emit |
| Добавить scheduler job | `apps/api/app/services/scheduler.py` → новый `_check_*` метод |
| Миграция БД | `apps/api/alembic/versions/` + update модель в `app/models/` |

---

## 📋 Journal изменений (recent)

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

- [docs/FRONTEND_TZ_v2.md](docs/FRONTEND_TZ_v2.md) — фронтенд ТЗ
- [docs/clients_domain_architecture.md](docs/clients_domain_architecture.md) — домен «Клиенты»
- [docs/roleplay_system_v2.md](docs/roleplay_system_v2.md) — роль-плей система v2
- [docs/anti_cheat_v2.md](docs/anti_cheat_v2.md) — anti-cheat
- [docs/architecture_audit_2026-04-09.md](docs/architecture_audit_2026-04-09.md) — исторический аудит

---

## 🎯 Product invariants (не нарушать)

1. **История = навсегда** (см. выше)
2. **Навигация = функция(role)** — один источник правды
3. **Elevated роли (admin/rop/methodologist) → master** — автоматически, не показываем PlanChip
4. **История ≠ подписка** — никаких gate-фильтров на `/history`
5. **Все 5 Arena режимов используют unified компоненты** (CountdownOverlay / CoachingCard / sfx / theme accent)
6. **WS heartbeat** на всех live endpoints — idle-kill 120s
7. **Unified 429 body** — `{feature, plan, limit, used, message}` для всех plan-limit проверок
8. **Lifelines + Power-ups квоты в Redis** с fail-open — никогда не блокирует геймплей при сбое Redis

---

## 🚦 Production readiness

| Слой | Статус |
|---|---|
| Alembic heads = current | ✅ `20260420_005 (head)` |
| TS compile | ✅ 0 ошибок |
| CSRF middleware | ✅ double-submit cookie |
| Rate limits | ✅ все mutation endpoints + LLM-калории (lifelines hint — 10/min) |
| WS idle-kill | ✅ все 3 endpoint (training / pvp / knowledge) |
| 429 upsell UX | ✅ PlanLimitModal global |
| Role-aware nav | ✅ 4 персоны |
| History preservation | ✅ контракт задокументирован |
| Auto-refresh tokens | ✅ mutex-guarded, circuit breaker |
| Fetch timeout | ✅ 30s default + forward user signal |

---

## 🤝 Вклад / доступ

Pilot-продукт для ~50 активных менеджеров/день. Доступ — только по приглашению.

Для разработчиков: перед PR — `make lint && make test && alembic upgrade head` должны пройти.


Роль	Email	Пароль
Админ	admin@trainer.local	Adm1n!2024
РОП команды Sales	rop1@trainer.local	Rop1!pass
РОП команды B2B	rop2@trainer.local	Rop2!pass
Методолог (Анна)	method@trainer.local	Method!1
Менеджер Иван Петров (Sales)	manager1@trainer.local	Mgr1!pass
Менеджер Мария Сидорова (Sales)	manager2@trainer.local	Mgr2!pass
Менеджер Дмитрий Козлов (B2B)	manager3@trainer.local	Mgr3!pass
Менеджер Ксения Морозова (B2B)	manager4@trainer.local	Mgr4!pass