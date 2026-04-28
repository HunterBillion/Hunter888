# Архитектура Домена `Клиенты`

Документ фиксирует целевую архитектуру модуля `Клиенты` для всего репозитория `Hunter888-main`.

Статус документа: `target architecture`

## 1. Принцип

`Клиенты` — это один домен, а не два независимых продукта.

Текущие сущности `real_clients` и `game_crm` должны трактоваться так:

- `real_clients` — ядро клиентского домена
- `game_crm` — AI/continuity-слой внутри того же клиентского домена
- `training` — сценарии и сессии обучения, которые могут использовать контекст клиента

Целевая модель:

1. `CRM Core`
2. `Work Process Layer`
3. `AI Continuity Layer`

## 2. Слои Домена

### 2.1 CRM Core

Отвечает за реального клиента и рабочие данные:

- карточка клиента
- ПДн
- владелец клиента
- принадлежность команде
- контакты
- долги
- кредиторы
- город
- доход
- теги
- согласия
- история взаимодействий
- напоминания
- дубли
- audit trail

### 2.2 Work Process Layer

Это обязательная прослойка между реальной CRM и AI-слоем.

Она отвечает за:

- единый путь клиента
- состояние в воронке
- следующий шаг
- контроль удержания связи
- причины потери
- причины паузы
- причины отзыва согласия
- правила возврата из потерянных
- единые SLA и таймауты

Именно этот слой должен быть главным источником правды для:

- канбана
- lifecycle-графа
- статистики РОП
- отчётов методолога
- рекомендаций

### 2.3 AI Continuity Layer

Это не отдельная CRM.

Это слой сопровождения и тренировки, связанный с клиентским путём:

- AI-истории
- синтетические события
- AI-сообщения
- сюжетные последствия
- тренажёр удержания связи
- аналитика по сценариям общения

AI-слой может использовать подмножество статусов, но не должен придумывать отдельный независимый жизненный цикл клиента.

## 3. Каноническая Модель Состояний

Целевой подход: не одно поле статуса, а два уровня состояния.

### 3.1 Lifecycle Stage

Это основной путь клиента в воронке.

Канонический список:

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

Смысл этапов:

- `new` — клиент создан, первичная квалификация ещё не проведена
- `contacted` — первый контакт установлен
- `interested` — клиент проявил предметный интерес
- `consultation` — назначена или проведена консультация
- `thinking` — клиент обдумывает решение
- `consent_received` — получено согласие на следующий шаг
- `contract_signed` — договор подписан
- `documents_in_progress` — идёт сбор и проверка документов
- `case_in_progress` — клиентский кейс уже в активной работе
- `completed` — клиентский путь успешно завершён
- `lost` — путь завершён потерей клиента

### 3.2 Work State

Это служебное операционное состояние внутри lifecycle.

Канонический список:

- `active`
- `callback_scheduled`
- `waiting_client`
- `waiting_documents`
- `consent_pending`
- `paused`
- `consent_revoked`
- `duplicate_review`
- `archived`

Принцип:

- канбан строится по `lifecycle_stage`
- служебные состояния не должны быть отдельными колонками основной воронки
- `paused`, `consent_revoked`, `duplicate_review` — это не этапы продаж, а operational state

## 4. Правила Переходов

Целевой путь клиента:

`new -> contacted -> interested -> consultation -> thinking -> consent_received -> contract_signed -> documents_in_progress -> case_in_progress -> completed`

Разрешённые боковые переходы:

- любой активный этап может перейти в `lost`
- `thinking` может вернуться в `consultation`
- `consent_received` может перейти в `thinking`
- `documents_in_progress` может вернуться в `contract_signed`
- `paused` не меняет lifecycle, только временно меняет work state
- `consent_revoked` не меняет lifecycle автоматически, но блокирует дальнейшее движение до решения менеджера

## 5. Как Показывать Воронку

Основная канбан-воронка должна содержать только lifecycle stages:

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

Но визуально:

