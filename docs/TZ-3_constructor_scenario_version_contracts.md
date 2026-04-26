# ТЗ-3. Constructor, ScenarioVersion И Contract Hardening

Статус: `implementation-ready spec` (rev 2 от 2026-04-26 — синхронизирована
с rename methodologist→rop из PR #46/#47/#48 и аудитом готовности).

Приоритет: `P1 / schema safety`

Связь с программой: документ 3 из 4. Должен реализовываться поверх [TZ-1_unified_client_domain_events.md](TZ-1_unified_client_domain_events.md) и [TZ-2_runtime_integrity_guards_followup.md](TZ-2_runtime_integrity_guards_followup.md).

> **Изменения в rev 2:**
> * Все ссылки на `apps/api/app/api/methodologist.py` обновлены на
>   `apps/api/app/api/rop.py` (роль методолога retired 2026-04-26,
>   surfaces переехали под `/rop/*` с временным `/methodologist/*` alias).
> * Аналогично `apps/api/app/schemas/methodologist.py` → `schemas/rop.py`.
> * Frontend `apps/web/src/app/methodologist/scenarios/page.tsx` (deleted
>   в PR #47) → `apps/web/src/components/dashboard/MethodologyPanel.tsx`
>   sub-tab `scenarios`.
> * **Добавлено §7.3.1 (КРИТИЧНО):** auto-publish-on-update в
>   `update_scenario` обязан быть удалён в первой же фазе имплементации.
> * Добавлены конкретные таблицы полей с типами/nullability/backfill SQL
>   в §14.1.
> * Добавлено §9.2.1 — explicit stage schema (ключи, типы, required).
> * Расширено §15.1 — поведение `expected_draft_revision` mismatch.
> * Добавлено §13.5 — retention legacy `Scenario` (FK history protection).
> * Добавлено §16.4 — AST-guard для arena content (защита от drift возврата).

## 1. Цель

Сделать сценарии, конструктор и методологический слой безопасными для изменений, чтобы публикация новых сценариев не ломала runtime, старые сессии не теряли воспроизводимость, а API, frontend, ORM и вспомогательные сервисы работали по одному контракту.

Результат этого ТЗ:

- `ScenarioTemplate` становится редактируемым draft-источником;
- `ScenarioVersion` становится единственным immutable published snapshot;
- runtime всегда работает с конкретной версией сценария;
- legacy `Scenario` перестает быть вторым параллельным источником бизнес-логики;
- schema drift между API, DB, frontend, methodologist и RAG устраняется и больше не возвращается незаметно.

## 2. Подтвержденная Текущая Проблема

### 2.1 Что реально сломано

1. В системе одновременно живут `ScenarioTemplate`, `ScenarioVersion` и legacy `Scenario`, но роли этих сущностей не доведены до конца.
2. Runtime местами резолвит сценарий через `ScenarioTemplate`, а местами через auto-created legacy `Scenario`, что создает скрытый compatibility maze.
3. Публикация сценария не оформлена как строгий lifecycle с immutable published snapshot и обязательной валидацией.
4. Methodologist layer использует backward-compatible mapping, но в некоторых местах drift уже подтвержден на уровне реальных полей ORM.
5. Frontend, API и runtime живут в режиме “терпим legacy shape”, а не в режиме versioned contracts.

### 2.2 Где это видно в коде

- `apps/api/app/models/scenario.py`
- `apps/api/app/api/scenarios.py`
- `apps/api/app/api/training.py`
- `apps/api/app/api/rop.py` (бывший `methodologist.py` — переименован в PR #46)
- `apps/api/app/schemas/rop.py` (бывший `schemas/methodologist.py`)
- `apps/api/app/models/rag.py`
- `apps/web/src/components/dashboard/MethodologyPanel.tsx` — sub-tab
  `scenarios` (бывший `apps/web/src/app/methodologist/scenarios/page.tsx`,
  удалён в PR #47; placeholder ждёт TZ-3 реализации)
- `apps/web/src/app/training/page.tsx`
- `apps/web/src/lib/scenario-utils.ts`

### 2.3 Верифицированные дефекты

1. В `apps/api/app/models/scenario.py` уже есть `ScenarioVersion`, но legacy `Scenario` все еще нужен runtime для compatibility.
2. В `apps/api/app/api/training.py` при отсутствии legacy row backend автоматически создает `Scenario` из `ScenarioTemplate`, чтобы существующая логика продолжала работать.
3. В `apps/api/app/api/scenarios.py` list/get одновременно отдают и templates, и legacy scenarios, что означает двойной read model.
4. В `apps/api/app/api/rop.py` сценарии редактируются через manual field mapping и aliases, а не через жесткий typed contract.
5. **🔴 Самый опасный дефект:** в `apps/api/app/api/rop.py` функции
   `create_scenario` и `update_scenario` обе вызывают
   `_create_scenario_version(... status="published")`. Это значит **любая
   правка существующего сценария создаёт новую опубликованную версию
   мгновенно**, без валидации, без явного действия "Publish". Это
   прямое нарушение §8 invariant 2 ("`ScenarioVersion.snapshot` после
   публикации не меняется никогда" — мы создаём шум, а не защищаем
   неизменяемость). Удаление этого вызова в `update_scenario` —
   первая обязательная задача §7.3.1.
6. В `apps/api/app/api/rop.py` `create_chunk/update_chunk` работают с полями `title/content/article_reference`, тогда как `apps/api/app/models/rag.py` для `LegalKnowledgeChunk` использует `fact_text/law_article/...`. Это подтвержденный schema drift, а не теоретический риск.
7. **Pydantic schemas в `apps/api/app/schemas/rop.py` (lines 106-141)
   уже описывают неправильную форму** (`ChunkCreateRequest`,
   `ChunkResponse` содержат `title`/`content`/`article_reference`).
   Эти классы НЕ используются handlers сейчас (handlers принимают
   `data: dict`), но их existence ввёл в заблуждение — TZ-3 обязан
   удалить их и заменить на canonical shape.

### 2.4 Root Cause

Root cause в том, что сценарный домен находится в середине незавершенной миграции:

- нет жесткого разделения между editable draft и immutable published artifact;
- runtime контракт не привязан окончательно к `ScenarioVersion`;
- compatibility layer разросся и стал скрывать drift вместо того, чтобы локализовать его;
- отсутствуют contract tests между backend, frontend и runtime.

## 3. In Scope

В рамках ТЗ-3 реализуются:

- канонический lifecycle для `ScenarioTemplate` и `ScenarioVersion`;
- strict publish flow;
- immutable published versions;
- runtime resolution строго по version id;
- migration off legacy `Scenario` как active business model;
- contract hardening для API, frontend и methodologist;
- schema alignment для methodologist/RAG related APIs;
- compatibility wrapper strategy;
- contract/e2e tests;
- rollback-safe migration.

## 4. Out Of Scope

В рамках ТЗ-3 не реализуются полностью:

- клиентский домен и event-driven projections из ТЗ-1;
- runtime guard/finalizer/follow-up политика из ТЗ-2;
- attachment/knowledge/persona governance из ТЗ-4, кроме устранения прямого schema drift в methodologist/RAG contracts.

## 5. Архитектурные Решения, Которые Считаются Зафиксированными

1. `ScenarioTemplate` является editable draft model.
2. `ScenarioVersion` является immutable published artifact.
3. Любой runtime старт обязан связываться с конкретным `scenario_version_id`.
4. Legacy `Scenario` сохраняется только как compatibility bridge на время миграции.
5. Нельзя редактировать опубликованную версию сценария “на месте”.
6. Любое изменение опубликованного контента обязано создавать новую версию.

## 6. Целевая Каноническая Модель

### 6.1 ScenarioTemplate

Editable сущность для конструктора.

Обязательные поля:

- `id`
- `code`
- `name`
- `description`
- `group_name`
- `status`
- `draft_revision`
- `current_published_version_id`
- `is_active`
- `created_at`
- `updated_at`

Также включает конфигурацию сценария:

- context fields
- stages
- traps/chains
- scoring modifiers
- prompt template fields

### 6.2 ScenarioVersion

Immutable snapshot published-сценария.

Обязательные поля:

- `id`
- `template_id`
- `version_number`
- `status`
- `snapshot`
- `schema_version`
- `created_by`
- `created_at`
- `published_at`
- `validation_report`
- `content_hash`

### 6.3 Legacy Scenario

На первом этапе существует только как compatibility bridge:

- поддержка старых FK и старых read paths;
- не является основным источником для редактирования;
- не является каноническим published artifact.

## 7. Lifecycle

### 7.1 Template Status

- `draft`
- `published`
- `archived`

### 7.2 Version Status

- `published`
- `archived`
- `superseded`

### 7.3 Канонические Переходы

#### Draft Update

- меняет только `ScenarioTemplate`;
- не меняет ни одной исторической `ScenarioVersion`;
- увеличивает `draft_revision`.

#### Publish

- запускает обязательную валидацию;
- создает новый `ScenarioVersion`;
- обновляет `current_published_version_id`;
- не меняет содержимое предыдущих published versions.

#### Archive

- архивирует template для новых запусков;
- не ломает исторические сессии;
- не удаляет published versions, связанные с историей запусков.

### 7.3.1 🔴 Обязательное удаление implicit auto-publish

`apps/api/app/api/rop.py` сегодня содержит **два** вызова
`_create_scenario_version(... status="published")`:

1. в `create_scenario` (legitimate — первая версия при создании); **оставить**.
2. в `update_scenario` (defective — версия публикуется на каждом save
   без явного действия пользователя); **удалить в первой же фазе
   имплементации** (PR C2).

После удаления:

* `update_scenario` обновляет ТОЛЬКО `ScenarioTemplate` поля и
  инкрементирует `draft_revision`.
* Новая опубликованная версия создаётся ТОЛЬКО через явный
  `POST /rop/scenarios/{id}/publish` — этот эндпоинт надо ввести
  параллельно с удалением auto-publish, иначе пользователи теряют
  возможность публиковать вообще.

Любое половинчатое решение (оставить auto-publish "временно",
добавить публикацию рядом, ввести feature flag) считается
архитектурным нарушением: оно делает invariant 2 (§8.2) недостижимым.

## 8. Invariants

1. Историческая сессия всегда указывает на конкретный immutable `scenario_version_id`.
2. `ScenarioVersion.snapshot` после публикации не меняется никогда.
3. Один `template_id + version_number` уникален.
4. Runtime не должен зависеть от mutable draft-полей template при активной сессии.
5. Любой publish обязан пройти schema validation и semantic validation.
6. Любой frontend/API payload должен быть совместим с declared contract version.
7. Compatibility layer не имеет права порождать новые формы drift.

## 9. Publish Contract

### 9.1 Обязательные Этапы Публикации

1. Load current draft.
2. Validate schema.
3. Validate semantic rules.
4. Freeze snapshot.
5. Compute `content_hash`.
6. Create new `ScenarioVersion`.
7. Mark previous active published version as `superseded`, если это нужно по policy.
8. Update template pointer to new published version.

### 9.2 Semantic Validation

Минимальные правила:

- есть валидный `code`;
- есть `name` и `description`;
- есть хотя бы один stage;
- stage order непрерывный и уникальный;
- required stage fields присутствуют (см. §9.2.1);
- difficulty и duration находятся в допустимых диапазонах;
- конфигурация traps/chains не ссылается на несуществующие элементы;
- prompt-related fields не содержат несогласованных placeholders;
- scoring modifiers проходят shape validation;
- target outcome валиден для сценарного типа.

### 9.2.1 Stage Shape (обязательная схема)

`ScenarioTemplate.stages` сейчас декларирован как `JSONB default=list`
без какой-либо typed-схемы — валидатор без явной спецификации
писать невозможно. TZ-3 фиксирует следующий минимальный shape для
одного элемента списка:

| Поле | Тип | Required | Описание |
|---|---|---|---|
| `order` | int | yes | Порядковый номер 1..N, непрерывный, уникальный |
| `name` | str | yes | Краткое имя этапа (≤80 символов) |
| `description` | str | yes | Что менеджер должен сделать (≤500 символов) |
| `manager_goals` | list[str] | yes | 1..5 целей этапа |
| `client_state` | str | optional | Эмоциональное/информационное состояние клиента в начале этапа |
| `traps` | list[uuid] | optional | id трапов из `traps` таблицы; должны существовать и быть `is_active` |
| `min_duration_seconds` | int | optional | Если задано — runtime не позволит закрыть этап раньше |
| `success_criteria` | dict | optional | Структурированные критерии прохождения (для скоринга L1/L9) |

Валидатор обязан:

* Падать с детальной ошибкой (поле, индекс, причина), а не общим
  "stages invalid".
* Не "auto-fix" пропущенные required-поля — это нарушение §9.3.
* Возвращать `validation_report` со списком issues для записи в
  `ScenarioVersion.validation_report` (для аудита и для UI Publish-кнопки).

### 9.3 Запреты

Запрещено:

- редактировать `ScenarioVersion.snapshot`;
- менять исторические результаты сессий, указывающие на старую версию;
- публиковать сценарий без validation report;
- silently auto-fixить некорректный payload во время publish.

## 10. Runtime Resolution Contract

### 10.1 Правило

При старте runtime используется:

- `ScenarioTemplate.current_published_version_id`, если старт идет по template id;
- либо explicit `scenario_version_id`, если он передан напрямую.

### 10.2 Что меняется

Сейчас backend в `api/training.py` местами создает legacy `Scenario` row на лету, чтобы существующая логика сессии продолжала работать. Это допустимо только как migration adapter.

Целевое правило:

- runtime не должен нуждаться в auto-created legacy `Scenario` как в основном артефакте;
- legacy `Scenario` может быть поддерживающим bridge для старых FK, но не ядром resolution logic.

### 10.3 Канонический Артефакт Для Runtime

Канонический источник сценарного контента для runtime:

- `ScenarioVersion.snapshot`

Не:

- mutable `ScenarioTemplate`
- auto-created legacy `Scenario`

## 11. API Contract Hardening

### 11.1 ROP Scenarios API (бывший Methodologist)

Эндпоинты живут в `apps/api/app/api/rop.py` (с временным
`/methodologist/*` alias до PR B3.2). Нужно ввести versioned typed
contracts:

- `ScenarioTemplateDraftResponse`
- `ScenarioTemplateUpdateRequest`
- `ScenarioPublishRequest`
- `ScenarioVersionResponse`

Новый отдельный эндпоинт: `POST /rop/scenarios/{template_id}/publish`
(см. §7.3.1 — обязательная замена implicit auto-publish-on-update).

### 11.2 Public Scenarios API

`/scenarios` для training UI должен возвращать стабильный read model, где явно отделены:

- template identity
- published version identity
- display fields
- compatibility fields для старых клиентов

### 11.3 Contract Versioning

Если response shape materially меняется, API обязан:

- либо ввести explicit versioned endpoint;
- либо задокументировать backward-compatible additive contract;
- либо использовать versioned schema objects.

## 12. ROP / RAG Schema Alignment

Это обязательная часть ТЗ-3, потому что уже есть подтвержденный drift.

### 12.1 Что сломано

`create_chunk/update_chunk` в `apps/api/app/api/rop.py` (бывший
`methodologist.py`) используют поля:

- `title`
- `content`
- `article_reference`

Но `LegalKnowledgeChunk` в `apps/api/app/models/rag.py` использует:

- `fact_text`
- `law_article`
- `common_errors`
- `match_keywords`
- `correct_response_hint`
- и другие реальные поля ORM

### 12.2 Что нужно сделать

1. Ввести typed request/response schemas для arena content в
   `apps/api/app/schemas/rop.py`. **Существующие классы
   `ChunkCreateRequest`, `ChunkUpdateRequest`, `ChunkResponse`
   (lines 106-141) с полями `title/content/article_reference` —
   удалить целиком, не дополнять алиасами**: они описывают неправильную
   форму, handlers их не используют, любая попытка "fix by aliasing"
   маскирует drift вместо его устранения.
2. Новые schemas обязаны использовать реальные ORM имена
   (`fact_text`, `law_article`, `common_errors`, `match_keywords`,
   `correct_response_hint`, `category`, `difficulty_level`,
   `is_court_practice`, `tags`).
3. UI-friendly aliases (если нужны) допускаются ТОЛЬКО через
   documented mapping в FE (например, `apps/web/src/components/dashboard/methodology/ArenaContentEditor.tsx`
   может локально mapping'ить `title→fact_text` для UX, но запрос на
   backend идёт canonical).
4. Добавить contract tests + AST-guard (см. §16.4), которые ловят
   попытку писать несуществующие ORM attributes.

### 12.3 Правило

Нельзя больше держать “тихие” alias-слои без explicit tests и deprecation policy. Если alias нужен, он должен быть documented, tested и ограничен по сроку жизни.

## 13. Non-Breaking Migration Strategy

### Фаза 0. Inventory

- перечислить все сценарные entrypoints;
- перечислить все consumers `ScenarioTemplate`, `ScenarioVersion`, `Scenario`;
- перечислить все frontend payload shapes;
- перечислить все methodologist contracts и alias fields.

### Фаза 1. Expand And Formalize

- добавить недостающие поля `status`, `current_published_version_id`, `draft_revision`, `schema_version`, `content_hash`, `validation_report`;
- ввести typed schemas;
- ввести validation service.

### Фаза 2. Compatibility Wrappers

- старые endpoints продолжают работать;
- но внутри уже используют новый publish/runtime resolution contract;
- legacy `Scenario` живет как adapter, не как primary artifact.

### Фаза 3. Runtime Cutover

- training/runtime начинает читать сценарный контент из `ScenarioVersion.snapshot`;
- historical sessions продолжают резолвиться без потери данных;
- auto-created legacy `Scenario` перестает быть обязательной веткой.

### Фаза 4. Cleanup

- удалить мертвые alias fields;
- удалить скрытые auto-create сценарные ветки;
- закрепить contract tests и документацию.

### 13.5 Retention legacy `Scenario` (FK history protection)

**Legacy `scenarios` строки нельзя удалять, пока существует хотя бы
одна `training_sessions.scenario_id` строка, ссылающаяся на них.** Это
прямое следствие §8 invariant 1 ("Историческая сессия всегда
указывает на конкретный immutable `scenario_version_id`") в комбинации
с §3 рамок проекта (история сессий — вечная, см. CLAUDE.md и
HISTORY PRESERVATION CONTRACT в `apps/api/app/models/training.py:51-59`).

Конкретные правила:

* Фаза 4 cleanup НЕ включает `DROP TABLE scenarios` или mass DELETE.
* Legacy `Scenario` строки могут получить пометку `is_active=false`
  для скрытия из новых listings, но строка остаётся.
* `TrainingSession.scenario_id` FK сохраняется (`ON DELETE CASCADE`
  опасно — даже одна случайная удалённая legacy-строка снесёт пилотную
  историю менеджера; при необходимости сменить на `ON DELETE RESTRICT`
  отдельной миграцией).
* Если в будущем нужна полная decommission `scenarios` таблицы —
  это отдельный проект (TZ-5+) с миграцией всех historical FK на
  `scenario_version_id`.

## 14. File-Level Implementation Plan

### 14.1 Модели + миграция

Обновить:

- `apps/api/app/models/scenario.py`
- при необходимости новые schema/validator модели в отдельном модуле

Добавить **новой alembic миграцией** следующие колонки. Backfill
SQL приведён ниже — ОБЯЗАТЕЛЕН в той же миграции, иначе CI
`alembic upgrade head` упадёт на ненулевых строках.

#### `scenario_templates` (новые колонки)

| Поле | Тип | Nullable | Default | Backfill для existing rows |
|---|---|---|---|---|
| `status` | varchar(20) (CHECK in {draft, published, archived}) | NOT NULL | `'published'` | server_default — все existing считаются опубликованными |
| `draft_revision` | int | NOT NULL | `0` | server_default — никогда не редактировались как draft |
| `current_published_version_id` | uuid (FK→scenario_versions.id, ON DELETE SET NULL) | nullable | NULL | UPDATE с подзапросом: для каждого template найти последний v1 row из миграции `20260423_002_add_scenario_versions.py` (детерминированный UUID, см. её строки 69-75) |

#### `scenario_versions` (новые колонки)

| Поле | Тип | Nullable | Default | Backfill для existing rows |
|---|---|---|---|---|
| `schema_version` | int | NOT NULL | `1` | все существующие v1 rows получают `1` |
| `content_hash` | varchar(64) | nullable до 1й публикации, потом NOT NULL on commit | NULL | для existing v1 rows compute SHA256 от `snapshot::text` (deterministic, реruнnable) |
| `validation_report` | JSONB | NOT NULL | `'{"backfilled": true, "issues": []}'::jsonb` | пустой backfill report — реальный валидатор ещё не применялся к этим rows |

#### Стратегические правила миграции

* Все `ALTER TABLE ADD COLUMN` без NOT NULL до backfill, потом
  `UPDATE ...` чтобы заполнить, потом `ALTER ... SET NOT NULL`
  (Postgres-safe pattern для больших таблиц; пилот мал, но привычка).
* `content_hash` SET NOT NULL применяется ТОЛЬКО к rows со
  `status='published'`; для будущих `superseded`/`archived` остаётся
  required (валидатор compute его при публикации).
* Backfill `current_published_version_id` идёт через подзапрос —
  не "UPDATE без WHERE" (защита от race с одновременной активной
  миграцией templates).

Также добавить:

- ORM comments/docstrings о source-of-truth semantics для каждой
  новой колонки;
- CHECK constraint на `scenario_templates.status` value lattice;
- индексы: `(template_id, version_number)` UNIQUE уже есть в
  миграции `20260423_002`; добавить `(template_id, status)` для
  lookup "active published version".

### 14.2 Сервисы

Создать:

- `apps/api/app/services/scenario_validator.py`
- `apps/api/app/services/scenario_publisher.py`
- `apps/api/app/services/scenario_runtime_resolver.py`
- `apps/api/app/services/scenario_contracts.py`

### 14.3 API

Обновить:

- `apps/api/app/api/rop.py` (бывший `methodologist.py`, переименован в PR #46)
- `apps/api/app/api/scenarios.py`
- `apps/api/app/api/training.py`

Нужно:

- **удалить implicit auto-publish-on-update в `update_scenario`** (см.
  §7.3.1 — это первая обязательная задача PR C2);
- ввести новый эндпоинт `POST /rop/scenarios/{template_id}/publish`
  с request body `{ "expected_draft_revision": int }` (см. §15.1);
- перевести publish/update на typed contracts из `schemas/rop.py`;
- перевести runtime resolution на version-first approach
  (`scenario_runtime_resolver.py` — см. §14.2);
- оставить thin compatibility handlers для старых consumers
  (legacy auto-create в `training.py` остаётся как `migration adapter`
  до Фазы 3 cutover, см. §13).

### 14.4 Frontend

Проверить и обновить:

- `apps/web/src/components/dashboard/MethodologyPanel.tsx` — sub-tab
  `scenarios` (бывший `apps/web/src/app/methodologist/scenarios/page.tsx`,
  удалён в PR #47; сейчас рендерит `<PlaceholderTab>`, должен стать
  полноценным конструктором).
- `apps/web/src/app/training/page.tsx`
- `apps/web/src/lib/scenario-utils.ts`
- связанные `types` файлы (`apps/web/src/types/index.ts`,
  `apps/web/src/types/api.ts` — последний желательно регенерировать
  через `openapi-typescript` против обновлённого backend, не править руками)

Нужно:

- явно различать template и version в UI данных;
- не полагаться на неформальные fallback поля;
- корректно показывать draft/published/archive states (с Publish-кнопкой,
  validation report panel, version history list);
- поддержать publish workflow и historical version display;
- запросы идут на canonical `/rop/scenarios/*` URLs (alias
  `/methodologist/*` живёт до PR B3.2 и тогда же выпиливается).

### 14.5 ROP Arena Content

Обновить:

- `apps/api/app/api/rop.py` (бывший `methodologist.py`)
- `apps/api/app/schemas/rop.py` — **удалить классы
  `ChunkCreateRequest`, `ChunkUpdateRequest`, `ChunkResponse`
  целиком** (lines 106-141), создать новые с canonical ORM names
  (см. §12.2).
- `apps/api/app/models/rag.py` (только если нужны новые indexes/
  constraints — поля менять не надо).
- `apps/web/src/components/dashboard/methodology/ArenaContentEditor.tsx`
  (бывший `apps/web/src/app/methodologist/arena-content/page.tsx`,
  перенесён в PR #47) — переключить с legacy `title/content/category`
  payload на canonical `fact_text/law_article/...`. UI строки
  (label'ы input'ов) могут остаться "Заголовок"/"Содержание" —
  это пользовательский язык, не контракт; mapping происходит при
  сборке payload перед `api.post`.

Нужно:

- привести request/response contracts к реальной модели;
- задокументировать aliases (если нужны на FE) явно в коде;
- закрыть drift tests + AST-guard (§16.4).

## 15. Data Contract Requirements

### 15.1 Scenario Publish Request

Эндпоинт: `POST /rop/scenarios/{template_id}/publish`

Минимальная структура body:

```json
{
  "expected_draft_revision": 12
}
```

#### Поведение `expected_draft_revision`

Это **optimistic concurrency token** — защита от случая, когда два
методолога редактируют один и тот же template и оба нажимают Publish.
Backend сравнивает `expected_draft_revision` с актуальным значением
`ScenarioTemplate.draft_revision` в момент publish:

* **Match** → publish продолжается обычным путём (validate → freeze
  snapshot → create version → update pointer).
* **Mismatch** → backend отвечает `409 Conflict` с body:

  ```json
  {
    "code": "scenario_publish_conflict",
    "message": "Template was modified by another user — refresh the editor and re-publish.",
    "expected": 12,
    "actual": 14
  }
  ```

  Фронт обязан показать модал "Кто-то ещё редактировал этот сценарий —
  обновить и опубликовать заново?" и НЕ должен silently ретраить с
  новым revision (это потеряет промежуточные правки второго методолога).

Если `expected_draft_revision` опущен в request body (legacy clients
до cutover) — backend принимает с warning в логах (для observability,
§17), но дальнейшая публикация работает в режиме "доверяй последнему".
Клиенты-конструкторы в TZ-3 обязаны всегда передавать revision.

### 15.2 Scenario Version Response

Минимальная структура:

```json
{
  "id": "uuid",
  "template_id": "uuid",
  "version_number": 3,
  "status": "published",
  "schema_version": 1,
  "published_at": "timestamp",
  "snapshot": {}
}
```

### 15.3 Arena Chunk Request

Канонический shape обязан использовать реальные поля модели, а UI-friendly aliases допускаются только через documented mapping.

## 16. Тестовый Пакет

### 16.1 Unit Tests

- publish создает новую immutable version;
- update draft не меняет старую version;
- runtime resolver выбирает правильную published version;
- validator ловит некорректный stage graph;
- chunk contract validator ловит несуществующие ORM поля.

### 16.2 Contract Tests

- `/scenarios` возвращает стабильный read model;
- methodologist scenario payload roundtrip совместим с frontend;
- arena chunk API не расходится с `LegalKnowledgeChunk`;
- training session получает правильный `scenario_version_id`.

### 16.3 E2E Tests

Минимальные сценарии:

1. Создать draft -> publish -> запустить training -> historical session зафиксирована на version N.
2. Изменить draft -> publish новую версию -> новый training идет на version N+1, старый остается на N.
3. Архивировать template -> старые results и sessions доступны.
4. ROP arena chunk create/update работает без schema drift.
5. Legacy client получает совместимый response shape в transition phase.
6. **Concurrent publish race** (CLAUDE.md §4.1): два параллельных
   `POST /rop/scenarios/{id}/publish` с одинаковым
   `expected_draft_revision=N` → один получает 200, второй —
   409 conflict. Тест обязан использовать `asyncio.gather`, не
   sequential awaits.

### 16.4 AST Invariant Guards (по образцу TZ-1)

Добавить новый файл `apps/api/tests/test_scenario_invariants.py`
(в blocking CI scope, см. CLAUDE.md §1) с двумя AST-сканерами:

#### Guard 1 — запрет direct ScenarioVersion mutation после публикации

Сканирует `apps/api/app/` на:

* присваивания вида `version.snapshot = ...`, `version.content_hash = ...`,
  `version.published_at = ...` ВНЕ allow-list (`scenario_publisher.py`,
  alembic migrations).
* любой `UPDATE scenario_versions SET snapshot = ...` в SQL strings.

Падает на pre-fix code и проходит на post-fix code (см. CLAUDE.md §4.6).

#### Guard 2 — запрет writes в LegalKnowledgeChunk с несуществующими полями

По образцу `tests/test_client_domain_invariants.py`. Сканирует
`apps/api/app/api/rop.py` на конструкции:

* `LegalKnowledgeChunk(title=..., content=..., article_reference=...)`
  → fail.
* `setattr(chunk, "title", ...)` или `chunk.title = ...` → fail
  (поля `title`/`content`/`article_reference` отсутствуют в ORM).

Allow-list: только canonical имена (`fact_text`, `law_article`, и т.д.).
Этот guard — единственная durable защита от того, что drift вернётся
через будущий PR кого-то другого, кто не прочитал §12.

## 17. Observability

Нужно добавить:

- число draft updates;
- число publish attempts;
- число failed validations;
- число runtime starts без resolved version;
- число legacy fallback resolutions;
- число contract mismatches между frontend/backend schemas;
- число arena chunk payload validation failures.

## 18. Rollback И Safe Deployment

### Rollback

Если новый publish/runtime contract дает некорректный output:

- старые read paths остаются доступны через compatibility wrapper;
- published versions не откатываются “редактированием”;
- rollback делается переключением current pointer или feature flag, а не мутацией snapshot;
- runtime history сохраняется.

### Safe Deployment

Нельзя отключать legacy adapters, пока не подтверждены:

- publish parity;
- runtime resolution parity;
- frontend contract compatibility;
- historical session integrity;
- methodologist arena content compatibility.

## 19. Риски

1. Команда оставит mutable semantics у published version “ради удобства”.
2. Runtime продолжит читать одновременно template и version в разных местах.
3. Legacy `Scenario` останется не как bridge, а как скрытый основной артефакт.
4. Alias-heavy methodologist API снова замаскирует drift вместо его устранения.
5. Frontend начнет читать draft fields там, где нужен published snapshot.

## 20. Definition Of Done

ТЗ-3 считается завершенным только если:

- template/version lifecycle зафиксирован и реализован;
- publish создает immutable `ScenarioVersion`;
- runtime работает version-first;
- legacy `Scenario` перестал быть primary published model;
- typed contracts есть для methodologist и public scenarios API;
- contract drift для arena content устранен;
- есть contract tests и e2e tests;
- есть observability для publish/runtime resolution/fallbacks;
- historical sessions воспроизводимы на своих версиях.

## 21. Deliverables

- scenario validator;
- scenario publisher;
- scenario runtime resolver;
- обновленные ORM модели и миграции;
- обновленные API endpoints;
- compatibility adapters;
- frontend contract updates;
- tests;
- migration notes;
- cutover checklist.

## 22. Prompt Для Coding Agent

Используй этот документ как жесткий сценарный contract. Не лечи отдельные endpoints локальными alias-правками без введения publish lifecycle, immutable versions, runtime resolver и contract tests.

**Порядок имплементации (фазированный, по PR'ам):**

1. **PR C1 — Foundation:** alembic миграция (§14.1) + ORM поля
   `status/draft_revision/current_published_version_id` на template,
   `schema_version/content_hash/validation_report` на version. Backfill
   обязателен в той же миграции. Алembic upgrade head должен пройти на
   реальной БД (CLAUDE.md §4.3).
2. **PR C2 — Publisher + удаление auto-publish:** новые сервисы
   `scenario_validator.py`, `scenario_publisher.py`, новый эндпоинт
   `POST /rop/scenarios/{id}/publish`, **удаление вызова
   `_create_scenario_version` в `update_scenario`** (§7.3.1). Включая
   concurrent publish race test (CLAUDE.md §4.1).
3. **PR C3 — Runtime resolver:** `scenario_runtime_resolver.py`,
   training start читает snapshot из `ScenarioVersion`, legacy
   auto-create в `training.py` остаётся только как explicit migration
   adapter (§13).
4. **PR C4 — FE constructor:** `MethodologyPanel.tsx` sub-tab
   `scenarios` из `<PlaceholderTab>` в полноценный draft/publish UI
   (Publish button, validation report panel, version history list).
5. **PR C5 — Arena chunk schema fix:** удаление
   `ChunkCreateRequest/Update/Response` из `schemas/rop.py`, новые
   typed schemas с canonical ORM names, AST-guard (§16.4).

Любое место, где published content можно случайно изменить задним числом, где runtime читает mutable draft вместо version snapshot, или где API пишет поля, которых ORM не знает, считается незавершенной реализацией ТЗ.

Перед каждым `git push` — проверка `git diff origin/main..HEAD --stat`
(CLAUDE.md §1). Subagent calls — с `model="opus"` (CLAUDE.md §6).
