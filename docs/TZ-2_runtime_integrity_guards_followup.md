# ТЗ-2. Runtime Integrity Для Chat, Call, Training И Center

Статус: `implementation-ready spec`

Приоритет: `P0 / runtime safety`

Связь с программой: документ 2 из 4. Должен реализовываться поверх терминов и инвариантов из [TZ-1_unified_client_domain_events.md](/Users/bubble3/Desktop/Проекты_Х/wr1/Hunter888-main/docs/TZ-1_unified_client_domain_events.md).

## 1. Цель

Сделать runtime сессий единым, предсказуемым и non-breaking, чтобы `chat`, `call`, `training` и `center` не расходились по бизнес-эффектам в зависимости от точки входа, транспорта или частной ветки кода.

Результат этого ТЗ:

- у любой рабочей сессии есть канонический `mode`, `runtime_type`, `terminal_outcome` и `lead_client_id` при необходимости;
- старт и завершение сессии проходят через единые guard-правила;
- `REST` и `WS` перестают порождать разные побочные эффекты;
- любой terminal path гарантированно создает правильные события, обновляет CRM и создает `follow-up`, если это нужно;
- `Center` и `multi-call training` перестают жить как набор исключений.

## 2. Подтвержденная Текущая Проблема

### 2.1 Что реально сломано

1. Старт и завершение сессий уже частично валидируются, но не централизованы.
2. `mode integrity` есть, но остается распределенной между frontend, API и call-page.
3. Terminal logic и follow-up logic зависят от того, через какой path завершили сессию.
4. `Center` выделен только частично: terminal outcome guard уже есть, но полноценной state machine и канонического terminal event пока нет.
5. `training` смешивает учебный runtime и реальный клиентский runtime, что создает риск загрязнения CRM и аналитики.

### 2.2 Где это видно в коде

- `apps/api/app/api/training.py`
- `apps/api/app/ws/training.py`
- `apps/api/app/services/session_state.py`
- `apps/api/app/services/crm_followup.py`
- `apps/api/app/services/session_manager.py`
- `apps/web/src/app/clients/[id]/page.tsx`
- `apps/web/src/app/center/page.tsx`
- `apps/web/src/app/training/[id]/call/page.tsx`

### 2.3 Верифицированные расхождения

1. В `apps/api/app/api/training.py` старт сессии уже блокируется через `required_profile_missing`, а `mode` нормализуется и частично валидируется.
2. В `apps/api/app/services/session_state.py` `center` уже требует terminal outcome из фиксированного набора.
3. В `apps/api/app/services/crm_followup.py` follow-up создается эвристически из `call_outcome` и эмоций, а не из канонического runtime outcome contract.
4. В `apps/api/app/ws/training.py` после завершения сессии создается `ClientInteraction` для CRM timeline, а в `apps/api/app/api/training.py` такого симметричного канонического timeline path нет.
5. Во frontend `clients/[id]/page.tsx` и `center/page.tsx` уже передают `custom_session_mode`, но `training/[id]/call/page.tsx` все еще работает в режиме compatibility/fail-open и сам лечит несогласованный shape ответа.

### 2.4 Root Cause

Root cause не в том, что “не хватает нескольких if”. Root cause в том, что runtime semantics не выделены в единый контракт:

- нет единой модели рабочего `SessionRuntime`;
- нет одного канонического `terminal path`;
- guard-условия размазаны по слоям;
- follow-up является побочным эффектом эвристики, а не частью runtime contract;
- `REST` и `WS` конкурируют как два частично независимых orchestrator-а.

## 3. In Scope

В рамках ТЗ-2 реализуются:

- каноническая runtime-модель `Session`;
- канонические `mode`, `runtime_type`, `source`, `terminal_outcome`;
- единый `start-session contract`;
- единый `end-session contract`;
- guard engine;
- mode integrity и profile/lead completeness guards;
- разграничение `training.simulation` и `training.real_case`;
- state machine для `multi-call` и `center`;
- канонический `TaskFollowUp` creation policy;
- обязательные runtime events и CRM sync;
- observability, e2e и rollback-safe migration.

## 4. Out Of Scope

В рамках ТЗ-2 не реализуются полностью:

- финальная миграция клиентского домена и projector-модели из ТЗ-1;
- сценарное versioning и constructor hardening из ТЗ-3;
- attachment pipeline и persona/knowledge governance из ТЗ-4.

Но ТЗ-2 обязано работать так, чтобы после внедрения ТЗ-3 и ТЗ-4 runtime не пришлось переписывать заново.

