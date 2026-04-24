# ТЗ-4. Attachment, Knowledge Governance И Persona Policy

Статус: `implementation-ready spec`

Приоритет: `P1 / trust layer`

Связь с программой: документ 4 из 4. Должен реализовываться поверх [TZ-1_unified_client_domain_events.md](/Users/bubble3/Desktop/Проекты_Х/wr1/Hunter888-main/docs/TZ-1_unified_client_domain_events.md), [TZ-2_runtime_integrity_guards_followup.md](/Users/bubble3/Desktop/Проекты_Х/wr1/Hunter888-main/docs/TZ-2_runtime_integrity_guards_followup.md) и [TZ-3_constructor_scenario_version_contracts.md](/Users/bubble3/Desktop/Проекты_Х/wr1/Hunter888-main/docs/TZ-3_constructor_scenario_version_contracts.md).

## 1. Цель

Сделать документы, знания и persona-память полноценным доверенным слоем платформы, чтобы система не теряла вложения между режимами, не использовала устаревшие знания в рекомендациях и не путала личность/контекст клиента в рамках одной сессии и между сессиями.

Результат этого ТЗ:

- вложения работают как канонический домен с pipeline, дедупликацией и связью с событием;
- knowledge layer получает управляемый lifecycle с review/TTL/status policy;
- persona становится не набором prompt-хаков, а нормализованной session/client memory policy;
- CRM, runtime и AI начинают использовать одни и те же документы, статусы знаний и persona snapshots.

## 2. Подтвержденная Текущая Проблема

### 2.1 Что реально сломано

1. Attachment-домен уже есть, но пока это в основном storage + link, а не полноценный pipeline обработки и верификации.
2. Knowledge governance уже различает `actual/disputed/outdated/needs_review`, но это пока фильтрация источников, а не полный lifecycle знаний.
3. Persona consistency уже частично удерживается через `persona_snapshot` и conversation policy prompt, но это еще не канонический memory layer.
4. Система уже умеет нечто из этого делать, но каждая часть реализована локально и не сведена в один trust contract.

### 2.2 Где это видно в коде

- `apps/api/app/models/client.py`
- `apps/api/app/api/clients.py`
- `apps/api/app/api/training.py`
- `apps/api/app/services/attachment_storage.py`
- `apps/api/app/services/knowledge_governance.py`
- `apps/api/app/services/rag_legal.py`
- `apps/api/app/services/rag_legal_v2.py`
- `apps/api/app/services/conversation_policy.py`
- `apps/api/app/services/next_best_action.py`
- `apps/web/src/components/clients/ClientAttachments.tsx`
- `apps/web/src/components/clients/ClientTimeline.tsx`
- `apps/web/src/components/training/SessionAttachmentButton.tsx`

### 2.3 Верифицированные факты

1. В `apps/api/app/models/client.py` `Attachment` уже содержит `client_id`, `session_id`, `message_id`, `interaction_id`, `sha256`, `status`, `ocr_status`, `classification_status`.
2. В `apps/api/app/api/training.py` upload attachment в сессию уже связывает файл с CRM клиентом и создает `ClientInteraction`.
3. В `apps/api/app/services/next_best_action.py` pending attachments уже влияют на `next best action`, но только по простым status-checks.
4. В `apps/api/app/services/knowledge_governance.py` уже есть базовые статусы знаний и правило “outdated нельзя использовать для рекомендаций”.
5. В `apps/api/app/services/conversation_policy.py` уже есть anti-repeat, краткость и правило “не менять имя/пол/роль без явного обновления”.
6. В `apps/api/app/api/training.py` уже сохраняется `persona_snapshot` в `custom_params` при старте на реальном клиенте.

### 2.4 Root Cause

Root cause в том, что trust layer пока не выделен как самостоятельный домен:

- attachment lifecycle не завершен;
- knowledge source governance не доведено до reviewable model;
- persona memory не отделена от prompt assembly;
- разные части платформы используют эти данные по локальным правилам, а не по единому контракту.

## 3. In Scope

В рамках ТЗ-4 реализуются:

- канонический attachment domain и processing pipeline;
- linkage attachments к `lead_client_id`, `session_id`, `message_id`, `domain_event_id` и при необходимости `call_attempt_id`;
- knowledge item governance с TTL/review/status policy;
- persona memory model и session snapshot rules;
- conversation policy engine как сервис, а не только prompt fragment;
- anti-repeat and next-step policy;
- trust-layer observability, tests и rollback strategy.

## 4. Out Of Scope

В рамках ТЗ-4 не реализуются полностью:

- базовый клиентский event domain из ТЗ-1;
- базовый runtime finalizer из ТЗ-2;
- lifecycle publish/versioning сценариев из ТЗ-3.