- `completed` и `lost` должны быть terminal columns
- `paused`, `consent_revoked`, `duplicate_review` не выводятся как самостоятельные pipeline columns

## 6. Lifecycle Graph

Граф модуля `Клиенты` должен быть lifecycle-графом клиента, а не force-graph оргструктуры.

Он должен показывать:

- текущий путь клиента по этапам
- фактические переходы между этапами
- дату каждого перехода
- кто выполнил действие
- связанные касания
- события согласий
- напоминания
- AI continuity events
- точки потери и возврата

Для РОП и админа отдельно нужна агрегированная transition analytics:

- `new -> contacted`
- `contacted -> interested`
- `interested -> consultation`
- `consultation -> thinking`
- `thinking -> consent_received`
- `consent_received -> contract_signed`
- `contract_signed -> documents_in_progress`
- `documents_in_progress -> case_in_progress`
- `case_in_progress -> completed`
- потери по каждому этапу

## 7. Роли И Видимость

### 7.1 Manager

- видит только своих клиентов
- видит только свои AI continuity records
- может создавать и редактировать своих клиентов
- может менять этапы и work state в рамках правил
- может работать с напоминаниями, согласиями, историей контактов

### 7.2 ROP

- видит только свою команду
- это правило должно действовать везде:
- список клиентов
- детальная карточка
- воронка
- graph/lifecycle analytics
- дубли
- экспорт
- рекомендации
- audit для своей команды

### 7.3 Admin

- видит все команды
- видит менеджеров и РОПов
- может просматривать и администрировать все клиентские записи

### 7.4 Methodologist

- read-only доступ
- видит реальную информацию и статистику
- не выполняет destructive actions
- не делает merge, delete, reassignment, export действий от имени операционного пользователя

## 8. AI Клиент И Поля Карточки

Для AI continuity layer у клиента должна быть полная training-safe карточка, синхронная с реальным клиентским контекстом.

Минимальный набор полей:

- `full_name`
- `city`
- `income`
- `debt_amount`
- `creditors`
- `tags`
- `source`
- `notes`
- `contact_history`

Если этих полей нет в AI-слое, их нужно добавить как синтетический профиль, а не как ссылку на реальные ПДн.

Принцип:

- реальный клиент хранит реальные ПДн
- AI continuity использует synthetic mirror profile
- поля должны быть семантически теми же, чтобы путь клиента ощущался единым

## 9. Готовый Справочник Причин Потери

Справочник вводится сразу как базовый controlled vocabulary.

Его можно расширять, но не заполнять свободным текстом вместо причины.

### 9.1 Группа `contact_failure`

- `no_answer`
- `wrong_number`
- `unreachable`
- `asked_not_to_call`

### 9.2 Группа `interest_loss`

- `no_interest`
- `not_relevant`
- `just_collecting_info`
- `will_solve_without_us`

### 9.3 Группа `trust_barrier`

- `no_trust`
- `needs_reviews_or_proof`
- `negative_past_experience`

### 9.4 Группа `price_barrier`

- `too_expensive`
- `no_money_now`
- `choosing_cheaper_option`

### 9.5 Группа `decision_barrier`

- `needs_time_to_think`
- `family_discussion_pending`
- `decision_postponed`

### 9.6 Группа `competition`

- `went_to_competitor`
- `stays_with_current_provider`
- `bank_or_lawyer_alternative`

### 9.7 Группа `documents_or_process`

- `not_ready_to_collect_documents`
- `process_seems_too_complex`
- `not_ready_for_formal_step`

### 9.8 Группа `compliance_or_consent`

- `consent_not_given`
- `consent_revoked`
- `does_not_want_data_processing`

### 9.9 Группа `case_mismatch`

- `not_eligible`
- `insufficient_case_value`
- `outside_target_profile`

### 9.10 Группа `operational_timeout`

- `followup_timeout`
- `documents_timeout`
- `consultation_timeout`
- `inactive_too_long`

## 10. Дубликаты И Merge Policy

Merge должен поддерживать сценарий many-to-one.

