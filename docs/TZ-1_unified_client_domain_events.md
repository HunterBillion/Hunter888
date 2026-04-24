# ТЗ-1. Единый Клиентский Домен, События И CRM Timeline

Статус: `implementation-ready spec`

Приоритет: `P0 / foundation`

Связь с программой: документ 1 из 4. Все следующие ТЗ обязаны опираться на термины, инварианты и миграционные решения из этого документа.

## 1. Цель

Собрать платформу вокруг одного канонического клиентского домена, чтобы `CRM`, `chat`, `call`, `training`, `center`, `attachments` и аналитика перестали хранить одну и ту же историю в нескольких конкурирующих моделях.

Результат этого ТЗ:

- у любого реального кейса есть один канонический идентификатор `lead_client_id`;
- все значимые действия пишутся как `DomainEvent`;
- `CRM timeline` строится как проекция из событий, а не как набор ручных вставок из разных роутов и websocket-хендлеров;
- текущие модели `RealClient`, `ClientStory`, `GameClientEvent`, `TrainingSession` перестают быть независимыми источниками правды.

## 2. Почему Это Нужно Делать Сейчас

По текущему коду уже видно, что платформа частично чинит проблему, но чинит ее локально:

- профиль-гейт уже есть в `apps/api/app/services/profile_gate.py` и вызывается из `apps/api/app/api/training.py`;
- режим сессии уже нормализуется через `apps/api/app/services/session_state.py`;
- `ScenarioVersion` уже существует в `apps/api/app/models/scenario.py`;
- `Attachment` уже получил статусы OCR/classification в `apps/api/app/models/client.py`;
- knowledge governance уже начат в `apps/api/app/models/rag.py` и `apps/api/app/services/knowledge_governance.py`.

Но корневая проблема не устранена:

- `RealClient` в `apps/api/app/models/client.py` живет отдельно от `ClientStory` в `apps/api/app/models/roleplay.py`;
- `GameClientEvent` в `apps/api/app/models/game_crm.py` хранит отдельную событийную историю;
- `TrainingSession` в `apps/api/app/models/training.py` связывает CRM и runtime только частично через `real_client_id`;
- timeline в CRM создается из нескольких разных мест, включая `apps/api/app/api/training.py`, `apps/api/app/api/clients.py` и `apps/api/app/ws/training.py`.

Итог: система уже содержит правильные фрагменты, но пока не содержит одного домена.

## 3. Подтвержденная Текущая Проблема

### 3.1 Что на самом деле сломано

1. Один клиент представлен несколькими сущностями и статусами.
2. История взаимодействия пишется несколькими путями с разными payload-контрактами.
3. `CRM timeline` зависит от транспортного пути завершения сессии, а не от единого терминального события.
4. `ClientStory` и `game_crm` моделируют ту же реальность, что и CRM, но по своим правилам.
5. Невозможно надежно гарантировать, что изменение в одной части платформы не поломает другую, потому что нет общего контракта доменных событий и проекций.

### 3.2 Где это видно в коде

- `apps/api/app/models/client.py`
- `apps/api/app/models/game_crm.py`
- `apps/api/app/models/roleplay.py`
- `apps/api/app/models/training.py`
- `apps/api/app/api/training.py`
- `apps/api/app/ws/training.py`
- `apps/api/app/services/event_bus.py`
- `apps/api/app/services/game_crm_service.py`
- `apps/api/app/services/timeline_aggregator.py`

### 3.3 Root Cause

Root cause не в отсутствии отдельных фич. Root cause в том, что:

- доменная модель клиента не канонизирована;
- state и event semantics дублируются между CRM, training и AI continuity;
- проекции строятся вручную из побочных эффектов, а не из одного потока доменных событий;
- текущий `event_bus` полезен, но это не канонический клиентский event bus, а общий механизм приложения с несколькими обработчиками.

## 4. In Scope

В рамках ТЗ-1 реализуются:

- канонический `LeadClient`;
- канонический `DomainEvent` для клиентского домена;
- единый `lead_client_id` как обязательная связь между модулями;
- единый `status lattice` для клиентского домена;
- `CRM timeline projection`;
- `projection parity` и `dual-write migration`;
- карта миграции от `RealClient`, `ClientStory`, `GameClientEvent` и текущих interaction inserts;
- `audit trail`, `idempotency`, `repair jobs`, `rollback strategy`;
- file-level implementation plan;
- тестовый пакет и observability.