Но ТЗ-4 должно использовать эти основы и не создавать свои параллельные домены.

## 5. Архитектурные Решения, Которые Считаются Зафиксированными

1. Attachment является канонической бизнес-сущностью, а не просто файлом в storage.
2. Любое вложение должно быть связано с клиентом и доменным событием, если это возможно технически.
3. Knowledge item с `outdated` не участвует в рекомендациях.
4. `disputed` и `needs_review` могут использоваться только с source warning.
5. Persona snapshot фиксируется на старт сессии и не меняется молча во время runtime.
6. Persona policy не должна жить только в prompt text; она должна быть валидируемой и наблюдаемой.

## 6. Целевая Каноническая Модель

### 6.1 Attachment

Обязательные поля:

- `id`
- `lead_client_id`
- `session_id`
- `call_attempt_id`
- `message_id`
- `interaction_id`
- `domain_event_id`
- `uploaded_by`
- `filename`
- `content_type`
- `file_size`
- `sha256`
- `storage_path`
- `public_url`
- `document_type`
- `status`
- `ocr_status`
- `classification_status`
- `verification_status`
- `metadata`
- `created_at`

### 6.2 KnowledgeItem

Обязательные поля:

- `id`
- `source_type`
- `title`
- `body`
- `jurisdiction`
- `knowledge_status`
- `effective_from`
- `expires_at`
- `reviewed_by`
- `reviewed_at`
- `source_ref`
- `content_hash`
- `created_at`
- `updated_at`

### 6.3 MemoryPersona

Обязательные поля:

- `id`
- `lead_client_id`
- `address_form`
- `full_name`
- `gender`
- `role_title`
- `tone`
- `do_not_ask_again_slots`
- `confirmed_facts`
- `source_profile_version`
- `last_confirmed_at`

### 6.4 Session Persona Snapshot

Обязательные поля:

- `session_id`
- `lead_client_id`
- `persona_version`
- `address_form`
- `full_name`
- `gender`
- `role_title`
- `tone`
- `captured_at`
- `captured_from`

## 7. Attachment Pipeline

### 7.1 Этапы

- `uploaded`
- `received`
- `av_pending`
- `av_passed`
- `av_rejected`
- `ocr_pending`
- `ocr_done`
- `classification_pending`
- `classified`
- `verified`
- `rejected`

### 7.2 Правила

1. Любой upload создает `Attachment` record и доменное событие.
2. Дедупликация выполняется по `sha256` в пределах клиента и по policy, при этом duplicate link не должен терять факт повторной отправки.
3. `Attachment.status`, `ocr_status`, `classification_status` и `verification_status` не смешиваются.
4. Любое изменение статуса вложения должно быть replayable и observable.
5. Повторный звонок/чат должен видеть, какие документы уже получены и чего не хватает.

### 7.3 Канонические Domain Events

- `attachment.uploaded`
- `attachment.linked`
- `attachment.duplicate_detected`
- `attachment.av_passed`
- `attachment.av_rejected`
- `attachment.ocr_completed`
- `attachment.classified`
- `attachment.verified`
- `attachment.rejected`

### 7.4 CRM Projection

Каждое вложение должно быть видно в CRM timeline с:

- `domain_event_id`
- `attachment_id`
- `document_type`
- `status`
- `ocr_status`
- `classification_status`
- `source`

## 8. Knowledge Governance

### 8.1 Status Catalog

- `actual`
- `disputed`
- `outdated`
- `needs_review`

### 8.2 Политика Использования

#### actual

Можно использовать без дополнительных предупреждений.

#### disputed

Можно использовать только с явным warning/disclaimer.

#### needs_review

Можно использовать ограниченно и только с warning, если бизнес-политика это допускает.

#### outdated

Не участвует в рекомендациях и decision guidance. Может отображаться только как исторический контекст.

### 8.3 TTL И Review Policy

1. `expires_at` обязателен для чувствительных или быстроустаревающих знаний.
2. Истекший item автоматически переводится в `needs_review` или `outdated` по policy.
3. Должен существовать review SLA и очередь на ревью.
4. `reviewed_by` и `reviewed_at` обязательны для ручной актуализации.

### 8.4 Канонические Domain Events

- `knowledge_item.created`
- `knowledge_item.updated`
- `knowledge_item.reviewed`
- `knowledge_item.expired`
- `knowledge_item.status_changed`

## 9. Persona Policy

### 9.1 Что меняется

Сейчас persona consistency держится на:

- `persona_snapshot` в `custom_params`;
- prompt rules в `conversation_policy.py`.

Это полезно, но недостаточно.

Целевое правило:

- persona имеет отдельную модель;
- при старте сессии создается immutable session snapshot;
- runtime и policy engine работают от snapshot, а не от mutable ad hoc params.