Пользователь выбирает master record.

Правила:

- interactions переносятся в master
- reminders переносятся в master
- notes не теряются, а попадают в merged history
- primary phone и primary email выбираются явно
- остальные телефоны и email становятся secondary contacts
- consent history не удаляется и не схлопывается в одну запись
- все consent records сохраняются как история
- conflict по активному consent решается через current consent marker
- duplicate record помечается как merged, а не просто soft-delete без следа

Нужна отдельная таблица merge-аудита:

- `source_client_id`
- `target_client_id`
- `merged_by`
- `merge_reason`
- `merged_at`
- `field_resolution`

## 11. Экспорт

Экспорт должен работать:

- только по выбранным клиентам
- в формате `json`
- с role-aware filtering

Правила:

- manager экспортирует только своих выбранных
- rop только выбранных в своей команде
- admin любых выбранных
- methodologist только read-only export policy, если такой экспорт разрешён продуктом отдельно

## 12. Целевые Сущности

Минимальный целевой набор:

- `client`
- `client_profile`
- `client_contact`
- `client_lifecycle_event`
- `client_work_state`
- `client_interaction`
- `client_consent`
- `client_reminder`
- `client_duplicate_candidate`
- `client_merge_log`
- `client_ai_profile`
- `client_ai_event`

## 13. Что Должно Быть Переделано В Коде

### 13.1 Backend

- разделить lifecycle stage и work state
- ввести единый DTO для `ClientDetail`
- привести stats API к одному контракту
- сделать role-aware graph data
- сделать role-aware duplicates
- переделать merge под many-to-one
- переделать export под selected ids + JSON
- выровнять AI continuity layer под общий домен клиента

### 13.2 Frontend

- переделать карточку клиента под реальный `ClientDetail`
- перестроить канбан по lifecycle
- убрать служебные состояния из колонок
- заменить network graph на lifecycle graph
- добавить формы выбора причины потери и причины отзыва согласия
- привести bulk actions к реальному API контракту

### 13.3 Data / Migrations

- добавить реальные поля БД для `income`, `city`, `tags`, `creditors`
- добавить secondary contacts
- добавить merge log
- добавить lifecycle events
- выделить current work state

## 14. Порядок Внедрения

1. Зафиксировать архитектуру и словарь статусов
2. Выровнять role model
3. Выровнять API contracts
4. Ввести новый `ClientDetail`
5. Ввести lifecycle events + work state
6. Пересобрать pipeline UI
7. Пересобрать graph UI
8. Переделать duplicates/merge
9. Переделать export
10. Встроить AI continuity как часть общего домена

## 15. Связанные Файлы Репозитория

При дальнейшей реализации первыми должны быть пересмотрены:

- `README.md`
- `apps/api/app/models/client.py`
- `apps/api/app/models/game_crm.py`
- `apps/api/app/schemas/client.py`
- `apps/api/app/api/clients.py`
- `apps/api/app/api/game_crm.py`
- `apps/api/app/services/client_service.py`
- `apps/api/app/services/game_crm_service.py`
- `apps/web/src/types/index.ts`
- `apps/web/src/app/clients/page.tsx`
- `apps/web/src/app/clients/[id]/page.tsx`
- `apps/web/src/app/clients/pipeline/page.tsx`
- `apps/web/src/app/clients/graph/page.tsx`
- `apps/web/src/app/training/crm/page.tsx`


---

## 16. TZ-4 Evolution (2026-04-27 → 2026-04-28)

> Этот раздел добавлен после серии PR'ов TZ-4 (D0..D7.7c, D7.3, B1).
> Описывает где новые сущности живут в трёхслойной модели §2.

### 16.1 Новые сущности и их слой

