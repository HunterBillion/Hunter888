# ТЗ ДЛЯ ФРОНТЕНДА — ROLEPLAY SYSTEM v2.0

> **Статус бэкенда:** Полностью реализован и протестирован.
> **Дата:** 2026-03-18
> **Версия:** 2.0

---

## НОВЫЕ API ENDPOINTS (бэкенд готов)

### Существующие (работают)

| Метод | URL | Описание |
|---|---|---|
| POST | `/api/auth/login` | Авторизация → access + refresh |
| POST | `/api/auth/register` | Регистрация |
| POST | `/api/auth/refresh` | Обновление токена |
| POST | `/api/auth/logout` | Выход (blacklist в Redis) |
| GET | `/api/auth/me` | Текущий пользователь |
| GET | `/api/scenarios/` | Список сценариев (8 шт) |
| GET | `/api/scenarios/{id}` | **НОВЫЙ:** Детали + character + script + checkpoints |
| POST | `/api/training/sessions` | Создать сессию |
| GET | `/api/training/sessions/{id}` | Результаты сессии + messages + scoring |
| POST | `/api/training/sessions/{id}/end` | Завершить + скоринг + AI-рекомендации |
| GET | `/api/training/history` | История тренировок |
| POST | `/api/training/assign` | **НОВЫЙ:** РОП назначает тренировку |
| GET | `/api/training/assigned` | **НОВЫЙ:** Мои назначенные тренировки |
| GET | `/api/gamification/me/progress` | XP, уровень, стрик, ачивки |
| GET | `/api/gamification/leaderboard?period=week` | Лидерборд |
| POST | `/api/users/me/preferences` | **НОВЫЙ:** Сохранить настройки онбординга |
| GET | `/api/users/me/team-stats` | **НОВЫЙ:** РОП — статистика команды |
| GET | `/api/consent/status` | Статус согласия |
| POST | `/api/consent/` | Принять согласие |
| WS | `/ws/training` | WebSocket тренировка |

---

## БЛОК 1: CRM-КАРТОЧКА КЛИЕНТА (НОВЫЙ ЭКРАН)

### Где показывать
Между выбором сценария и началом тренировки. Менеджер видит карточку, читает, готовится, нажимает "Начать".

### Данные от бэкенда
При `session.start` бэкенд вернёт расширенный ответ:

```json
{
  "type": "session.started",
  "data": {
    "session_id": "uuid",
    "character_name": "Алексей Михайлов",
    "initial_emotion": "cold",
    "scenario_title": "Холодный звонок — Скептик",
    "client_card": {
      "full_name": "Алексей Михайлов",
      "age": 42,
      "gender": "male",
      "city": "Краснодар",
      "profession": "Владелец автосервиса (закрыт)",
      "lead_source": "website_form",
      "lead_source_label": "Заявка с сайта",
      "total_debt": 2100000,
      "creditors": [
        {"name": "Сбербанк", "amount": 1400000},
        {"name": "ФНС", "amount": 400000},
        {"name": "МФО Займер", "amount": 300000}
      ],
      "income": 45000,
      "income_type": "gray",
      "property": [
        {"type": "Квартира", "status": "единственная"},
        {"type": "Автомобиль", "status": "оценка ~600К"}
      ],
      "call_history": [
        {"date": "2026-03-15", "note": "Звонили, не дозвонились"},
        {"date": "2026-03-12", "note": "Оставил заявку на сайте"}
      ],
      "crm_notes": "Интересовался стоимостью, бросил форму на этапе долга"
    }
  }
}
```

### Макет CRM-карточки