### 9.2 Инварианты

1. В рамках одной сессии нельзя менять имя, пол, роль или форму обращения без explicit profile/persona update event.
2. Слот, помеченный в `do_not_ask_again_slots`, нельзя спрашивать повторно без достаточного основания.
3. Если факт уже подтвержден, система должна использовать его, а не пересобирать из воздуха.
4. Каждая существенная реплика должна вести либо к одному новому факту, либо к одному следующему шагу.

### 9.3 Канонические Domain Events

- `persona.snapshot_captured`
- `persona.updated`
- `persona.slot_locked`
- `persona.conflict_detected`
- `conversation.policy_violation_detected`

## 10. Conversation Policy Engine

### 10.1 Что это такое

Не просто prompt text, а сервис с проверками и explainable violations.

### 10.2 Обязательные Проверки

- `near_repeat`
- `missing_next_step`
- `too_long_for_mode`
- `persona_conflict`
- `asked_known_slot_again`
- `unjustified_identity_change`

### 10.3 Поведение По Режимам

#### call / center

- 1-2 короткие фразы;
- один следующий шаг;
- без длинных лекций;
- без повторного сбора уже известного.

#### chat

- кратко;
- не более нескольких предложений без запроса на глубину;
- follow-up вопрос только если он минимально необходим.

## 11. Next Best Action Integration

### 11.1 Attachment Awareness

`next_best_action` должен учитывать:

- missing required documents;
- pending OCR/classification;
- duplicate uploads;
- verified documents.

### 11.2 Knowledge Awareness

high-stakes рекомендации не должны основываться на `outdated`.

### 11.3 Persona Awareness

NBA и runtime prompts должны использовать уже подтвержденные persona facts, а не предлагать повторный сбор тех же данных.

## 12. Non-Breaking Migration Strategy

### Фаза 0. Inventory

- перечислить все attachment upload paths;
- перечислить все knowledge consumers;
- перечислить все persona-related fields и prompt hooks;
- перечислить все places, где anti-repeat/next-step логика уже есть.

### Фаза 1. Expand Schema

- добавить недостающие поля и статусы;
- добавить `MemoryPersona` и session snapshot storage;
- добавить knowledge TTL/review metadata;
- добавить `domain_event_id` linkage для attachments.

### Фаза 2. Dual-Write / Dual-Read Compatibility

- старые upload/read paths продолжают работать;
- новые поля и события пишутся параллельно;
- старые UI-компоненты получают backward-compatible response shape.

### Фаза 3. Policy Enforcement

- conversation policy engine начинает аудировать, но сначала может работать в warn-only mode;
- после подтверждения качества переводится в enforce mode для нужных режимов.

### Фаза 4. Cutover

- CRM/UI читают attachment/knowledge/persona из канонических моделей;
- ad hoc prompt hooks и разрозненные aliases сокращаются до compatibility wrappers.

## 13. File-Level Implementation Plan

### 13.1 Модели

Обновить или создать:

- `apps/api/app/models/client.py`
- `apps/api/app/models/rag.py`
- новый модуль для `MemoryPersona`, если его нельзя безопасно добавить в существующую модель

### 13.2 Сервисы

Создать:

- `apps/api/app/services/attachment_pipeline.py`
- `apps/api/app/services/knowledge_review_policy.py`
- `apps/api/app/services/persona_memory.py`
- `apps/api/app/services/conversation_policy_engine.py`

Если `conversation_policy.py` сохраняется, его нужно превратить в thin facade поверх нового engine.

### 13.3 API

Обновить:

- `apps/api/app/api/clients.py`
- `apps/api/app/api/training.py`
- knowledge/methodologist related endpoints, если они возвращают knowledge item data

Нужно:

- писать canonical attachment events;
- возвращать status-rich attachment response;
- работать с persona snapshot явно;
- не ломать текущие upload flows на transition phase.

### 13.4 Frontend

Обновить:

- `apps/web/src/components/clients/ClientAttachments.tsx`
- `apps/web/src/components/clients/ClientTimeline.tsx`
- `apps/web/src/components/training/SessionAttachmentButton.tsx`
- связанные type definition файлы

Нужно:

- показывать новые статусы pipeline;
- различать duplicate/verified/pending attachments;
- корректно отображать source warnings у disputed knowledge;
- не скрывать persona/policy conflicts, если они surfaced UI.

## 14. Data Contract Requirements

### 14.1 Attachment Response

Минимальная структура:

```json
{
  "id": "uuid",
  "lead_client_id": "uuid",
  "session_id": "uuid-or-null",
  "domain_event_id": "uuid",
  "status": "received",
  "ocr_status": "pending",
  "classification_status": "pending",
  "verification_status": "unverified",
  "duplicate_of": "uuid-or-null"
}
```

