# ТЗ-4. Attachment, Knowledge Governance И Persona Policy

Статус: `implementation-ready spec` (rev 2 от 2026-04-27 — закрыты 10 critical
audit gaps + 5 wording clarifications + добавлено 15 deliverables в
§6/§7/§9/§11/§12/§13/§15/§19. См. §22 ниже для прикладного PR-плана).

Приоритет: `P1 / trust layer`

Связь с программой: документ 4 из 4. Должен реализовываться поверх [TZ-1](TZ-1_unified_client_domain_events.md), [TZ-2](TZ-2_runtime_integrity_guards_followup.md) и [TZ-3](TZ-3_constructor_scenario_version_contracts.md).

> **Изменения в rev 2** (после Opus-аудита 2026-04-27 + анализа hotfix PR #55):
>
> **Closed footguns (по аналогии с TZ-3 §7.3.1 auto-publish-on-update):**
> * §8.3.1 (NEW) — auto-flip TTL ТОЛЬКО `actual → needs_review`. Переход в
>   `outdated` возможен ТОЛЬКО через manual `reviewed_by`. Иначе day-of-TTL
>   массово выкосит SQL-фильтр в `rag_legal.py:217` всю knowledge base.
> * §12.4.1 (NEW) — Phase 4 cutover ОБЯЗАН удалить legacy
>   `custom_params["persona_snapshot"]` write в `training.py:531-537`.
>   Иначе `MemoryPersona` живёт параллельно с ad-hoc dict, runtime
>   читает первое попавшееся, drift continues invisibly.
> * §13.2.1 (NEW) — `conversation_policy.py` "thin facade" → явный
>   forbidden-list: удалить `conversation_policy_prompt()`,
>   `audit_assistant_reply()` оставить только как deprecated wrapper.
>
> **Field shape таблицы (по аналогии с TZ-3 §9.2.1 stage shape gap):**
> * §6.1.1 / §6.2.1 / §6.3.1 / §6.4.1 (NEW) — explicit таблицы column /
>   type / nullable / default / enum для всех 4 entities.
> * §6.5 (NEW) — slot-code catalog для `do_not_ask_again_slots` +
>   `address_form` enum (вы / ты / formal / informal / auto).
> * §6.6 (NEW) — `ClientProfile` vs `MemoryPersona` coexistence rules.
>   `ClientProfile` остаётся AI-character (objections/traps).
>   `MemoryPersona` — кросс-сессионная память реального CRM-клиента.
>
> **State machines + race contracts:**
> * §7.1.1 (NEW) — 4 раздельных state machines (status / ocr_status /
>   classification_status / verification_status) с allowed transitions.
> * §7.2.6 (NEW) — sha256 dedup contract: composite UNIQUE
>   `(client_id, sha256)` partial index + race resolution rule.
> * §9.2.5 (NEW) — `MemoryPersona.version` optimistic concurrency.
>
> **Backfill / migration:**
> * §12.0 (NEW) — Inventory deliverable: явный список upload paths
>   (`training.py:1059`, `clients.py:646`) и migration plan через
>   `attachment_pipeline.ingest_upload(...)`.
> * §12.1.1 (NEW) — explicit backfill spec для existing `attachments`
>   rows (synthetic `attachment.uploaded` events, `created_at` как event
>   timestamp). `domain_event_id` NOT NULL после backfill.
>
> **Filter coverage + promotion:**
> * §11.2.1 (NEW) — outdated filter работает в ОБОИХ слоях: RAG
>   retrieval + NBA decision boundary, оба покрыты тестами §15.1.
> * §12.3.1 (NEW) — warn-only → enforce promotion criteria
>   (≥7 дней warn-only, FP rate < 5% на ≥200 sessions, zero
>   persona_conflict false positives на §15.3 e2e, explicit
>   feature-flag flip).
>
> **UI surface map:**
> * §13.4.1 (NEW) — каждое event class из §7.3 / §8.4 / §9.3 имеет
>   minimum один UI surface (toast / sidebar badge / timeline chip).
>
> **Test additions:**
> * §15.1.7 (NEW) — AI persona prompt из `SessionPersonaSnapshot`
>   byte-identical при двух вызовах в одной сессии (формализует
>   regression test PR #55, перенесённый в TZ-4 boundary).
> * §15.3.7-8 (NEW) — concurrent same-sha256 race + outdated mid-
>   session status flip e2e сценарии.
>
> **DoD additions:**
> * §19 — explicit removal of legacy paths (`custom_params['persona_snapshot']`
>   write, `conversation_policy_prompt()`, direct `Attachment(...)` ctors
>   outside pipeline) listed как DoD items, не только additions новых paths.
>
> **Wording clarifications (rev 2):**
> * §7.2 #2 — dedup policy = same `sha256` AND same `client_id`
>   (cross-client dedup forbidden by privacy policy).
> * §9.2 invariant 1 — "explicit profile/persona update event" =
>   `persona.updated` из §9.3 (явная cross-reference).
> * §10.2 `unjustified_identity_change` — определено как: identity
>   field изменилось без preceding `persona.updated` в той же сессии
>   за последние 60 секунд.
> * §13.4 — каждое event class имеет минимум 1 UI surface (см. §13.4.1).
> * §14.1 — `verification_status: "unverified"` legal value (см. §7.1.1
>   таблицу — это enum verification_status, отдельный от status).

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

### 6.1.1 Attachment Field Shape (rev 2)

| Колонка | Тип | Nullable | Default | Enum/CHECK |
|---|---|---|---|---|
| `id` | uuid | NOT NULL | `gen_random_uuid()` | PK |
| `lead_client_id` | uuid | NOT NULL | — | FK→lead_clients(id) ON DELETE CASCADE; index |
| `session_id` | uuid | nullable | — | FK→training_sessions(id) ON DELETE SET NULL |
| `call_attempt_id` | uuid | nullable | — | FK→call_attempts(id) ON DELETE SET NULL |
| `message_id` | uuid | nullable | — | FK→messages(id) ON DELETE SET NULL |
| `interaction_id` | uuid | nullable | — | FK→client_interactions(id) ON DELETE SET NULL |
| `domain_event_id` | uuid | NOT NULL (после §12.1.1 backfill) | — | FK→domain_events(id) ON DELETE RESTRICT |
| `uploaded_by` | uuid | NOT NULL | — | FK→users(id) ON DELETE RESTRICT |
| `filename` | varchar(500) | NOT NULL | — | — |
| `content_type` | varchar(120) | NOT NULL | `'application/octet-stream'` | — |
| `file_size` | bigint | NOT NULL | `0` | CHECK file_size >= 0 |
| `sha256` | varchar(64) | NOT NULL | — | CHECK length(sha256) = 64; UNIQUE(client_id, sha256) WHERE duplicate_of IS NULL |
| `storage_path` | varchar(2000) | NOT NULL | — | — |
| `public_url` | varchar(2000) | nullable | — | — |
| `document_type` | varchar(60) | NOT NULL | `'unknown'` | enum: `passport / consent / contract / decision / debt_proof / income_proof / property_proof / receipt / unknown / other` |
| `status` | varchar(40) | NOT NULL | `'uploaded'` | enum §7.1.1 |
| `ocr_status` | varchar(40) | NOT NULL | `'not_required'` | enum §7.1.1 |
| `classification_status` | varchar(40) | NOT NULL | `'not_required'` | enum §7.1.1 |
| `verification_status` | varchar(40) | NOT NULL | `'unverified'` | enum §7.1.1 |
| `duplicate_of` | uuid | nullable | — | FK→attachments(id) ON DELETE SET NULL (self-ref) |
| `metadata` | jsonb | NOT NULL | `'{}'::jsonb` | произвольное (классификатор может писать `{document_subtype, ocr_confidence, classifier_version}`); НЕ дублирует первоклассные колонки |
| `created_at` | timestamp tz | NOT NULL | `now()` | — |

> **NB:** `verification_status` — отдельный enum от `status` (§7.1.1
> table); они не смешиваются (см. §7.2 #3). `metadata` НЕ должна
> содержать дубликаты первоклассных колонок (например, не писать
> `domain_event_id` в metadata после миграции — это первоклассная FK).

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

### 6.2.1 KnowledgeItem Field Shape (rev 2)

Реализуется как extension `LegalKnowledgeChunk` (`apps/api/app/models/rag.py:47-146`); таблица переименование в `knowledge_items` НЕ требуется (TZ-1 §11.3 retention rule распространяется и на этот случай).

| Колонка | Тип | Nullable | Default | Enum/CHECK |
|---|---|---|---|---|
| `id` | uuid | NOT NULL | `gen_random_uuid()` | PK |
| `source_type` | varchar(40) | NOT NULL | `'manual'` | enum: `manual / scraped / partner_feed / court_practice / methodologist / regulator` |
| `title` | varchar(300) | NOT NULL (для новых rows; existing — backfilled из `law_article` поля) | — | — |
| `body` | text | NOT NULL | — | хранит markdown; max 65536 chars (CHECK octet_length) |
| `jurisdiction` | varchar(20) | NOT NULL | `'RU'` | enum: `RU / EU / US / OTHER` |
| `knowledge_status` | varchar(20) | NOT NULL | `'actual'` | enum §8.1: `actual / disputed / outdated / needs_review` |
| `effective_from` | timestamp tz | nullable | — | bukatu_от какой даты item актуален; `NULL` = since-creation |
| `expires_at` | timestamp tz | nullable | — | TTL deadline; cron в §8.3 проверяет |
| `reviewed_by` | uuid | nullable | — | FK→users(id) ON DELETE SET NULL |
| `reviewed_at` | timestamp tz | nullable | — | вместе с `reviewed_by` фиксирует ручную актуализацию |
| `source_ref` | varchar(2000) | nullable | — | URL / docket / РКН-номер / иной machine-readable ref |
| `content_hash` | varchar(64) | NOT NULL (для новых rows) | — | SHA256 от `body`; UNIQUE по `(source_type, content_hash)` для дедупа импортов |
| `created_at` | timestamp tz | NOT NULL | `now()` | — |
| `updated_at` | timestamp tz | NOT NULL | `now()` | onupdate |

> **Backward-compat:** существующие LegalKnowledgeChunk-колонки (`fact_text`, `law_article`, `category`, `common_errors` …) сохраняются. Новые поля nullable до §12.1.1 backfill, затем NOT NULL.

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

### 6.3.1 MemoryPersona Field Shape (rev 2)

Новая таблица `memory_personas`, одна строка на `lead_client_id` (UNIQUE).

| Колонка | Тип | Nullable | Default | Enum/CHECK |
|---|---|---|---|---|
| `id` | uuid | NOT NULL | `gen_random_uuid()` | PK |
| `lead_client_id` | uuid | NOT NULL | — | FK→lead_clients(id) ON DELETE CASCADE; UNIQUE |
| `address_form` | varchar(20) | NOT NULL | `'auto'` | enum §6.5: `вы / ты / formal / informal / auto` |
| `full_name` | varchar(200) | NOT NULL | — | — |
| `gender` | varchar(20) | NOT NULL | `'unknown'` | enum: `male / female / other / unknown` |
| `role_title` | varchar(100) | nullable | — | роль клиента (должник / гарант / поручитель / представитель) |
| `tone` | varchar(40) | NOT NULL | `'neutral'` | enum: `neutral / friendly / formal / cautious / hostile` |
| `do_not_ask_again_slots` | jsonb | NOT NULL | `'[]'::jsonb` | list of slot codes из §6.5 каталога |
| `confirmed_facts` | jsonb | NOT NULL | `'{}'::jsonb` | dict slot_code→{value, confirmed_at, source} |
| `source_profile_version` | int | NOT NULL | `1` | bumps when full_name/gender/role_title/address_form changes |
| `version` | int | NOT NULL | `1` | optimistic concurrency token (§9.2.5) — bumps на каждый update |
| `last_confirmed_at` | timestamp tz | NOT NULL | `now()` | — |
| `created_at` | timestamp tz | NOT NULL | `now()` | — |
| `updated_at` | timestamp tz | NOT NULL | `now()` | onupdate |

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

### 6.4.1 SessionPersonaSnapshot Field Shape (rev 2)

Новая таблица `session_persona_snapshots`, **immutable** (одна строка на сессию).
После INSERT обновлять row нельзя — runtime гарантирует §9.2 invariant 1.

| Колонка | Тип | Nullable | Default | Enum/CHECK |
|---|---|---|---|---|
| `session_id` | uuid | NOT NULL | — | PK; FK→training_sessions(id) ON DELETE CASCADE; UNIQUE |
| `lead_client_id` | uuid | nullable | — | FK→lead_clients(id) ON DELETE SET NULL; nullable для simulation сессий |
| `persona_version` | int | NOT NULL | `1` | копия `MemoryPersona.version` на момент captured_at |
| `address_form` | varchar(20) | NOT NULL | `'auto'` | enum §6.5 |
| `full_name` | varchar(200) | NOT NULL | — | — |
| `gender` | varchar(20) | NOT NULL | `'unknown'` | enum как в §6.3.1 |
| `role_title` | varchar(100) | nullable | — | — |
| `tone` | varchar(40) | NOT NULL | `'neutral'` | enum как в §6.3.1 |
| `captured_at` | timestamp tz | NOT NULL | `now()` | — |
| `captured_from` | varchar(40) | NOT NULL | — | enum: `real_client / home_preview / training_simulation / pvp / center` |
| `mutation_blocked_count` | int | NOT NULL | `0` | observability: сколько раз runtime попытался изменить snapshot и был заблокирован (§9.2 invariant 1) |

### 6.5 Slot Catalog & Address-Form Enum (rev 2)

#### `address_form` enum
Используется в `MemoryPersona.address_form` и `SessionPersonaSnapshot.address_form`.

| Value | Семантика |
|---|---|
| `вы` | строго на «вы» |
| `ты` | строго на «ты» |
| `formal` | формальный регистр (официальные обращения), часто = «вы» |
| `informal` | неформальный регистр |
| `auto` | runtime выбирает по эвристике (default до первого confirmation) |

#### Slot codes для `do_not_ask_again_slots` и `confirmed_facts`
Slot — это атомарный факт о клиенте, который AI не должен спрашивать повторно после подтверждения. Каталог fixed (расширяется отдельным PR через миграцию).

| Slot code | Описание | Тип значения |
|---|---|---|
| `full_name` | ФИО | string |
| `phone` | основной телефон | string |
| `email` | основной email | string |
| `city` | город проживания | string |
| `age` | возраст | int |
| `gender` | пол | enum (male/female/other) |
| `role_title` | роль (должник/гарант/представитель) | string |
| `total_debt` | сумма долга, ₽ | int |
| `creditors` | список кредиторов | list[{name, amount}] |
| `income` | официальный доход / месяц, ₽ | int |
| `income_type` | тип дохода | enum (official/gray/mixed/none) |
| `family_status` | семейное положение | enum (single/married/married_kids/divorced/widow) |
| `children_count` | количество детей | int |
| `property_status` | имущество (единственное жильё / нет) | enum |
| `consent_124fz` | согласие на обработку ПДн (152-ФЗ) | bool + timestamp |
| `next_contact_at` | договорённость о следующем контакте | timestamp |
| `lost_reason` | причина выхода из воронки | string |

`confirmed_facts` JSONB shape:
```json
{
  "full_name": {"value": "Макаров Григорий Львович", "confirmed_at": "2026-04-27T10:00Z", "source": "session/abc"},
  "city": {"value": "Рязань", "confirmed_at": "2026-04-27T10:01Z", "source": "session/abc"}
}
```

### 6.6 ClientProfile vs MemoryPersona Coexistence (rev 2)

Эти модели **никогда не share rows** и решают разные задачи:

| | ClientProfile (`apps/api/app/models/roleplay.py:442`) | MemoryPersona (новая) |
|---|---|---|
| Роль | AI-character training entity (что говорит/как сопротивляется) | Кросс-сессионная human-CRM-client memory |
| Ключ | `session_id` UNIQUE (одна на сессию) | `lead_client_id` UNIQUE (одна на клиента) |
| Lifetime | живёт со временем сессии | живёт со временем клиента |
| Источник | scenarios / archetype generator / `persist_client_profile_from_dict` (PR #55) | manual confirmation events `persona.updated` |
| Поля overlap (`full_name`, `gender`) | да, но разный смысл (см. правило ниже) | да |

**Resolution rule** when session has both `real_client_id` AND `archetype_code`:

* Identity-уровень (`address_form / full_name / role_title / gender`) — **MemoryPersona wins**.
* Behavior-уровень (`hidden_objections / trap_ids / chain_id / cascade_ids / breaking_point / fears / soft_spot`) — **ClientProfile wins** (это AI-character behavior, отделено от identity).
* Нейтральные поля (`city / total_debt / creditors / income`) — **MemoryPersona если presented в `confirmed_facts`, иначе ClientProfile**.

После §12 Phase 4 cutover `ClientProfile.full_name` и `ClientProfile.gender` НЕ читаются runtime'ом для real-client сессий (только для simulation/archetype-only). PR #55 hotfix продолжает работать как backstop: `persist_client_profile_from_dict` пишет ClientProfile с identity полями, но runtime их игнорирует когда есть SessionPersonaSnapshot.

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

### 7.1.1 Per-Field Status Enums (rev 2)

§7.2 #3 говорит «не смешиваются» — это означает ЧЕТЫРЕ раздельных state machines, по одной на каждую status-колонку. Все 11 значений из §7.1 распределены ниже.

#### `Attachment.status` (lifecycle phase)

| Value | Описание |
|---|---|
| `uploaded` | пользователь нажал upload, FE начал PUT/POST |
| `received` | backend принял body, sha256 вычислен, row создан |
| `rejected` | upload отклонён (size limit / mime блокировка / privacy violation) |

Allowed transitions:

```
uploaded → received → (terminal; ocr/classification/verification дальше идут в своих колонках)
uploaded → rejected (terminal)
```

#### `Attachment.ocr_status`

| Value | Описание |
|---|---|
| `not_required` | для текстовых mime типов или если OCR feature off |
| `ocr_pending` | в очереди на OCR |
| `ocr_done` | text successfully extracted; может быть пустым |
| `ocr_failed` | OCR engine упал; retry policy в pipeline |

Allowed transitions:

```
not_required (terminal — initial state для не-image/PDF)
ocr_pending → ocr_done (terminal)
ocr_pending → ocr_failed → ocr_pending (retry, max N в metadata)
```

#### `Attachment.classification_status`

| Value | Описание |
|---|---|
| `not_required` | если document_type явно указан manual или classifier off |
| `classification_pending` | classifier в очереди |
| `classified` | document_type определён или confirmed |
| `classification_failed` | classifier upal или confidence < threshold |

Allowed transitions:

```
not_required (terminal)
classification_pending → classified (terminal)
classification_pending → classification_failed (terminal — manual review)
```

#### `Attachment.verification_status`

| Value | Описание |
|---|---|
| `unverified` | initial state — никто не verified |
| `pending_review` | в queue для manual review методологом/РОП |
| `verified` | подтверждено как валидный документ нужного типа |
| `rejected_review` | отклонено по review (фейк / не тот тип / нечитаемо) |

Allowed transitions:

```
unverified → pending_review → verified (terminal)
unverified → pending_review → rejected_review (terminal)
unverified → verified (auto-verify policy для определённых document_type, если configured)
```

> **NB:** `verified` и `rejected_review` — terminal. Изменение требует
> создания нового Attachment row (повторный upload), не мутации
> существующего. Это часть §7.2 #4 «replayable and observable».

### 7.2 Правила

1. Любой upload создает `Attachment` record и доменное событие.
2. Дедупликация выполняется по `sha256` в пределах клиента (см. §7.2.6 для dedup contract) — same `sha256` AND same `client_id`. Cross-client dedup ЗАПРЕЩЁН (privacy policy). Duplicate link не должен терять факт повторной отправки.
3. `Attachment.status`, `ocr_status`, `classification_status` и `verification_status` не смешиваются — это четыре раздельных state machines, см. §7.1.1.
4. Любое изменение статуса вложения должно быть replayable и observable — каждое state-transition порождает canonical Domain Event (§7.3).
5. Повторный звонок/чат должен видеть, какие документы уже получены и чего не хватает (см. §11.1).

### 7.2.6 sha256 Dedup Contract (rev 2)

#### SQL уровень

В миграции D1 добавляется composite UNIQUE partial index:

```sql
CREATE UNIQUE INDEX uq_attachments_client_sha256_orig
ON attachments (lead_client_id, sha256)
WHERE duplicate_of IS NULL;
```

Этот индекс гарантирует что **один и тот же файл (sha256) для одного клиента может существовать как «оригинал» только один раз**. Дубликаты (с непустым `duplicate_of`) добавляются без ограничения — это и есть «не теряем факт повторной отправки».

#### Race resolution

Два concurrent upload одного файла одним менеджером:

1. Pipeline `attachment_pipeline.ingest_upload(...)` сначала ищет существующий original row через `SELECT FOR UPDATE WHERE lead_client_id=X AND sha256=Y AND duplicate_of IS NULL`.
2. **Если найден** → INSERT новый row с `duplicate_of=existing.id`, status=`received`, и emit `attachment.duplicate_detected` event.
3. **Если не найден** → INSERT новый row с `duplicate_of=NULL`. Если IntegrityError (race с другим writer'ом) → re-fetch (повтор шага 1), upgrade себя в `duplicate_of=winning_id`.
4. Никогда не silently drop upload — оба upload'а получают свой Attachment row + Domain Event. Менеджер видит «отправлено успешно» в обоих случаях.

#### Что хранится в metadata

```json
{
  "duplicate_of_event_id": "uuid",  // первый upload's domain_event_id
  "duplicate_count_at_upload": 3,    // сколько было дубликатов на момент этого
  "uploaded_via": "session/abc"      // origin для аудита
}
```

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
2. Истекший item автоматически переводится в `needs_review` (НЕ `outdated` — см. §8.3.1 critical rule).
3. Должен существовать review SLA и очередь на ревью.
4. `reviewed_by` и `reviewed_at` обязательны для ручной актуализации.

### 8.3.1 🔴 Auto-flip rule (rev 2 — closed footgun)

**ПРАВИЛО**: автоматический cron-таск переводит истёкший item ТОЛЬКО `actual → needs_review`. Переход в `outdated` ВОЗМОЖЕН ТОЛЬКО через manual `reviewed_by` action.

**Почему так строго**: в коде `apps/api/app/services/rag_legal.py:217` (и `rag_legal_v2.py:131`) уже стоит SQL-фильтр `WHERE knowledge_status != 'outdated'`. Если ослабить правило и позволить cron массово переводить в `outdated` (например, на день где у 100 items одновременно истёк TTL), то весь блок knowledge базы мгновенно исчезнет из RAG retrieval. Менеджеры начнут получать от AI «не знаю, нет данных» по типичным вопросам.

Это точный аналог **TZ-3 §7.3.1 auto-publish-on-update** footgun — автоматический mutate canonical state без manual review приводит к катастрофе.

#### Поведение cron

```python
# apps/api/app/services/knowledge_review_policy.py — ежедневный cron
async def expire_overdue_knowledge_items(db):
    items = await db.execute(
        select(LegalKnowledgeChunk)
        .where(LegalKnowledgeChunk.expires_at < now())
        .where(LegalKnowledgeChunk.knowledge_status == "actual")
    )
    for item in items:
        item.knowledge_status = "needs_review"   # ← ONLY this transition
        await emit_knowledge_event(
            db, event_type="knowledge_item.expired",
            knowledge_item_id=item.id,
            from_status="actual", to_status="needs_review",
            reviewed_by=None,                    # ← NULL signals automated
        )
```

#### Manual `outdated` transition

Только через `POST /admin/knowledge/{id}/mark-outdated` с body `{reason}`. Эндпоинт:
* Требует role `rop` или `admin`.
* Записывает `reviewed_by=user.id, reviewed_at=now()`.
* Emit `knowledge_item.status_changed` с `from_status` = текущий, `to_status='outdated'`.
* Появляется в admin Audit Log.

#### Test

Добавить в §15.1: `test_auto_expire_never_writes_outdated` — pre-fix-fail тест: создать item с TTL прошлым, прогнать cron, assert `knowledge_status == 'needs_review'` (НЕ `'outdated'`).

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

### 11.2.1 Two-Layer Outdated Filter (rev 2)

`outdated` filter ОБЯЗАН работать в ДВУХ слоях независимо:

1. **RAG retrieval** (`apps/api/app/services/rag_legal.py:217`,
   `rag_legal_v2.py:131`) — SQL-фильтр уже existing, оставляем.
2. **NBA decision boundary** (`apps/api/app/services/next_best_action.py`)
   — добавляем re-check на каждом recommendation: если incoming
   knowledge ref имеет `knowledge_status != 'actual'`, recommendation
   либо отбрасывается, либо помечается `requires_warning=true`.

**Почему оба слоя**:

* Если только RAG — NBA-эвристики (которые могут вызывать knowledge
  через закэшированные snapshot'ы или через legacy paths) пропустят
  outdated content.
* Если только NBA — raw RAG callers (например, прямой вызов из chat
  handler без NBA посредника) сольют outdated в ответ.
* Race: item был `actual` на момент RAG retrieval, стал `outdated`
  посреди сессии — NBA layer ловит mid-session flip.

#### Tests

Оба слоя покрываются §15.1 unit tests:
* `test_rag_retrieval_excludes_outdated`
* `test_nba_rejects_outdated_knowledge_ref`
* `test_nba_handles_mid_session_status_flip` (race scenario, §15.3.8)

### 11.3 Persona Awareness

NBA и runtime prompts должны использовать уже подтвержденные persona facts, а не предлагать повторный сбор тех же данных.

### 11.3 Persona Awareness

NBA и runtime prompts должны использовать уже подтвержденные persona facts, а не предлагать повторный сбор тех же данных.

## 12. Non-Breaking Migration Strategy

### Фаза 0. Inventory

- перечислить все attachment upload paths;
- перечислить все knowledge consumers;
- перечислить все persona-related fields и prompt hooks;
- перечислить все places, где anti-repeat/next-step логика уже есть.

### 12.0 Inventory Deliverable (rev 2)

Audit 2026-04-27 уже выполнил часть inventory work; результаты ниже фиксируются в спеке так чтобы D2/D3 PR'ы НЕ открывали третий/четвёртый upload path параллельно existing ones.

#### Attachment upload paths (текущие)

| Path | File:Line | Что делает | Plan |
|---|---|---|---|
| Training session upload | `apps/api/app/api/training.py:1059` | Прямой `Attachment(...)` constructor + `ClientInteraction` insert | **D2** перевести на `attachment_pipeline.ingest_upload(...)` |
| CRM card upload | `apps/api/app/api/clients.py:646` | Прямой `Attachment(...)` constructor с `lead_client_id`, без `session_id` | **D2** перевести на `attachment_pipeline.ingest_upload(...)`. ⚠️ Нужен `correlation_id = attachment.id` (нет session, см. TZ-1 §3 invariant 4) |

После D2: **direct `Attachment(...)` constructor выше allow-list (только `attachment_pipeline.py` + repair jobs)** — проверяется AST guard'ом (`tests/test_attachment_invariants.py`, добавляется в D2).

#### Knowledge consumers (текущие)

| Path | File:Line | Filter outdated? |
|---|---|---|
| RAG legal v1 | `apps/api/app/services/rag_legal.py:217` | ✅ SQL filter |
| RAG legal v2 | `apps/api/app/services/rag_legal_v2.py:131` | ✅ SQL filter |
| RAG retrieval at training | `apps/api/app/services/rag_legal.py:309,712` | ✅ |
| Methodologist arena chunks endpoint | `apps/api/app/api/rop.py:612-721` | ❌ — list endpoint показывает все, что норм для методолога |
| **NBA (`next_best_action.py`)** | apps/api/app/services/next_best_action.py | ❌ **MISSING** — добавить в D4 (§11.2.1) |

#### Persona-related fields / prompt hooks (текущие)

| Source | File:Line | Что хранит | Plan |
|---|---|---|---|
| `custom_params["persona_snapshot"]` | `apps/api/app/api/training.py:531-537` | 5 fields ad-hoc dict | **D3** заменить на `SessionPersonaSnapshot.load_for_session(...)`; **§12.4.1** удалить write полностью в D7 cutover |
| `ClientProfile` (роль AI-character) | `apps/api/app/models/roleplay.py:442-493` | Объект для AI-роли клиента в тренировке | **Сохранить** — см. §6.6 coexistence rules. PR #55 hotfix продолжает работать. |
| `conversation_policy_prompt()` | `apps/api/app/services/conversation_policy.py:28-48` | Hard-coded RU text injected в system prompt | **D5** удалить (§13.2.1 forbidden list); заменить на `engine.render_prompt(snapshot, mode)` |
| `audit_assistant_reply()` | `apps/api/app/services/conversation_policy.py:67-103` | 3 из 6 checks (`too_long`, `near_repeat`, `missing_next_step`) | **D5** оставить как deprecated wrapper, делегирует `engine.audit(...)` |

### Фаза 1. Expand Schema

- добавить недостающие поля и статусы;
- добавить `MemoryPersona` и session snapshot storage;
- добавить knowledge TTL/review metadata;
- добавить `domain_event_id` linkage для attachments.

### 12.1.1 Migration Backfill Spec (rev 2)

D1 alembic миграция должна включать backfill этапы для existing rows (не только ALTER ADD COLUMN). Без backfill `domain_event_id NOT NULL` constraint упадёт на existing data.

#### Attachments backfill

```sql
-- 1. Add columns nullable first
ALTER TABLE attachments ADD COLUMN call_attempt_id uuid;
ALTER TABLE attachments ADD COLUMN domain_event_id uuid;
ALTER TABLE attachments ADD COLUMN verification_status varchar(40) DEFAULT 'unverified' NOT NULL;
ALTER TABLE attachments ADD COLUMN duplicate_of uuid;

-- 2. Backfill domain_event_id с synthetic attachment.uploaded events
-- (one event per existing attachment row, occurred_at = attachment.created_at)
INSERT INTO domain_events (id, lead_client_id, event_type, aggregate_type,
                           aggregate_id, source, actor_id, occurred_at,
                           idempotency_key, correlation_id, schema_version)
SELECT gen_random_uuid(), a.lead_client_id, 'attachment.uploaded', 'attachment',
       a.id, 'backfill_d1', a.uploaded_by, a.created_at,
       'attachment-backfill:' || a.id::text, a.id::text, 1
FROM attachments a
WHERE a.lead_client_id IS NOT NULL  -- skip orphans, they get NULL fk
  AND NOT EXISTS (
    SELECT 1 FROM domain_events de
    WHERE de.aggregate_id = a.id AND de.event_type = 'attachment.uploaded'
  );

-- 3. Link attachments to their backfilled events
UPDATE attachments a
SET domain_event_id = de.id
FROM domain_events de
WHERE de.aggregate_id = a.id
  AND de.event_type = 'attachment.uploaded'
  AND a.domain_event_id IS NULL;

-- 4. Now SET NOT NULL (after backfill is complete)
ALTER TABLE attachments ALTER COLUMN domain_event_id SET NOT NULL;

-- 5. UNIQUE partial index for sha256 dedup (§7.2.6)
CREATE UNIQUE INDEX uq_attachments_client_sha256_orig
ON attachments (lead_client_id, sha256)
WHERE duplicate_of IS NULL;
```

> ⚠️ **CLAUDE.md §4.3** — миграция использует `INSERT ... SELECT` через
> `op.execute(sa.text(...))` — должна пройти `alembic upgrade head` на
> CI Postgres до merge.
>
> ⚠️ Если в проде существуют orphan attachments без `lead_client_id`
> (старые WS uploads), backfill их пропустит и они останутся с
> `domain_event_id IS NULL`. После SET NOT NULL они станут
> непередаваемы — это **acceptable** (отдельная repair job очистит
> orphans до миграции, см. CRM repair pattern из TZ-1).

#### `custom_params["persona_snapshot"]` → `session_persona_snapshots` backfill

D3 миграция (отдельная revision):

```sql
INSERT INTO session_persona_snapshots
    (session_id, lead_client_id, persona_version, address_form,
     full_name, gender, role_title, tone, captured_at, captured_from,
     mutation_blocked_count)
SELECT
    s.id,
    s.real_client_id,                 -- nullable for simulation
    1,
    'auto',
    COALESCE(s.custom_params->>'persona_snapshot'->>'full_name',
             'Backfilled Persona'),
    'unknown',
    NULL,
    'neutral',
    s.started_at,
    CASE
      WHEN s.real_client_id IS NOT NULL THEN 'real_client'
      WHEN s.source = 'home' THEN 'home_preview'
      WHEN s.source = 'pvp' THEN 'pvp'
      WHEN s.source = 'center' THEN 'center'
      ELSE 'training_simulation'
    END,
    0
FROM training_sessions s
WHERE NOT EXISTS (
    SELECT 1 FROM session_persona_snapshots sps WHERE sps.session_id = s.id
);
```

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

### 12.3.1 Warn-only → Enforce Promotion Criteria (rev 2)

Без measurable threshold §12 Phase 3 — всё то же DoD-ловушка как TZ-3
auto-publish. Promotion возможен ТОЛЬКО при выполнении ВСЕХ условий:

| Критерий | Threshold | Источник данных |
|---|---|---|
| Время в warn-only mode | ≥ 7 дней prod (cron-time) | feature flag flip date |
| False-positive rate (per check) | < 5% | annotated sample of ≥ 200 sessions; ROP/admin labels violation as TP/FP в admin UI |
| `persona_conflict` zero false-positive guarantee | 0 на §15.3 e2e suite | автотесты (CI gate) |
| Explicit feature flag flip | manual env var `tz4_conversation_policy_enforce_enabled=1` + `docker compose restart api` | ops checklist |

Promotion checklist (ops procedure):
1. Один раз в неделю review `runtime_conversation_policy_violations_total`
   counter (см. §16) и FP queue в admin UI.
2. После 7 дней + low FP rate — admin marks "ready for enforce".
3. ROP signs off через `POST /admin/runtime/policy/promote` (admin-only,
   audited).
4. Env var flip + restart.
5. Rollback план: `tz4_conversation_policy_enforce_enabled=0` + restart →
   мгновенно warn-only.

### Фаза 4. Cutover

- CRM/UI читают attachment/knowledge/persona из канонических моделей;
- ad hoc prompt hooks и разрозненные aliases сокращаются до compatibility wrappers.

### 12.4.1 🔴 Phase 4 MUST-DELETE list (rev 2 — closed footgun)

Phase 4 cutover ОБЯЗАН удалить следующие legacy paths (не оставлять
параллельно с canonical models — иначе drift returns invisibly):

| Что удалить | Файл:строка | Почему |
|---|---|---|
| `custom_params["persona_snapshot"] = {...}` write | `apps/api/app/api/training.py:531-537` | После SessionPersonaSnapshot ad-hoc dict даёт два источника правды; runtime прочитает первое попавшееся → drift |
| `conversation_policy_prompt()` callers | `apps/api/app/services/conversation_policy.py:28-48` + все импорты | Engine.render_prompt() единственный путь; иначе hard-coded RU text shadow |
| Direct `Attachment(...)` constructor | вне `apps/api/app/services/attachment_pipeline.py` | Защищается AST guard (D2) |
| Frontend hard-coded `STATUS_LABELS` для `received/processing/ready/failed` | `apps/web/src/components/clients/ClientAttachments.tsx:17-22` | Заменить на all 11 statuses из §7.1.1 + сгенерированный label map |

**Test enforcement**: добавить в `tests/test_persona_no_legacy_writes.py`
AST grep на `custom_params\['persona_snapshot'\]\s*=`. Должен fail
после Phase 4 если кто-то re-introduce legacy write.

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

### 13.2.1 Forbidden Patterns (rev 2)

После §12 Phase 4 cutover следующие patterns ЗАПРЕЩЕНЫ в `apps/api/`:

| Pattern | Forbidden because | AST guard test |
|---|---|---|
| `LegalKnowledgeChunk(title=..., content=..., article_reference=...)` outside `attachment_pipeline.py` | Уже в `tests/test_arena_chunk_invariants.py` (TZ-3 C5) | существует |
| `Attachment(...)` constructor вне `attachment_pipeline.py` или `attachment_storage.py` repair | Bypasses pipeline → no canonical events | NEW: `tests/test_attachment_invariants.py` (D2) |
| `custom_params['persona_snapshot'] = ...` write | Drift с SessionPersonaSnapshot | NEW: `tests/test_persona_no_legacy_writes.py` (D7) |
| `conversation_policy_prompt()` import outside `conversation_policy.py` itself | Shadow path для prompt assembly | NEW: `tests/test_conversation_policy_engine.py` (D5) |
| `DomainEvent(event_type='...')` constructor с string не из allow-list | Typos like `attachements.uploaded` silently fail | NEW: `client_domain.py` `ALLOWED_EVENT_TYPES: frozenset` enforced на runtime + `tests/test_domain_event_allowlist.py` (D2) |
| `LegalKnowledgeChunk.knowledge_status = 'outdated'` cron-style write | §8.3.1 only manual review | NEW: AST grep test (D4) |

Все 6 guards идут в **blocking CI scope** (CLAUDE.md §1 CI gate) — fail
PR перед merge, не на прод.

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

### 13.4.1 UI Surface Map (rev 2)

Каждый canonical event class из §7.3 / §8.4 / §9.3 ДОЛЖЕН иметь
минимум один UI surface — backend silent emission без UI читателя =
нет ценности для оператора.

| Event class | UI Surface | Component | Trigger |
|---|---|---|---|
| `attachment.uploaded` / `linked` | Timeline chip + ClientAttachments row | `ClientTimeline.tsx` (NEW attachment row), `ClientAttachments.tsx` | Real-time через WS notification |
| `attachment.duplicate_detected` | Toast «Файл уже был отправлен N раз» + duplicate-of link на ClientAttachments | `SessionAttachmentButton.tsx` (toast), `ClientAttachments.tsx` (link) | После upload response |
| `attachment.av_passed` / `av_rejected` | Status badge на attachment row | `ClientAttachments.tsx` | WS update |
| `attachment.ocr_completed` | Spinner → ✓ icon transition | `ClientAttachments.tsx` | WS update |
| `attachment.classified` | document_type badge | `ClientAttachments.tsx` | WS update |
| `attachment.verified` / `rejected` | green/red verification badge | `ClientAttachments.tsx` | WS update |
| `knowledge_item.expired` | Admin sidebar counter badge | NEW: `apps/web/src/components/dashboard/KnowledgeReviewQueue.tsx` (D6) | Polling /admin/knowledge/queue |
| `knowledge_item.status_changed` | Toast в admin panel | `KnowledgeReviewQueue.tsx` | WS or polling |
| `persona.snapshot_captured` | (silent — only audit log) | — | — |
| `persona.updated` | Toast «Имя клиента обновлено» в training UI | `apps/web/src/app/training/[id]/page.tsx` (NEW handler) | WS update |
| `persona.conflict_detected` | Inline warning chip в pre-call screen + toast | `ClientCard.tsx`, `apps/web/src/app/training/[id]/call/page.tsx` | WS push |
| `conversation.policy_violation_detected` | Sidebar badge counter (warn-only) → blocking modal (enforce mode) | `apps/web/src/app/training/[id]/call/page.tsx` | WS push |

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

### 15.1.7 Additional Unit Tests (rev 2)

* **`test_persona_prompt_byte_identical_within_session`** — формализует regression test PR #55 на новой границе: build a SessionPersonaSnapshot, render system prompt дважды через `engine.render_prompt(snapshot, mode)`, assert byte-equal. Защищает §9.2 invariant 1.
* **`test_auto_expire_never_writes_outdated`** — pre-fix-fail test §8.3.1: создать item с TTL прошлым, прогнать cron, assert `knowledge_status == 'needs_review'` (НЕ `outdated`).
* **`test_nba_rejects_outdated_knowledge_ref`** — §11.2.1 двухслойный filter: NBA получает knowledge ref с `status='outdated'` → recommendation отброшено (или помечено `requires_warning=true`).
* **`test_attachment_status_field_isolation`** — §7.2 #3: проверить что `status / ocr_status / classification_status / verification_status` не путают значения (transition в одной не trigger transition в другой).
* **`test_sha256_dedup_race_inserts_duplicate_row`** — §7.2.6 + CLAUDE.md §4.1: `asyncio.gather(2x ingest_upload(same sha256))` → один original + один duplicate row, оба в timeline.
* **`test_memory_persona_optimistic_concurrency`** — §9.2.5: 2 concurrent updates с одинаковым `version=N` → один success (`version=N+1`), второй PersonaConflict 409.

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
7. **Concurrent same-sha256 race (rev 2)**: 2 параллельных upload одного файла одним менеджером через `asyncio.gather` — оба upload получают свой Attachment row, второй с `duplicate_of`, оба `attachment.uploaded` events в timeline. Закрывает §7.2.6.
8. **Outdated mid-session status flip (rev 2)**: создать item `actual` → начать сессию → admin flip item к `outdated` через `POST /admin/knowledge/{id}/mark-outdated` → следующий NBA call в той же сессии НЕ использует item. Закрывает §11.2.1.

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

ТЗ-4 считается завершенным только если **выполнены все additions И все removals** (rev 2 — добавлены removal items):

**Additions:**
- attachment domain имеет канонический pipeline и event linkage;
- knowledge governance использует status/TTL/review policy;
- outdated knowledge не участвует в рекомендациях (двухслойный filter §11.2.1);
- disputed/needs_review помечаются warning policy;
- persona snapshot хранится отдельно (SessionPersonaSnapshot) и используется runtime;
- conversation policy engine умеет детектить все 6 проверок §10.2;
- attachment/knowledge/persona contracts покрыты тестами;
- observability покрывает pipeline/status/policy violations (§16);
- UI совместим с новыми response shapes (§13.4.1 surface map);
- 6 AST guards (§13.2.1) в blocking CI scope.

**Removals (rev 2 — explicit DoD requirement):**
- ❌ `custom_params["persona_snapshot"]` write удалён (`apps/api/app/api/training.py:531-537`);
- ❌ `conversation_policy_prompt()` callers удалены, осталась только deprecated wrapper в `conversation_policy.py`;
- ❌ Direct `Attachment(...)` constructor вне `attachment_pipeline.py` удалён;
- ❌ Frontend hard-coded 4-status `STATUS_LABELS` в `ClientAttachments.tsx:17-22` заменён на 11-status map;
- ❌ Auto-flip cron `actual → outdated` запрещён (только `actual → needs_review`, §8.3.1).

**Promotion gate** (§12.3.1):
- Conversation policy engine ≥ 7 дней warn-only в prod;
- FP rate < 5% per check on annotated sample of ≥ 200 sessions;
- Zero `persona_conflict` false positives on §15.3 e2e suite;
- Explicit feature-flag flip via `tz4_conversation_policy_enforce_enabled=1`.

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

## 22. Phased PR Plan (rev 2)

| PR | Scope | Why this order | Size |
|---|---|---|---|
| **D0** (this PR) | Spec rev 2 — 10 critical gaps + 5 wording + 15 deliverables | Без spec корректирующих rules дальнейшие D1-D7 наслоят баги по типу TZ-3 auto-publish | docs only |
| **D1 — Foundation** | Alembic migration: добавить 4 columns + duplicate_of к attachments, 9 columns к LegalKnowledgeChunk, новые таблицы memory_personas + session_persona_snapshots, UNIQUE indices §7.2.6, CHECK constraints для enums §7.1.1, backfill §12.1.1. ORM modeling. | Pure expand. Старый код продолжает работать. | Большой (alembic + 6 моделей) |
| **D2 — Attachment pipeline** | `services/attachment_pipeline.py` с 9 canonical events. AST guard `tests/test_attachment_invariants.py` (no direct ctor). Refactor `clients.py:646` + `training.py:1059` через pipeline. Добавить `ALLOWED_EVENT_TYPES: frozenset` в `client_domain.py`. | Первый user-visible: full lifecycle visible в CRM | Большой |
| **D3 — Persona memory** | `services/persona_memory.py`. На session start пишет `SessionPersonaSnapshot` + emit `persona.snapshot_captured`. Read-through cache для prompt assembler. **Backfill §12.1.1 для existing sessions**. PR #55 hotfix продолжает работать как backstop (см. §6.6). | Закрывает root cause hotfix #55 на правильном уровне | Большой |
| **D4 — Knowledge TTL** | `services/knowledge_review_policy.py` cron. AST guard на запрет `cron-style write knowledge_status='outdated'` (§8.3.1). NBA filter добавление (§11.2.1). Admin endpoint `POST /admin/knowledge/{id}/mark-outdated`. | Без NBA layer §11.2.1 двухслойный filter не работает | Средний |
| **D5 — Conversation policy engine v2** | `services/conversation_policy_engine.py` с 6 проверками. `conversation_policy.py` → thin facade (deprecated wrapper). Warn-only mode + `conversation.policy_violation_detected` event. UI surface §13.4.1. | Без MemoryPersona (D3) `persona_conflict` / `asked_known_slot_again` не expressible | Большой |
| **D6 — FE uplift** | `ClientAttachments.tsx` 11 statuses, `ClientTimeline.tsx` attachment rows, `SessionAttachmentButton.tsx` pipeline progress, новый `KnowledgeReviewQueue.tsx` для admin, persona conflict toast в training UI | После backend D2-D5 ready | Средний |
| **D7 — Cutover** | Promotion criteria (§12.3.1) check → enforce mode flag flip. **Удалить legacy paths из §12.4.1 must-delete list**. Add `tests/test_persona_no_legacy_writes.py` AST guard. | DoD §19 removals только сейчас | Финальный |

**Каждый PR**:
- rebase на origin/main перед push (CLAUDE.md §1)
- собственные unit tests + AST guards
- Postgres-CI tests для concurrency (§4.1)
- alembic upgrade head pass на real PG (§4.3)
- post-merge CI green check (§4.2)
- prod smoke (§4.4)
- subagent calls — `model="opus"` (§6)