## 5. Архитектурные Решения, Которые Считаются Зафиксированными

1. `Center` является отдельным runtime-режимом, а не просто `call` с особыми флагами.
2. `training` делится на `simulation` и `real_case`.
3. Только `real_case` имеет право порождать реальные CRM effects.
4. Пользователь со статусом `AUTHENTICATED_BUT_INCOMPLETE` может видеть read-only и onboarding экраны, но не может стартовать рабочие режимы.
5. Любое завершение рабочей сессии обязано завершаться через один канонический runtime finalizer, независимо от того, вызвано оно по `REST`, `WS`, `hangup`, timeout или explicit user action.

## 6. Целевая Каноническая Runtime-Модель

### 6.1 Session

Минимальные обязательные поля:

- `id`
- `user_id`
- `lead_client_id`
- `scenario_id`
- `scenario_version_id`
- `mode`
- `runtime_type`
- `source`
- `status`
- `started_at`
- `ended_at`
- `terminal_outcome`
- `completion_reason`
- `entry_channel`
- `call_attempt_no`
- `parent_session_id`
- `custom_params`

### 6.2 Mode

Разрешенные значения:

- `chat`
- `call`
- `center`

### 6.3 Runtime Type

Разрешенные значения:

- `training_simulation`
- `training_real_case`
- `crm_call`
- `crm_chat`
- `center_single_call`

### 6.4 Status

Разрешенные значения:

- `starting`
- `active`
- `ending`
- `completed`
- `failed`
- `cancelled`

### 6.5 Terminal Outcome

Outcome не может быть свободным текстом.

Общий нормализованный каталог:

- `deal_agreed`
- `deal_not_agreed`
- `continue_next_call`
- `needs_followup`
- `documents_required`
- `callback_requested`
- `client_unreachable`
- `user_cancelled`
- `timeout`
- `error`

### 6.6 Completion Reason

Отдельное поле, не равное outcome:

- `explicit_end`
- `client_hangup`
- `operator_hangup`
- `timeout`
- `guard_block`
- `system_failure`
- `redirected`

## 7. Runtime Invariants

1. Любая сессия имеет валидный `mode`.
2. Любая рабочая сессия имеет валидный `runtime_type`.
3. `crm_call`, `crm_chat`, `training_real_case` и `center_single_call` не могут существовать без связанного клиента.
4. `training_simulation` не создает реальных CRM-проекций.
5. Ни один terminal path не может завершить рабочую сессию без нормализованного outcome, если этот outcome обязателен для данного режима.
6. `REST` и `WS` обязаны вызывать один и тот же finalizer.
7. `follow-up` создается не из случайных side effects, а из outcome policy.
8. Любой terminal event обязан быть idempotent.
9. Повторный вызов завершения сессии не должен создавать второй follow-up, вторую timeline запись или второй terminal event.

## 8. Guard Engine

### 8.1 Обязательные Guards На Старте

- `profile_complete_guard`
- `mode_integrity_guard`
- `runtime_type_guard`
- `lead_client_presence_guard`
- `lead_client_access_guard`
- `scenario_version_guard`
- `session_uniqueness_guard`

### 8.2 Правила

#### profile_complete_guard

Блокирует старт:

- `crm_call`
- `crm_chat`
- `training_real_case`
- `center_single_call`

Не блокирует:

- onboarding
- help
- read-only views
- `training_simulation`, если продуктово это разрешено

#### mode_integrity_guard

- CRM start из карточки клиента обязан явно передавать `call` или `chat`;
- `center` обязан явно стартовать как `center`;
- backend не имеет права “догадываться” о рабочем `mode`, если есть `lead_client_id` и рабочий runtime;
- отсутствие `mode` в рабочем контексте = hard error, не fallback.

#### lead_client_presence_guard

Обязателен для:

- `crm_call`
- `crm_chat`
- `training_real_case`
- `center_single_call`

### 8.3 Обязательные Guards На Завершении

- `terminal_outcome_required_guard`
- `runtime_status_guard`
- `idempotent_finalization_guard`
- `projection_safe_commit_guard`
- `followup_policy_guard`

#### terminal_outcome_required_guard

Для `center_single_call` outcome обязателен всегда и должен быть одним из:

- `deal_agreed`
- `deal_not_agreed`
- `continue_next_call`

Для `crm_call`, `crm_chat` и `training_real_case` outcome обязателен, если runtime порождает бизнес-эффекты.