## 5. Out Of Scope

В рамках ТЗ-1 не реализуются полностью:

- runtime-guards `chat/call/training/center`;
- terminal outcome flow и follow-up orchestration;
- полноценный `Attachment pipeline`;
- `KnowledgeItem TTL`, SLA review и policy engine;
- финальная переработка конструктора сценариев.

Эти задачи будут специфицированы в ТЗ-2, ТЗ-3 и ТЗ-4. Но ТЗ-1 обязано заложить для них правильную платформенную основу.

## 6. Архитектурные Решения, Которые Считаются Зафиксированными

1. `ClientStory` не удаляется на первом этапе, а переводится в роль `projection`.
2. Источник правды для клиентского пути не `ClientStory`, а канонический клиентский домен.
3. `Center` остается отдельным режимом, но его runtime-поведение будет описано в ТЗ-2.
4. `Training` делится на `simulation` и `real_case`; только `real_case` имеет право писать в реальный клиентский timeline.
5. Любая критичная миграция проводится через `expand -> dual-write -> backfill -> cutover -> contract cleanup`.

## 7. Целевая Каноническая Модель

### 7.1 Агрегаты

#### LeadClient

Канонический бизнес-агрегат клиента/кейса.

Обязательные поля:

- `id`
- `owner_user_id`
- `team_id`
- `profile_id`
- `crm_card_id`
- `lifecycle_stage`
- `work_state`
- `status_tags`
- `created_at`
- `updated_at`
- `archived_at`
- `source_system`
- `source_ref`

#### Profile

Профиль для персонализации и guard-логики.

Обязательные поля:

- `id`
- `lead_client_id`
- `full_name`
- `gender`
- `role_title`
- `lead_source`
- `primary_contact`
- `consents`
- `completeness_status`
- `last_confirmed_at`

#### CRMCard

Рабочая CRM-проекция поверх `LeadClient`.

Обязательные поля:

- `id`
- `lead_client_id`
- `owner_user_id`
- `priority`
- `next_action_at`
- `last_contact_at`
- `lost_reason`
- `pause_reason`
- `source_channel`

#### DomainEvent

Единственный канонический журнал клиентских действий.

Обязательные поля:

- `id`
- `lead_client_id`
- `event_type`
- `aggregate_type`
- `aggregate_id`
- `session_id`
- `call_attempt_id`
- `actor_type`
- `actor_id`
- `source`
- `occurred_at`
- `payload_json`
- `idempotency_key`
- `schema_version`
- `causation_id`
- `correlation_id`

### 7.2 Проекции

Только как производные сущности:

- `CRM timeline`
- `ClientStory`
- `training report timeline fragment`
- `analytics transition ledger`
- `task suggestions / next best action`

Принцип: производная сущность может быть пересобрана из `DomainEvent`.

## 8. Каноническая Решетка Состояний

### 8.1 Lifecycle Stage

- `new`
- `contacted`
- `interested`
- `consultation`
- `thinking`
- `consent_received`
- `contract_signed`
- `documents_in_progress`
- `case_in_progress`
- `completed`
- `lost`

### 8.2 Work State

- `active`
- `callback_scheduled`
- `waiting_client`
- `waiting_documents`
- `consent_pending`
- `paused`
- `consent_revoked`
- `duplicate_review`
- `archived`

### 8.3 Status Tags

Теги не управляют state machine.

Примеры:

- `vip`
- `high_risk`
- `needs_legal_review`
- `escalated`
- `hot_lead`
- `repeat_contact`

### 8.4 Правило

`status` и `tags` нельзя смешивать. Любое поле, которое влияет на переходы, SLA, обязательность follow-up или routing, обязано быть либо `lifecycle_stage`, либо `work_state`, но не тегом.

## 9. Domain Event Catalog

Минимальный стартовый каталог для ТЗ-1:

- `lead_client.created`
- `lead_client.profile_updated`
- `lead_client.lifecycle_changed`
- `lead_client.work_state_changed`
- `lead_client.tag_added`
- `lead_client.tag_removed`
- `crm.interaction_logged`
- `crm.reminder_created`
- `session.linked_to_client`
- `session.attachment_linked`
- `training.real_case_logged`
- `call.outcome_logged`
- `center.outcome_logged`
- `consent.updated`
- `persona.snapshot_captured`