```
┌────────────────────────────────────────────────────┐
│            КАРТОЧКА КЛИЕНТА                        │
│                                                    │
│  👤 Алексей Михайлов, 42 года                      │
│  📍 Краснодар                                      │
│  💼 Владелец автосервиса (закрыт)                  │
│  📱 Источник: Заявка с сайта (3 дня назад)         │
│                                                    │
│  ─── ФИНАНСЫ ───                                   │
│  💰 Долг: 2 100 000 ₽                              │
│  📊 Сбербанк: 1.4М | ФНС: 400К | МФО: 300К       │
│  💳 Доход: ~45К (серый)                             │
│  🏠 Квартира (единств.) | Авто (~600К)             │
│                                                    │
│  ─── ИСТОРИЯ ───                                   │
│  📋 15.03 — Не дозвонились                         │
│  📋 12.03 — Заявка с сайта                         │
│  📝 "Интересовался стоимостью"                      │
│                                                    │
│  ⚠️ Психотип, страхи и ловушки СКРЫТЫ              │
│     Вы узнаете их в процессе разговора              │
│                                                    │
│  [🎤 НАЧАТЬ ТРЕНИРОВКУ]  [← НАЗАД]                 │
└────────────────────────────────────────────────────┘
```

### Компонент
- Файл: `src/components/training/ClientCard.tsx`
- Props: `clientCard: ClientCardData`
- Стиль: glass morphism, тема VibeHunter
- Анимация: fade-in при появлении, числа долга с counter-up эффектом
- Адаптивность: mobile-first

---

## БЛОК 2: РАСШИРЕННЫЙ ЭКРАН ТРЕНИРОВКИ

### Постепенное раскрытие информации

| Время | Что появляется | Компонент | Анимация |
|---|---|---|---|
| 0 мин | CRM-карточка (свёрнутая) | `ClientCardMini.tsx` | Slide-in сверху |
| 0-1 мин | Только чат + аватар + микрофон | Существующие | — |
| 1 мин | Hints в чате: "Категория возражения: доверие" | `ObjectionHint.tsx` | Fade-in, пульс |
| 3 мин | VibeMeter активируется | `VibeMeter.tsx` | Scale-in |
| 5 мин | ScriptAdherence с подсказками | `ScriptAdherence.tsx` | Slide-in справа |
| 5+ мин | TalkListenRatio | `TalkListenRatio.tsx` | Fade-in |

### Новый WS-тип сообщений: `trap.detected`

```json
{
  "type": "trap.detected",
  "data": {
    "trap_name": "Запрос 100% гарантий",
    "caught": true,
    "bonus": 3,
    "message": "Вы правильно не дали 100% гарантию"
  }
}
```

Или если менеджер попался:

```json
{
  "type": "trap.detected",
  "data": {
    "trap_name": "Запрос 100% гарантий",
    "caught": false,
    "penalty": -5,
    "message": "Вы пообещали 100% гарантию — это ложное обещание"
  }
}
```

### Компонент TrapNotification
- Файл: `src/components/training/TrapNotification.tsx`
- Появляется как toast снизу
- Зелёный если caught=true, красный если false
- Framer Motion: slide-up + fade-out через 5 сек

---

## БЛОК 3: РАСШИРЕННЫЙ ЭКРАН РЕЗУЛЬТАТОВ

### Новые секции в результатах

```json
{
  "session": { "...existing..." },
  "messages": [ "...existing..." ],
  "score_breakdown": {
    "script_adherence": { "raw_score": 73.3, "checkpoints": [...] },
    "objection_handling": { "heard": true, "acknowledged": true, "...": "..." },
    "communication": { "empathy_detected": true, "polite_markers": 3 },
    "anti_patterns": { "detected": [] },
    "result": { "consultation_agreed": true, "meeting_scheduled": false }
  },
  "feedback_text": "1. Работа с ценой: используйте технику 'разбивка по месяцам'...",
  "trap_results": [
    {"name": "Запрос 100% гарантий", "caught": true, "bonus": 3},
    {"name": "Бесплатная консультация", "caught": false, "penalty": -3}
  ],
  "soft_skills": {
    "avg_response_time_sec": 4.2,
    "talk_listen_ratio": 0.45,
    "name_usage_count": 3,
    "interruptions": 1,
    "avg_message_length": 87
  },
  "client_card": { "...full card including hidden data..." }
}
```