| Сущность | Слой | Owning service | Канонические события |
|---|---|---|---|
| `MemoryPersona` (per `lead_client_id`) | AI Continuity Layer | `services/persona_memory.py` | `persona.updated`, `persona.slot_locked` |
| `SessionPersonaSnapshot` (per `training_sessions.id`, immutable) | AI Continuity Layer | `services/persona_memory.py` (write at session start; никогда не UPDATE) | `persona.snapshot_captured`, `persona.conflict_detected` |
| `Attachment` (расширен 4 поля D1) | CRM Core | `services/attachment_pipeline.py` (единая точка входа) | 9 событий из `attachment.*` (uploaded, linked, duplicate_detected, av_passed/rejected, ocr_completed, classified, verified, rejected) |
| `LegalKnowledgeChunk` (расширен 8 полей D1) | Work Process Layer (governance) | `services/knowledge_review_policy.py` | 5 событий `knowledge_item.*` (created, updated, expired, reviewed, status_changed) |

### 16.2 Канонические писатели (AST-guarded)

Каждый из 4 классов сущностей имеет AST guard который блокирует
прямую конструкцию / запись в обход canonical service. Это
build-time invariant — нарушение валит CI.

| Сущность | Guard test | Allowed writers |
|---|---|---|
| `ClientInteraction` | `tests/test_client_domain_invariants.py` | `client_domain.py`, `client_domain_repair.py`, `crm_timeline_projector.py` |
| `Attachment` (+ 7 status/identity columns) | `tests/test_attachment_invariants.py` | `attachment_pipeline.py` |
| `MemoryPersona` / `SessionPersonaSnapshot` (+ 5 mutable persona fields) | `tests/test_persona_invariants.py` | `persona_memory.py` |
| `LegalKnowledgeChunk.knowledge_status` (+ reviewed_by/reviewed_at/expires_at) | `tests/test_knowledge_invariants.py` | `knowledge_review_policy.py` |

Plus runtime guard на `event_type`:
`client_domain.ALLOWED_EVENT_TYPES: frozenset[str]` (D1.1) — все 48
канонических event_type'ов; typo вроде `"attachements.uploaded"`
бросает `UnknownDomainEventType` на emit.

### 16.3 Conversation Policy Engine (TZ-4 §10)

Новый сервис `services/conversation_policy_engine.py` с шестью
явными проверками после каждой AI reply:

| Code | Severity | Описание |
|---|---|---|
| `too_long_for_mode` | medium | call/center > 3 sentences или chat > 5 |
| `near_repeat` | high | SequenceMatcher ratio ≥ 0.86 vs последних 5 ответов |
| `missing_next_step` | low | chat/center: нет next-step verb |
| `persona_conflict` | high | Reply противоречит SessionPersonaSnapshot |
| `asked_known_slot_again` | medium | Reply спрашивает уже подтверждённый slot |
| `unjustified_identity_change` | critical | Reply меняет address_form (вы↔ты) без обновления профиля |

Engine работает в **warn-only mode** по умолчанию. Каждое нарушение
эмитится как `conversation.policy_violation_detected` event +
WS-push'ится через notification manager. Ничего не блокируется.
Перевод в `enforce mode` (D7.2) — по env флагу
`CONVERSATION_POLICY_ENFORCE_ENABLED=true` после 7-дневного окна
телеметрии и FP rate < 5% (§12.3.1).

### 16.4 Runtime audit hook (D7.6)

`services/conversation_audit_hook.py` интегрирует engine в WS
training handler. Каждое `assistant` сообщение после save-to-DB
проходит через `audit_and_publish_assistant_reply`:

1. Загружает `SessionPersonaSnapshot` + `MemoryPersona` (если есть).
2. Запускает `engine.audit_assistant_reply` — 6 проверок.
3. Эмитит каждое violation как `DomainEvent`.
4. Если `unjustified_identity_change` — вызывает
   `persona_memory.record_conflict_attempt` (бамп
   `mutation_blocked_count` через raw UPDATE — выходит за рамки
   AST guard на ORM-write).
5. Dual WS push: durable outbox (`ws_delivery.enqueue`) + live push
   (`notifications.send_ws_notification`).

Fail-mode safe: каждый шаг изолирован try/except — audit hook
никогда не валит WS handler.