### 9.1 Общие правила для событий

1. Событие описывает факт, а не команду.
2. Событие неизменяемо после записи.
3. Все consumers читают событие по `schema_version`.
4. Любой producer обязан выставлять `idempotency_key`.
5. Любая проекция обязана быть re-playable.

## 10. CRM Timeline Как Projection

### 10.1 Что меняется

Сейчас `ClientInteraction` создается напрямую из нескольких мест приложения. Это остается допустимо только как временный compatibility-layer.

Целевое правило:

`business action -> DomainEvent -> CRM Timeline Projector -> ClientInteraction`

### 10.2 Канонический Mapping

#### Для `crm.interaction_logged`

- `ClientInteraction.client_id = lead_client_id` через совместимость с `RealClient`
- `ClientInteraction.type` вычисляется из `event_type` и `payload`
- `ClientInteraction.content` заполняется только из нормализованного timeline payload
- `ClientInteraction.metadata.domain_event_id` обязателен
- `ClientInteraction.metadata.schema_version` обязателен

#### Для `session.attachment_linked`

Обязательные `metadata`:

- `domain_event_id`
- `attachment_id`
- `session_id`
- `message_id`
- `source`

#### Для `training.real_case_logged`

Обязательные `metadata`:

- `domain_event_id`
- `training_session_id`
- `session_mode`
- `scenario_id`
- `scenario_version_id`
- `score_total`
- `outcome`

### 10.3 Запрет

Нельзя добавлять новую запись в `ClientInteraction` из произвольного роута без параллельного `DomainEvent`. Любой новый interaction write без event-write считается архитектурным дефектом.

## 11. Совместимость С Текущими Моделями

### 11.1 RealClient

На первом этапе `RealClient` сохраняется как physical table и operational compatibility model.

Но:

- `RealClient.id` становится текущим physical anchor для `lead_client_id migration`;
- новые cross-module связи должны проектироваться на будущий канонический `lead_client_id`;
- новые фичи не имеют права вводить еще один параллельный client aggregate.

### 11.2 ClientStory

`ClientStory` сохраняется, но считается только AI/continuity projection.

Запрещено:

- принимать `ClientStory.lifecycle_state` как источник правды для CRM;
- строить новые cross-module workflow напрямую на `ClientStory`;
- плодить отдельные state transitions вне канонического client domain.

### 11.3 GameClientEvent

`GameClientEvent` сохраняется только как специализированный event log continuity-слоя до завершения миграции.

Все новые глобально значимые клиентские события обязаны писаться в `DomainEvent`, даже если параллельно продолжается запись в `GameClientEvent`.

## 12. Anti-Break Migration Strategy

Это обязательная часть ТЗ. Цель не просто внедрить новый домен, а внедрить его без разрушения платформы.

### Фаза 0. Inventory And Freeze Rules

- зафиксировать current producers `ClientInteraction`;
- зафиксировать current producers `GameClientEvent`;
- описать все текущие места, где создается или меняется client lifecycle;
- запретить новые write-paths в client history без обновления этого spec.

### Фаза 1. Expand Schema

Добавить:

- таблицу `lead_clients`
- таблицу `domain_events`
- таблицу `crm_timeline_projection_state`
- nullable связи к `lead_client_id` в существующих сущностях, где это нужно

На этой фазе ни один старый путь не удаляется.

### Фаза 2. Dual-Write Producers

Обновить текущие producer-пути так, чтобы они:

- продолжали писать в старые таблицы;
- параллельно писали в `DomainEvent`;
- использовали единый `idempotency_key`.

Dual-write обязателен для:

- `apps/api/app/api/clients.py`
- `apps/api/app/api/training.py`
- `apps/api/app/ws/training.py`
- `apps/api/app/services/game_crm_service.py`

### Фаза 3. Build Projections

Реализовать projector для:

- `CRM timeline`
- `ClientStory projection bridge`
- `transition analytics`

На этом этапе timeline из старых прямых writes и timeline из projector должны быть сопоставимы по количеству и содержанию.

### Фаза 4. Backfill

Написать backfill job, который:

- связывает существующие `RealClient` с `LeadClient`;
- переносит исторические interaction records в `DomainEvent`;
- строит missing projection records;
- помечает неразрешимые конфликты как `repair_required`.

### Фаза 5. Cutover

После прохождения parity-check:

- новый `CRM timeline` считается каноническим;
- новые interaction rows создаются только projector-ом;
- прямые interaction writes остаются только как compatibility wrapper, который внутри все равно пишет `DomainEvent`.

### Фаза 6. Cleanup

- удалить мертвые прямые вставки;
- удалить неиспользуемые metadata-форматы;
- зафиксировать contract tests;
- обновить документацию и ADR.

## 13. Инварианты

1. У каждого реального рабочего кейса есть один и только один `lead_client_id`.
2. Ни один модуль не может быть единственным владельцем истории клиента, кроме канонического event log.
3. Любое событие, влияющее на CRM, training, center, follow-up или analytics, обязано существовать в `DomainEvent`.
4. Любая timeline-проекция обязана содержать `domain_event_id`.
5. Любая повторная обработка события не должна создавать дубль.
6. `ClientStory` и другие производные модели должны быть восстановимы из `DomainEvent` или bridge-проекций.
7. При rollback старые operational path'ы продолжают работать без потери данных.

## 14. File-Level Implementation Plan

### 14.1 Новые сущности и миграции

Создать или обновить:

- `apps/api/app/models/lead_client.py`
- `apps/api/app/models/domain_event.py`
- `apps/api/app/models/crm_projection.py`
- миграции Alembic для новых таблиц и индексов

Если команда предпочитает не создавать отдельный `lead_client.py`, допускается размещение `LeadClient` в `models/client.py`, но тогда `DomainEvent` должен оставаться отдельным модулем.

### 14.2 Обновить текущие модели

- `apps/api/app/models/client.py`
- `apps/api/app/models/training.py`
- `apps/api/app/models/roleplay.py`
- `apps/api/app/models/game_crm.py`

Необходимые изменения:

- nullable/required references к `lead_client_id`;
- нормализация status fields;
- compatibility fields и bridge relations;
- комментарии на уровне ORM о source-of-truth semantics.

### 14.3 Producers

Обновить write-paths:

- `apps/api/app/api/clients.py`
- `apps/api/app/api/training.py`
- `apps/api/app/ws/training.py`
- `apps/api/app/services/game_crm_service.py`
- `apps/api/app/services/client_service.py`

Каждый путь должен:

- выделять нормализованный event payload;
- создавать `DomainEvent` в той же транзакции, где пишется бизнес-данные;
- прокидывать `correlation_id` и `idempotency_key`;
- логировать `lead_client_id`.

### 14.4 Projection Layer

Создать:

- `apps/api/app/services/domain_event_projector.py`
- `apps/api/app/services/crm_timeline_projector.py`
- `apps/api/app/services/client_story_projector.py`

Допускается объединить первые два сервиса на старте, если разделение дает лишнюю сложность, но `ClientStory` projector должен оставаться отдельным.

### 14.5 Event Bus Integration

Обновить:

- `apps/api/app/services/event_bus.py`

Задача не заменить весь существующий bus, а:

- добавить отдельный channel/namespace для client domain events;
- гарантировать outbox semantics;
- не смешивать achievements/gamification handlers с каноническими клиентскими проекциями;
- обеспечить reprocessing tooling.

### 14.6 API/Schema Layer

Проверить и обновить:

- `apps/api/app/schemas/client.py`
- `apps/api/app/schemas/training.py`
- `apps/web/src/types/index.ts`
- `apps/web/src/types/api.ts`

Нужно:

- добавить `lead_client_id`;
- добавить projection metadata;
- не ломать старые response shape до завершения cutover;
- ввести versioned response contracts там, где shape меняется materially.

## 15. Data Contract Requirements

### 15.1 DomainEvent Payload Contract

Минимальная структура:

```json
{
  "schema_version": 1,
  "event_type": "crm.interaction_logged",
  "lead_client_id": "uuid",
  "session_id": "uuid-or-null",
  "actor": {
    "type": "user|system|ai|client"
  },
  "payload": {},
  "source": "api|ws|job|migration"
}
```

### 15.2 Projection Metadata Contract

Минимальная структура:

```json
{
  "domain_event_id": "uuid",
  "schema_version": 1,
  "projection_version": 1,
  "source": "crm_timeline_projector"
}
```

