# ТЗ-3. Constructor, ScenarioVersion И Contract Hardening

Статус: `implementation-ready spec`

Приоритет: `P1 / schema safety`

Связь с программой: документ 3 из 4. Должен реализовываться поверх [TZ-1_unified_client_domain_events.md](/Users/bubble3/Desktop/Проекты_Х/wr1/Hunter888-main/docs/TZ-1_unified_client_domain_events.md) и [TZ-2_runtime_integrity_guards_followup.md](/Users/bubble3/Desktop/Проекты_Х/wr1/Hunter888-main/docs/TZ-2_runtime_integrity_guards_followup.md).

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
- `apps/api/app/api/methodologist.py`
- `apps/api/app/models/rag.py`
- `apps/web/src/app/methodologist/scenarios/page.tsx`
- `apps/web/src/app/training/page.tsx`
- `apps/web/src/lib/scenario-utils.ts`

### 2.3 Верифицированные дефекты

1. В `apps/api/app/models/scenario.py` уже есть `ScenarioVersion`, но legacy `Scenario` все еще нужен runtime для compatibility.
2. В `apps/api/app/api/training.py` при отсутствии legacy row backend автоматически создает `Scenario` из `ScenarioTemplate`, чтобы существующая логика продолжала работать.
3. В `apps/api/app/api/scenarios.py` list/get одновременно отдают и templates, и legacy scenarios, что означает двойной read model.
4. В `apps/api/app/api/methodologist.py` сценарии редактируются через manual field mapping и aliases, а не через жесткий typed contract.
5. В `apps/api/app/api/methodologist.py` `create_chunk/update_chunk` работают с полями `title/content/article_reference`, тогда как `apps/api/app/models/rag.py` для `LegalKnowledgeChunk` использует `fact_text/law_article/...`. Это подтвержденный schema drift, а не теоретический риск.

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
- required stage fields присутствуют;
- difficulty и duration находятся в допустимых диапазонах;
- конфигурация traps/chains не ссылается на несуществующие элементы;
- prompt-related fields не содержат несогласованных placeholders;
- scoring modifiers проходят shape validation;
- target outcome валиден для сценарного типа.

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

### 11.1 Methodologist Scenarios API

Нужно ввести versioned typed contracts:

- `ScenarioTemplateDraftResponse`
- `ScenarioTemplateUpdateRequest`
- `ScenarioPublishRequest`
- `ScenarioVersionResponse`

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

## 12. Methodologist / RAG Schema Alignment

Это обязательная часть ТЗ-3, потому что уже есть подтвержденный drift.

### 12.1 Что сломано

`create_chunk/update_chunk` в `apps/api/app/api/methodologist.py` используют поля:

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

1. Ввести typed request/response schemas для methodologist arena content.
2. Явно задокументировать alias mapping только как transition layer.
3. Нормализовать backend к реальным ORM полям.
4. Добавить contract tests, которые ловят попытку писать несуществующие ORM attributes.

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

## 14. File-Level Implementation Plan

### 14.1 Модели

Обновить:

- `apps/api/app/models/scenario.py`
- при необходимости новые schema/validator модели в отдельном модуле

Добавить:

- status fields для template;
- publish pointer на current version;
- schema/content metadata для version;
- ORM comments/docstrings о source-of-truth semantics.

### 14.2 Сервисы

Создать:

- `apps/api/app/services/scenario_validator.py`
- `apps/api/app/services/scenario_publisher.py`
- `apps/api/app/services/scenario_runtime_resolver.py`
- `apps/api/app/services/scenario_contracts.py`

### 14.3 API

Обновить:

- `apps/api/app/api/methodologist.py`
- `apps/api/app/api/scenarios.py`
- `apps/api/app/api/training.py`

Нужно:

- убрать implicit publish semantics;
- перевести publish/update на typed contracts;
- перевести runtime resolution на version-first approach;
- оставить thin compatibility handlers для старых consumers.

### 14.4 Frontend

Проверить и обновить:

- `apps/web/src/app/methodologist/scenarios/page.tsx`
- `apps/web/src/app/training/page.tsx`
- `apps/web/src/lib/scenario-utils.ts`
- связанные `types` файлы

Нужно:

- явно различать template и version в UI данных;
- не полагаться на неформальные fallback поля;
- корректно показывать draft/published/archive states;
- поддержать publish workflow и historical version display.

### 14.5 Methodologist Arena Content

Обновить:

- `apps/api/app/api/methodologist.py`
- `apps/api/app/models/rag.py`
- frontend arena-content screens, если они используют legacy chunk shape

Нужно:

- привести request/response contracts к реальной модели;
- задокументировать aliases;
- закрыть drift tests.

## 15. Data Contract Requirements

### 15.1 Scenario Publish Request

Минимальная структура:

```json
{
  "template_id": "uuid",
  "expected_draft_revision": 12
}
```

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
4. Methodologist arena chunk create/update работает без schema drift.
5. Legacy client получает совместимый response shape в transition phase.

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

Сначала формализуй lifecycle `ScenarioTemplate` и `ScenarioVersion`, затем внедри validator и publisher, затем переведи runtime на version-first resolution, затем убери скрытую зависимость от auto-created legacy `Scenario`. Любое место, где published content можно случайно изменить задним числом, где runtime читает mutable draft вместо version snapshot, или где API пишет поля, которых ORM не знает, считается незавершенной реализацией ТЗ.