### 16.5 Admin oversight surfaces (TZ-4 §13.4.1)

| Где | Что | Файл |
|---|---|---|
| `Методология → Качество AI` (sub-tab) | Агрегаты policy violations + persona conflicts по команде/менеджеру за окно 1d/7d/30d | `web/components/dashboard/methodology/AiQualityPanel.tsx` |
| `Методология → Ревью знаний` (sub-tab) | Очередь `knowledge_status='needs_review'` + manual review action (единственный путь к `outdated`) | `web/components/dashboard/methodology/KnowledgeReviewQueue.tsx` |
| `Активность → AuditLogPanel` (сурфейс расширен) | filter "Документы" показывает `entity_type=attachments` | `web/components/dashboard/AuditLogPanel.tsx` |
| `Карточка клиента → Память клиента` | MemoryPersona snapshot + slot_locked chips + последний SessionPersonaSnapshot + event counts | `web/components/clients/ClientMemorySection.tsx` |
| `Call screen badges` | Per-session live counter for policy + persona conflicts (warn-only severity strip) | `web/components/policy/PolicyViolationCounter.tsx` + `persona/PersonaConflictBadge.tsx` |

Команда панель **намеренно не тронута** — она про people-management
(AlertPanel / WeakLinks / Behavior / Ocean / Recommendations), а
TZ-4 события — про AI craft. Семантически это разные оси, и
смешение их в одной панели создавало бы шум.

### 16.6 ClientProfile coexistence (§6.6)

В рамках TZ-4 НЕ удалена legacy `ClientProfile` модель (живёт в
`models/roleplay.py`). Правила сосуществования:

* **Identity-уровень** (full_name / gender / role_title /
  address_form): **MemoryPersona wins** для real-client сессий.
  ClientProfile в этом контексте — fallback для simulation сессий
  без CRM-привязки.
* **Behavior-уровень** (hidden_objections / trap_ids / chain_id /
  cascade_ids / breaking_point / fears / soft_spot): **ClientProfile
  wins** — это AI-character behavior, отделено от identity.
* **Нейтральные поля** (city / total_debt / creditors / income):
  MemoryPersona если presented в `confirmed_facts`, иначе
  ClientProfile.

После D7.4 cutover (отложено — нужны pilot snapshot rows в проде)
runtime будет читать identity ТОЛЬКО из SessionPersonaSnapshot для
real-client сессий, а ClientProfile.full_name / .gender станут
строго fallback'ом для simulation paths.

### 16.7 Migration history (TZ-4)

| Revision | PR | Что |
|---|---|---|
| `20260427_001` | D1 #57 | Foundation: 4 attachment column extensions, 8 LegalKnowledgeChunk extensions, MemoryPersona + SessionPersonaSnapshot tables, partial UNIQUE index на attachments, backfill |
| `20260427_002` | D2 #59 | CHECK constraint на `legal_knowledge_chunks.knowledge_status` (4 канонических значения) |
| `20260427_003` | D7.3 #69 | `attachments.domain_event_id NOT NULL` + defensive orphan repair |
| `20260427_004` | B1 #73 | `ocr_status` / `classification_status` rename to spec §7.1.1 canonical + CHECK constraints |

### 16.8 Spec drift (открытые вопросы)

См. `docs/ARCHITECTURE_AUDIT_2026_04_28.md` §"Spec drift summary"
для свежего каталога расхождений между `TZ-4 spec rev 2` и
имплементацией. Самые острые:

* §11.2.1 NBA layer 2 — `filter_safe_knowledge_refs` helper готов
  (PR #75) но callsite в `next_best_action` пока не consume legal
  knowledge (актуальный NBA — pure CRM-state-driven).
* §8.3 endpoint wording: spec говорит `mark-outdated`, имплементация
  ships `review`. Спека дешевле в правке.
* §6.3.1 `MemoryPersona.last_confirmed_at` обещает обновляться на
  каждом `lock_slot` — текущая имплементация пишет только при
  initial create.