### Макет экрана результатов

```
┌────────────────────────────────────────────────────┐
│          РЕЗУЛЬТАТЫ СЕССИИ                         │
│                                                    │
│  ОБЩИЙ БАЛЛ: 74/100  ★★★☆☆                        │
│  XP: +198  |  Уровень: 12 (до 13: 340 XP)        │
│                                                    │
│  ═══ 5 СЛОЁВ СКОРИНГА ═══                         │
│  [PentagramChart — уже есть]                       │
│                                                    │
│  1. Скрипт (22/30)                                 │
│     ✅ Приветствие ✅ Квалификация ⚠️ Презентация   │
│     ❌ Возражения ✅ Закрытие                       │
│                                                    │
│  2. Возражения (18/25) [уже есть]                  │
│  3. Коммуникация (16/20) [уже есть]                │
│                                                    │
│  4. Антипаттерны (-3)                              │
│     ⚠️ Мин 4:12: "Мы гарантируем результат"       │
│     Лучше: "Статистика — 97%"                      │
│                                                    │
│  5. Результат (8/10) [уже есть]                    │
│                                                    │
│  ═══ ЛОВУШКИ (НОВЫЙ БЛОК) ═══                     │
│  ✅ Запрос гарантий → +3                           │
│  ❌ Бесплатная консультация → -3                   │
│                                                    │
│  ═══ МЯГКИЕ НАВЫКИ (НОВЫЙ БЛОК) ═══              │
│  Скорость ответа: 4.2 сек ✅                       │
│  Talk/Listen: 45%/55% ✅                           │
│  Имя клиента: 3 раза ✅                            │
│  Перебивания: 1 ⚠️                                 │
│                                                    │
│  ═══ ЭМОЦИОНАЛЬНЫЙ ПУТЬ ═══                       │
│  [EmotionTimeline — уже есть, расширить]           │
│  cold──→skeptical──→warming──→open (не deal)       │
│  0:00    1:30        3:45      5:20                │
│                                                    │
│  ═══ AI-РЕКОМЕНДАЦИИ ═══                          │
│  [feedback_text — markdown рендер]                 │
│  1. Работа с ценой: "разбивка по месяцам"         │
│  2. Пауза 2-3 сек после возражения                │
│  3. Конкретная дата встречи обязательна            │
│                                                    │
│  ═══ РАСКРЫТИЕ КЛИЕНТА (НОВЫЙ БЛОК) ═══          │
│  Теперь вы знаете:                                 │
│  Психотип: Скептик-прагматик                      │
│  Страхи: субсидиарка, потеря авто                  │
│  Мягкая точка: дети (не использовали!)             │
│  Точка слома: конкретный расчёт экономии           │
│                                                    │
│  [🔄 ПОВТОРИТЬ] [📊 ИСТОРИЯ] [➡️ СЛЕДУЮЩАЯ]       │
└────────────────────────────────────────────────────┘
```

### Новые компоненты

| Компонент | Файл | Описание |
|---|---|---|
| `TrapResults.tsx` | `components/results/` | Список ловушек: caught ✅ / failed ❌, бонус/штраф |
| `SoftSkillsCard.tsx` | `components/results/` | 5 метрик с прогресс-барами |
| `ClientReveal.tsx` | `components/results/` | Раскрытие скрытых данных клиента |
| `AIRecommendations.tsx` | `components/results/` | Markdown-рендер AI советов |
| `CheckpointProgress.tsx` | `components/results/` | Горизонтальный таймлайн чекпоинтов |

---

## БЛОК 4: ВЫБОР СЦЕНАРИЯ (РАСШИРЕННЫЙ)

### Данные от API

`GET /api/scenarios/` возвращает:
```json
[
  {"id": "uuid", "title": "Холодный звонок — Скептик", "description": "...", "scenario_type": "cold_call", "difficulty": 5, "estimated_duration_minutes": 10},
  {"id": "uuid", "title": "Дожим — «Подумаю и перезвоню»", "scenario_type": "warm_call", "difficulty": 5, ...},
  ...
]
```