Для `training_simulation` допускается более мягкий terminal contract, но сессия все равно должна завершаться через нормализованный финализатор.

## 9. Канонический Start Contract

### 9.1 Вход

Любой старт сессии обязан явно сформировать:

- `mode`
- `runtime_type`
- `source`
- `scenario_id`
- `scenario_version_id` или policy его резолва
- `lead_client_id`, если нужен рабочий runtime

### 9.2 Mapping Правила

#### CRM Card Start

Из `clients/[id]/page.tsx`:

- voice -> `mode=call`, `runtime_type=crm_call`, `source=crm_voice`
- chat -> `mode=chat`, `runtime_type=crm_chat`, `source=crm_chat`

#### Center Start

Из `center/page.tsx`:

- `mode=center`
- `runtime_type=center_single_call`
- `source=center`

#### Training Start

Из training flow:

- без реального клиента -> `runtime_type=training_simulation`
- с реальным клиентом -> `runtime_type=training_real_case`

### 9.3 Запрет На Fallback

Если старт идет из рабочего режима, backend не должен silently перекидывать его в `chat` или в другой тип runtime. Ошибка контракта должна всплывать сразу.

## 10. Канонический End Contract

### 10.1 Общее Правило

И `POST /training/sessions/{id}/end`, и `WS session.end`, и автоматический hangup, и timeout обязаны завершаться через один сервис:

- `runtime_finalizer.finalize_session(...)`

### 10.2 Ответственность Финализатора

Финализатор обязан:

1. Валидировать guard-условия завершения.
2. Нормализовать `terminal_outcome`.
3. Закрыть сессию атомарно.
4. Сохранить runtime summary.
5. Создать канонический terminal `DomainEvent`.
6. Передать данные в CRM projection path, если runtime боевой.
7. Создать `TaskFollowUp`, если этого требует policy.
8. Выполнить idempotent cleanup.

### 10.3 Что запрещено

Запрещено, чтобы:

- `REST` создавал один набор побочных эффектов, а `WS` другой;
- timeline писался напрямую только из WS ветки;
- follow-up создавался только в одной ветке;
- session status закрывался в одном месте, а terminal event рождался в другом вне общей транзакционной схемы.

## 11. Outcome Policy

### 11.1 Center Single Call

Канонические исходы:

- `deal_agreed`
- `deal_not_agreed`
- `continue_next_call`

Политика:

- `deal_agreed` -> terminal event + CRM update + optional close task
- `deal_not_agreed` -> terminal event + CRM close reason
- `continue_next_call` -> terminal event + mandatory `TaskFollowUp`

### 11.2 Multi-Call Flow

Канонические рабочие состояния процесса:

- `stage1_first_contact`
- `stage2_qualification`
- `followup_scheduled`
- `stage3_return_call`
- `stage4_closing`
- `stage5_finalize`
- `crm_transferred`

Канонические рабочие исходы:

- `enough_data`
- `client_requests_later`
- `need_documents_or_time`
- `qualified_and_ready`
- `objections_resolved`
- `agreement_or_reject`

### 11.3 Policy Mapping

#### `client_requests_later`

- создать `TaskFollowUp`
- обновить CRM next action
- не закрывать кейс

#### `need_documents_or_time`

- создать `TaskFollowUp`
- перевести `work_state` в `waiting_documents` или `waiting_client`
- сохранить missing-items payload

#### `qualified_and_ready`

- обновить lifecycle/stage
- подготовить следующий звонок или transfer

#### `agreement_or_reject`

- обязательно зафиксировать финальный результат в CRM

## 12. Follow-Up Как Канонический Runtime Effect

### 12.1 Что меняется

Сейчас `crm_followup.py` использует гибрид outcome/emotion эвристик. Это допустимо только как temporary compatibility layer.

Целевое правило:

`terminal_outcome + runtime_type + current_client_state -> followup_policy -> TaskFollowUp`

### 12.2 TaskFollowUp

Обязательные поля:

- `id`
- `lead_client_id`
- `session_id`
- `reason`
- `channel`
- `due_at`
- `status`
- `auto_generated`
- `domain_event_id`

### 12.3 Инварианты

1. Один terminal event не может создать два одинаковых follow-up.
2. Follow-up должен ссылаться на `domain_event_id`.
3. Если follow-up обязателен, отсутствие follow-up после terminal event считается runtime defect.

## 13. CRM Sync Rules

### 13.1 Боевые Runtime Paths

Для `crm_call`, `crm_chat`, `training_real_case`, `center_single_call` после завершения сессии обязаны появиться:

- terminal `DomainEvent`
- CRM timeline projection
- если нужно, `TaskFollowUp`
- обновление карточки клиента

### 13.2 Simulation Paths

Для `training_simulation`:

- нет реальной CRM записи;
- нет follow-up на реального клиента;
- есть только training/report/domain events уровня симуляции.

## 14. Non-Breaking Migration Strategy

### Фаза 0. Freeze И Inventory

- перечислить все существующие end-paths;
- перечислить все места прямой записи в CRM timeline;
- перечислить все места создания follow-up/reminder после сессии.

### Фаза 1. Introduce Runtime Finalizer

Создать единый runtime finalizer без удаления текущих entrypoints.

На этой фазе:

- `REST` и `WS` продолжают существовать;
- но оба обязаны делегировать финализацию одному сервису.

### Фаза 2. Dual-Path Verification

Сравнить output старых веток и нового finalizer-а по:

- статусу сессии
- terminal outcome
- CRM effect
- follow-up creation
- event emission

### Фаза 3. Cutover

После parity:

- убрать расхождения между `REST` и `WS`;
- оставить один runtime finalization contract;
- compatibility wrappers допустимы только как thin adapters.

### Фаза 4. Cleanup

- убрать дублирующий timeline write;
- убрать эвристики, которые дублируют каноническую policy;
- зафиксировать contract tests.

## 15. File-Level Implementation Plan

### 15.1 Новые сервисы

Создать:

- `apps/api/app/services/runtime_guard_engine.py`
- `apps/api/app/services/runtime_finalizer.py`
- `apps/api/app/services/runtime_outcome_policy.py`
- `apps/api/app/services/followup_policy.py`

Допускается объединение `runtime_outcome_policy` и `followup_policy` на первом шаге, если это уменьшает сложность, но `runtime_finalizer` и `runtime_guard_engine` должны остаться отдельными.

> **Note (2026-04-26 implementation status).** На момент реализации факт расхождения с этим именованием:
>
> | Спека (§15.1) | Реальный файл | Статус |
> |---|---|---|
> | `runtime_outcome_policy.py` | `apps/api/app/services/completion_policy.py` | покрывает всю outcome/finalize policy для training + PvP |
> | `followup_policy.py` | `apps/api/app/services/task_followup_policy.py` | TaskFollowUp создание + idempotency |
> | `runtime_guard_engine.py` | `apps/api/app/services/runtime_guard_engine.py` | как в спеке |
> | `runtime_finalizer.py` | `apps/api/app/services/runtime_finalizer.py` | как в спеке |
>
> Текущие имена выбраны как более информативные (`completion_policy` отражает консолидацию 7 терминальных путей; `task_followup_policy` явно отделяет канонический `TaskFollowUp` от legacy `ManagerReminder`). Переименование не требуется; при будущих ссылках в коде использовать фактические имена.

### 15.2 Обновить backend entrypoints

- `apps/api/app/api/training.py`
- `apps/api/app/ws/training.py`
- `apps/api/app/services/session_state.py`
- `apps/api/app/services/crm_followup.py`
- `apps/api/app/services/session_manager.py`

Что нужно сделать:

- вынести канонический mapping `mode/runtime_type/source`;
- заменить локальные terminal side effects вызовом `runtime_finalizer`;
- оставить current API/WS shape максимально совместимым до cutover;
- запретить новые direct CRM effects вне finalizer-а.

### 15.3 Обновить frontend start paths

- `apps/web/src/app/clients/[id]/page.tsx`
- `apps/web/src/app/center/page.tsx`
- `apps/web/src/app/training/[id]/call/page.tsx`
- `apps/web/src/types/index.ts`
- `apps/web/src/types/api.ts`

Нужно:

- явно работать с `mode` и `runtime_type`;
- убрать неявные fallback semantics из start contracts;
- сохранить временную fail-open совместимость только на read-side, пока backend не стабилизирован;
- после стабилизации перевести call-page на strict runtime contract.

## 16. Data Contract Requirements

### 16.1 Start Session Request

Минимальная структура:

```json
{
  "scenario_id": "uuid",
  "lead_client_id": "uuid-or-null",
  "mode": "chat|call|center",
  "runtime_type": "training_simulation|training_real_case|crm_call|crm_chat|center_single_call",
  "source": "string"
}
```

На переходный период допускается принимать legacy `real_client_id` и `custom_session_mode`, но backend обязан нормализовать их в канонические поля.

### 16.2 End Session Request

Минимальная структура:

```json
{
  "terminal_outcome": "deal_agreed",
  "completion_reason": "explicit_end"
}
```

На переходный период допускается принимать legacy `outcome` и `result`, но финализатор обязан нормализовать их до канонического каталога.

## 17. Тестовый Пакет

### 17.1 Unit Tests

- guard engine корректно блокирует неполный профиль;
- `crm_call` без mode не стартует;
- `center_single_call` не завершается без валидного outcome;
- finalizer идемпотентен;
- follow-up policy не создает дублей.

### 17.2 Contract Tests

- `REST end` и `WS end` создают одинаковый terminal effect;
- `training_real_case` и `training_simulation` различаются только там, где должны;
- CRM card start всегда порождает правильный `mode/runtime_type`;
- center start всегда порождает `mode=center`, `runtime_type=center_single_call`.

### 17.3 E2E Tests

Минимальные сценарии:

1. `crm_call` стартует из CRM, корректно доходит до завершения и пишет CRM timeline.
2. `crm_chat` стартует из CRM, завершает сессию и не теряет mode integrity.
3. `center_single_call` завершается каждым из 3 допустимых исходов.
4. `training_real_case` создает CRM effect и follow-up при нужном исходе.
5. `training_simulation` не создает CRM effect.
6. Повторный `end_session` не создает дублей.
7. `client_hangup` и explicit end приводят к одному каноническому finalization output.

## 18. Observability

Обязательные метрики и алерты:

- число start attempts по `mode/runtime_type/source`;
- число blocked starts по guard reason;
- число terminal events по outcome;
- mismatch `REST vs WS finalizer parity`;
- число сессий без terminal outcome;
- число required follow-up without created task;
- число CRM runtime sessions without CRM projection;
- latency финализатора;
- число duplicate end attempts.

## 19. Rollback И Safe Deployment

### Rollback

Если новый finalizer дает некорректные побочные эффекты:

- старые entrypoints остаются adapter-ами и не удаляются до подтверждения parity;
- feature flag отключает новый write/read path;
- terminal events продолжают журналироваться;
- повторная обработка выполняется через idempotent replay.

### Safe Deployment

Нельзя выкатывать cutover, пока не выполнены одновременно:

- parity `REST vs WS`;
- parity CRM effects;
- parity follow-up creation;
- e2e на `crm_call`, `center`, `training_real_case`;
- smoke test на повторное завершение.

## 20. Риски

1. Команда оставит “временные” специальные ветки для `center`, и они снова станут вторым runtime.
2. Будет смешан `training_simulation` и `training_real_case`, что испортит CRM и аналитику.
3. Follow-up останется частично эвристическим и начнет зависеть от эмоции вместо outcome contract.
4. Frontend сохранит fail-open semantics дольше, чем допустимо, и будет скрывать backend drift.
5. Новый finalizer будет добавлен рядом со старой логикой, а не станет единственным местом финализации.

## 21. Definition Of Done

ТЗ-2 считается завершенным только если:

- существует единый `runtime_finalizer`;
- существует `runtime_guard_engine`;
- `REST` и `WS` используют один finalization contract;
- `center` имеет строгий terminal outcome contract;
- `crm_call`, `crm_chat`, `training_real_case`, `training_simulation` и `center_single_call` различаются канонически;
- follow-up создается policy-driven и idempotent;
- боевые runtime paths всегда пишут CRM effects;
- simulation paths не пишут CRM effects;
- есть parity-report и e2e tests;
- observability покрывает blocked starts, terminal outcomes, follow-up gaps и finalizer parity.

## 22. Deliverables

- runtime guard engine;
- runtime finalizer;
- outcome/follow-up policy services;
- обновленные API/WS entrypoints;
- обновленные frontend start contracts;
- contract/e2e tests;
- dashboards и alerts;
- migration notes и cutover checklist.

## 23. Prompt Для Coding Agent

Используй этот документ как жесткий runtime contract. Не исправляй `REST` и `WS` по отдельности, не оставляй отдельные direct writes в CRM timeline и не добавляй новые follow-up side effects вне канонического finalizer-а.

Сначала введи `runtime_guard_engine` и `runtime_finalizer`, затем переведи на них `api/training.py` и `ws/training.py`, затем зафиксируй policy для `center`, `crm_call`, `crm_chat`, `training_real_case` и `training_simulation`. Любое место, где рабочая сессия может стартовать или завершиться без канонического `mode`, `runtime_type`, `terminal_outcome` и idempotent business effects, считается незавершенной реализацией ТЗ.