### 14.2 Knowledge Item Response

Минимальная структура:

```json
{
  "id": "uuid",
  "knowledge_status": "actual",
  "effective_from": "timestamp-or-null",
  "expires_at": "timestamp-or-null",
  "reviewed_by": "uuid-or-null",
  "reviewed_at": "timestamp-or-null",
  "jurisdiction": "string-or-null"
}
```

### 14.3 Persona Snapshot Response

Минимальная структура:

```json
{
  "session_id": "uuid",
  "lead_client_id": "uuid",
  "full_name": "string",
  "gender": "string-or-null",
  "role_title": "string-or-null",
  "address_form": "string-or-null",
  "captured_at": "timestamp"
}
```

## 15. Тестовый Пакет

### 15.1 Unit Tests

- duplicate attachment detection работает idempotent;
- OCR/classification state transitions валидны;
- outdated knowledge исключается из recommendation context;
- disputed/needs_review дают source warning;
- persona snapshot immutable внутри сессии;
- anti-repeat policy детектит повтор вопроса и persona conflict.

### 15.2 Contract Tests

- attachment upload из CRM и из training дают совместимый канонический response shape;
- ClientTimeline читает attachment/training metadata без drift;
- knowledge response contracts совпадают с backend model;
- persona snapshot contract совместим с runtime prompt assembler.

### 15.3 E2E Tests

Минимальные сценарии:

1. Клиент отправляет файл в training/call -> attachment виден в CRM timeline и карточке клиента.
2. Повторная отправка того же файла помечается как duplicate, но событие отправки не теряется.
3. Pending OCR/classification влияет на `next best action`.
4. `outdated` knowledge не попадает в high-stakes recommendation.
5. `disputed` knowledge попадает только с warning.
6. В рамках сессии AI не меняет имя/роль/пол и не задает повторный уже отвеченный вопрос.

## 16. Observability

Нужно добавить:

- число attachment uploads;
- число duplicate detections;
- pipeline lag по OCR/classification/verification;
- число knowledge items по status;
- число expired knowledge items;
- число source warnings в ответах;
- число persona conflicts;
- число near-repeat violations;
- число missing-next-step violations.

## 17. Rollback И Safe Deployment

### Rollback

Если новый trust layer дает неверный output:

- старые upload/read paths остаются как compatibility слой;
- новые статусные поля и события можно временно не читать из UI;
- canonical events продолжают писаться;
- policy enforcement можно переключить в audit-only mode.

### Safe Deployment

Нельзя включать hard enforcement, пока не подтверждены:

- attachment pipeline parity;
- knowledge filter correctness;
- persona snapshot correctness;
- conversation policy false-positive rate;
- UI compatibility для attachment/timeline/knowledge views.

## 18. Риски

1. Команда сведет ТЗ-4 к “добавим OCR”, оставив знания и persona в старом ad hoc состоянии.
2. Persona engine останется только prompt-текстом и не станет наблюдаемым сервисом.
3. Attachment pipeline начнет жить отдельно от CRM timeline и domain events.
4. Knowledge TTL/review появится в модели, но не будет реально влиять на retrieval.
5. Anti-repeat начнут лечить локальными regex без нормальной memory model.

## 19. Definition Of Done

ТЗ-4 считается завершенным только если:

- attachment domain имеет канонический pipeline и event linkage;
- knowledge governance использует status/TTL/review policy;
- outdated knowledge не участвует в рекомендациях;
- disputed/needs_review помечаются warning policy;
- persona snapshot хранится отдельно и используется runtime;
- conversation policy engine умеет детектить repeat, missing-next-step и persona conflicts;
- attachment/knowledge/persona contracts покрыты тестами;
- observability покрывает pipeline/status/policy violations;
- UI совместим с новыми response shapes.

## 20. Deliverables

- attachment pipeline service;
- knowledge review policy service;
- persona memory service;
- conversation policy engine;
- updated models and migrations;
- updated API endpoints;
- updated frontend attachment/timeline rendering;
- tests;
- dashboards and alerts;
- migration notes.

## 21. Prompt Для Coding Agent

Используй этот документ как trust-layer contract. Не решай задачу частичными локальными правками вида “добавили одно поле в attachment” или “усилили prompt”, если при этом не появляется канонический attachment pipeline, knowledge lifecycle и persona memory policy.

Сначала формализуй модели и статусы, затем введи canonical events и pipeline services, затем переведи API/UI на новые contracts, и только после этого включай более строгую policy enforcement логику. Любое место, где файл можно потерять между режимами, где high-stakes ответ опирается на `outdated`, или где persona/identity клиента меняется без explicit update event, считается незавершенной реализацией ТЗ.