### Макет каталога

```
┌────────────────────────────────────────────────────┐
│          ВЫБОР ТРЕНИРОВКИ                          │
│                                                    │
│  [🎯 Быстрая] [📋 Каталог] [📌 Назначенные]      │
│                                                    │
│  ─── ФИЛЬТРЫ ───                                   │
│  Тип: [Все] [Cold] [Warm] [Objection]             │
│  Сложность: [1-3] [4-6] [7-10]                    │
│                                                    │
│  ─── СЦЕНАРИИ ───                                  │
│                                                    │
│  ┌──────────────────────┐ ┌──────────────────────┐ │
│  │ ❄️ Холодный — Скептик│ │ ❄️ Холодный — Тревож.│ │
│  │ ★★★★★☆☆☆☆☆ (5/10)   │ │ ★★★☆☆☆☆☆☆☆ (3/10)   │ │
│  │ ~10 мин | cold_call  │ │ ~10 мин | cold_call  │ │
│  │ [НАЧАТЬ]             │ │ [НАЧАТЬ]             │ │
│  └──────────────────────┘ └──────────────────────┘ │
│                                                    │
│  ┌──────────────────────┐ ┌──────────────────────┐ │
│  │ 🔥 Холодный — Агресс.│ │ 💤 Холодный — Апатич.│ │
│  │ ★★★★★★★★☆☆ (8/10)   │ │ ★★★★☆☆☆☆☆☆ (4/10)   │ │
│  │ ~10 мин | cold_call  │ │ ~12 мин | cold_call  │ │
│  │ [НАЧАТЬ]             │ │ [НАЧАТЬ]             │ │
│  └──────────────────────┘ └──────────────────────┘ │
│                                                    │
│  ... ещё 4 карточки                                │
└────────────────────────────────────────────────────┘
```

### Компонент
- Файл: `src/components/training/ScenarioCard.tsx`
- Props: `scenario: ScenarioResponse, onSelect: (id) => void`
- Иконки по типу: ❄️ cold, 🔥 warm, ⚔️ objection
- Сложность: звёздочки или цветовая шкала

---

## БЛОК 5: НАЗНАЧЕННЫЕ ТРЕНИРОВКИ

### API
`GET /api/training/assigned` → список назначенных РОПом

```json
[
  {
    "id": "uuid",
    "scenario_id": "uuid",
    "scenario_title": "Холодный звонок — Агрессивный должник",
    "assigned_by": "uuid",
    "deadline": "2026-03-25T00:00:00",
    "created_at": "2026-03-18T12:00:00"
  }
]
```

### Где показывать
- На `/dashboard` — бейдж "3 назначенных"
- На `/training` — вкладка "Назначенные" с дедлайнами
- Если есть просроченные — красный бейдж

---

## БЛОК 6: DASHBOARD — РАСШИРЕННЫЙ

### Новые секции

```
┌────────────────────────────────────────────────────┐
│                   DASHBOARD                        │
│                                                    │
│  ─── МОЙ ПРОГРЕСС ───                             │
│  [XPBar] Уровень 12 — Старший менеджер             │
│  [StreakCounter] 🔥 5 дней подряд                  │
│  [AchievementToast] Новая ачивка!                  │
│                                                    │
│  ─── БЫСТРЫЕ ДЕЙСТВИЯ ───                          │
│  [🎯 Быстрая тренировка]                           │
│  [📋 Выбрать сценарий]                             │
│  [📌 Назначенные (3)] ← бейдж                     │
│                                                    │
│  ─── СТАТИСТИКА ───                                │
│  Всего сессий: 23                                  │
│  Средний балл: 72.4                                │
│  Лучший результат: 91                              │
│  Сессий на этой неделе: 4                          │
│                                                    │
│  ─── СЛАБЫЕ МЕСТА ─── (НОВЫЙ)                     │
│  ⚠️ Работа с агрессивными: avg 54                  │
│  ⚠️ Закрытие на встречу: 40% чекпоинтов            │
│  💡 Рекомендация: потренируйте возражения           │
│                                                    │
│  ─── ЕСЛИ РОП/ADMIN ─── (НОВЫЙ)                   │
│  Команда: Отдел продаж                             │
│  Участников: 4 | Активных: 4                      │
│  Сессий за неделю: 12                              │
│  Лучший: Иван Петров (avg 78)                     │
│  [📊 Подробная статистика команды]                  │
└────────────────────────────────────────────────────┘
```