## 16. Тестовый Пакет

### 16.1 Unit Tests

- `idempotency_key` не допускает дубль события;
- projector корректно маппит event в `ClientInteraction`;
- `ClientStory` bridge получает событие и не создает конфликтный lifecycle;
- lifecycle/work_state transitions валидируются against lattice;
- backfill корректно распознает already-migrated records.

### 16.2 Contract Tests

- API response не теряет старые поля во время dual-write;
- frontend типы совместимы с новыми nullable/non-nullable полями;
- `training real_case -> DomainEvent -> CRM timeline` дает одинаковый output через REST и WS path;
- `ClientInteraction.metadata` всегда содержит `domain_event_id`.

### 16.3 E2E Tests

Минимальные сценарии:

1. Создание клиента -> изменение статуса -> запись interaction -> timeline projection.
2. `training real_case` с привязанным клиентом -> событие -> timeline.
3. Загрузка attachment -> event -> timeline link.
4. Переигровка projector-а на исторических событиях -> idempotent rebuild.
5. Rollback path: отключенный projector не приводит к потере старой operational записи.

## 17. Observability

Нужно добавить:

- dashboard количества `DomainEvent` по типам;
- алерт на `projection lag`;
- алерт на `dead-letter` или `repair_required`;
- алерт на mismatch между direct writes и projected writes в dual-write фазе;
- метрику `timeline parity ratio`;
- метрику `events without lead_client_id`;
- structured logs с `lead_client_id`, `domain_event_id`, `correlation_id`.

## 18. Rollback И Repair Strategy

### Rollback

Если новый projector дает некорректный output:

- operational writes в старые таблицы не отключаются до подтвержденного parity;
- feature flag выключает read path на новые projections;
- `DomainEvent` продолжает записываться, чтобы не потерять историю;
- после фикса projector выполняется replay.

### Repair

Нужен отдельный repair job:

- находит события без projection;
- находит projection без `domain_event_id`;
- находит конфликтный `lead_client_id mapping`;
- пересобирает projection по диапазону времени или `correlation_id`.

## 19. Риски

1. Команда попытается “срезать угол” и заменить только часть producers, оставив hidden writes.
2. Команда начнет использовать `DomainEvent` как новый мусорный JSON-лог без жесткого каталога событий.
3. Cutover будет сделан раньше, чем появится parity-check.
4. `ClientStory` продолжит неявно использоваться как источник правды.
5. Frontend начнет читать новую проекцию раньше, чем стабилизируется metadata-контракт.

## 20. Definition Of Done

ТЗ-1 считается завершенным только если выполнено все ниже:

- существует канонический `LeadClient`;
- существует таблица `DomainEvent`;
- ключевые producer-paths пишут `DomainEvent` в той же транзакции;
- `CRM timeline` строится через projector;
- `ClientInteraction.metadata.domain_event_id` заполняется всегда;
- проведен backfill и зафиксирован parity-report;
- есть contract tests и e2e tests;
- есть feature flags для cutover/rollback;
- есть observability по lag, parity и repair;
- `ClientStory` переведен в projection semantics хотя бы на уровне контрактов и write rules.

## 21. Deliverables

- код моделей и миграций;
- projector services;
- dual-write producer updates;
- backfill job;
- repair job;
- dashboards и alerts;
- ADR по каноническому клиентскому домену;
- отчет parity перед cutover;
- обновленная документация по API/metadata contracts.

## 22. Prompt Для Coding Agent

Используй этот документ как обязательный implementation contract. Не делай локальную точечную починку без учета dual-write, projection parity, rollback и совместимости с существующими моделями `RealClient`, `ClientStory`, `GameClientEvent`, `TrainingSession`.

Сначала реализуй schema expand и `DomainEvent`/`LeadClient`, затем dual-write producers, затем projector и только после этого backfill и cutover. Любое изменение, которое пишет в timeline или меняет клиентский lifecycle в обход `DomainEvent`, считается нарушением ТЗ, даже если тесты локально проходят.

Обязательно добавь contract tests, replay/idempotency tests, parity instrumentation и feature flags на чтение новых projections. Если в каком-то месте невозможно безопасно перевести write-path за один шаг, оставь compatibility wrapper, но не оставляй новый код без записи канонического события.
