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