---

## БЛОК 7: ТЕСТОВЫЕ ПОЛЬЗОВАТЕЛИ ДЛЯ РАЗРАБОТКИ

| Email | Пароль | Роль | Команда |
|---|---|---|---|
| admin@trainer.local | Adm1n!2024 | admin | Отдел продаж |
| rop1@trainer.local | Rop1!pass | rop | Отдел продаж |
| rop2@trainer.local | Rop2!pass | rop | Отдел B2B |
| method@trainer.local | Method!1 | methodologist | — |
| manager1@trainer.local | Mgr1!pass | manager | Отдел продаж |
| manager2@trainer.local | Mgr2!pass | manager | Отдел продаж |
| manager3@trainer.local | Mgr3!pass | manager | Отдел B2B |
| manager4@trainer.local | Mgr4!pass | manager | Отдел B2B |

---

## БЛОК 8: WebSocket ПРОТОКОЛ (обновления)

### Новые типы сообщений (сервер → клиент)

| Тип | Когда | Данные |
|---|---|---|
| `session.started` | После session.start | + `client_card` (CRM данные) |
| `trap.detected` | Когда менеджер попал/избежал ловушку | `{trap_name, caught, bonus/penalty, message}` |
| `hint.objection` | Через 1 мин | `{category: "trust", message: "Возражение: доверие"}` |
| `hint.checkpoint` | Через 3 мин | `{checkpoint: "Презентация", status: "not_reached"}` |
| `soft_skills.update` | Каждые 2 мин | `{talk_ratio, avg_response_time, name_count}` |

### Emotion engine v2
`emotion.update` теперь может содержать доп. инфо:
```json
{
  "type": "emotion.update",
  "data": {
    "previous": "cold",
    "current": "skeptical",
    "archetype": "skeptic",
    "trigger": "facts"
  }
}
```

---

## ПРИОРИТЕТЫ РЕАЛИЗАЦИИ

| Приоритет | Что делать | Файлы |
|---|---|---|
| 🔴 P0 | Web Speech API → STT | `training/[id]/page.tsx`, `CrystalMic.tsx` |
| 🔴 P0 | Web Speech API → TTS | `training/[id]/page.tsx` |
| 🔴 P0 | CRM-карточка перед тренировкой | `training/ClientCard.tsx` NEW |
| 🔴 P0 | Сценарии из API (8 карточек) | `training/page.tsx`, `ScenarioCard.tsx` NEW |
| 🟡 P1 | Token refresh interceptor | `lib/api.ts` |
| 🟡 P1 | WebSocket reconnect | `training/[id]/page.tsx` |
| 🟡 P1 | Trap notifications | `training/TrapNotification.tsx` NEW |
| 🟡 P1 | Расширенные результаты | `results/[id]/page.tsx` |
| 🟠 P2 | Назначенные тренировки | `training/page.tsx` |
| 🟠 P2 | Dashboard расширение (РОП + слабые места) | `dashboard/page.tsx` |
| 🟠 P2 | Onboarding: React Hook Form + Zod | `onboarding/page.tsx` |
| 🟢 P3 | Gamification → real API | `components/gamification/*` |
| 🟢 P3 | Лидерборд из API | `leaderboard/page.tsx` |

---

*Бэкенд полностью готов. Все endpoints протестированы. 71 unit test зелёные. БД содержит: 8 users, 8 scenarios, 5 characters, 32 professions, 15 traps, 5 objection chains, 10 achievements.*
