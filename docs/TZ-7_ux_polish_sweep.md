# ТЗ-7 — UX polish sweep: Russification, шрифты, подсказки

> **Статус:** проектируется. Rev. 1: 2026-04-29. Rev. 2: 2026-04-29 после code audit.
> **Триггер:** пользователь зашёл на платформу 2026-04-29 и обнаружил массу мелких английских слов, недостаточно крупный шрифт, отсутствующие подсказки на админских surface'ах.
>
> ⚠️ **Корректировки rev. 2:**
> - Tooltip-инфраструктура **уже существует**: `Tooltip.tsx` (Radix), `InfoButton.tsx`, `PixelInfoButton.tsx`. Используется в **6 компонентах** /dashboard (`ClientDomainPanel`, `TeamTrendChart`, `ActivityChart`, `wiki/WikiChartsSection`, `wiki/HealthTab`, `wiki/ManagerListView`). Задача — **расширить покрытие**, не «построить с нуля».
> - Шрифт `xs` **уже подняли** с 12px до 14px (см. `tailwind.config.ts:69` — комментарий «// 14px min (was 12px)»). Дальнейший bump (xs 14→15, sm 14→16) требует обоснования; WCAG AA на 14px уже проходит. Если делаем — только после контраст-аудита.
> - Грубый подсчёт **187 hard-coded английских строк** через regex — корректен по порядку величины, но включает enum-значения (`"Default"`, `"Outline"`). Истинный объём UI-копии для перевода — ~120-150 строк.

## 1. Контекст

Платформа разработана с английскими identifier'ами в коде (`Blocked starts`, `Idempotent finalize`, `Follow-up gap`) которые **протекли в UI**. Менеджеры/ROP русские — английский UI создаёт когнитивную нагрузку и ощущение «недоделано».

В этой сессии (2026-04-29) были точечно исправлены:
- `/dashboard?tab=system` Runtime Metrics → русифицирован
- `/results/[id]` `LOST CONTROL` → `ПОТЕРЯЛ КОНТРОЛЬ` + пиксельный шрифт VT323

Но это первый виток. Требуется **системный** sweep.

## 2. Что включает sweep

### 2.1 Russification audit

Прогнать grep по `apps/web/src/` на все hard-coded английские строки:
```bash
grep -rn '"[A-Z][a-z]\+\([ A-Za-z]\+\)\?"' apps/web/src/components apps/web/src/app
```

Категоризация:
- **UI labels** (заголовки, кнопки, badges) → перевести
- **Tooltips / hints** → перевести
- **Empty states** ("No data", "Nothing to show") → перевести
- **Error messages** → перевести (или взять из `messages.errors.ru`)
- **Identifiers** (CSS классы, data-attrs, debug logs) → оставить английскими
- **Code-style fixed names** (`runtime_blocked_starts_total`) → оставить как есть, добавить human-readable label рядом

Ожидаемый объём: ~150-200 строк правок.

### 2.2 Размер шрифта

Сейчас в Tailwind config `xs: 14px` (увеличено с 12px). Глобальный bump по shкале:
- `xs` 14 → 15px
- `sm` 14 → 16px
- `base` 16 → 17-18px

Тест: открыть на 13" MacBook + 27" 4K-мониторе. Текст должен читаться без squinting.

Также: проверить контраст (`text-muted` иногда даёт контраст ниже WCAG AA на dark theme).

### 2.3 Tooltips на /dashboard (extend coverage)

**Использовать уже существующие компоненты:**
- `apps/web/src/components/ui/InfoButton.tsx` — стандартный «i» (40 строк, готов)
- `apps/web/src/components/ui/PixelInfoButton.tsx` — пиксельный вариант для геймифицированных surface'ов (263 строки, готов)
- `apps/web/src/components/ui/Tooltip.tsx` — Radix-обёртка под капотом (39 строк)

Уже подключены в 6 файлах. Расширить ещё на ~24 surface'а (admin-формы, тёмные сабтабы вне wiki, settings).

Каждый surface admin/ROP получает `<InfoButton />` с **расширенной** подсказкой:
- Что эта панель показывает
- Откуда берутся данные
- Что делать если что-то «странное»
- Ссылку на соответствующий ТЗ-документ для углубления

Стиль подсказок — пиксельный «i» (как просил пользователь):
```tsx
<button className="font-pixel text-base ..." aria-describedby="tip-runtime-metrics">i</button>
<Tooltip id="tip-runtime-metrics">
  <h4>Телеметрия выполнения сессий</h4>
  <p>Показывает сколько сессий завершилось, сколько защит сработало,
     сколько задач на повторный звонок не создалось — за период с
     момента запуска api-сервера. Подробнее: ТЗ-2 §18.</p>
</Tooltip>
```

Surfaces которые получат подсказки:
- `/dashboard` overview tabs (Команда / Активность / Методология / Система)
- Каждый sub-tab (Сценарии, Скоринг, Wiki, Reviews, Качество AI, Runtime Metrics, Client Domain, ...)
- Каждый виджет внутри (heatmap, weak-links, ROI, benchmark)

Итого ~30 подсказок.

### 2.4 Pixel font detail на /results

Уже сделано (этой сессии — `font-pixel` + `WebkitFontSmoothing: none`). Дополнения:

- Phase 1 (count-up) — добавить пиксельную тень (`text-shadow` cluster для эффекта CRT)
- Phase 3 (details) — кнопка «Разбор полёта» тоже пиксельная
- Звуковой эффект при появлении глитча — добавить в `useSound` (`pixel_appear.wav`)

### 2.5 Проверка по ролям

Системный test plan: пройти по платформе как **каждая роль** (manager, rop, admin) и зафиксировать **каждое** английское слово. Использовать `playwright` для автоматизации.

Сделать `tests/visual/russification_check.spec.ts` который ходит по всем routes и грепает на text-content страницы.

## 3. Acceptance criteria

- [ ] grep по `apps/web/src/` на латинские слова в hard-coded JSX даёт ≤ 20 hits (только идентификаторы)
- [ ] **Каждый** sub-tab `/dashboard` имеет визуальный «i» с подсказкой
- [ ] Открытая страница `/results/[id]` визуально читается с расстояния 1м (тестируется на пилоте)
- [ ] Контраст всего текста проходит WCAG AA (`axe-core` audit clean)
- [ ] Тестер-новичок (не разработчик) понимает что показывает каждая панель админа без объяснений

## 4. Какой эффект на пилоте

До TZ-7:
- ROP видит "Idempotent finalize" — спрашивает «что это?»
- Пользователь читает мелкий текст щурясь
- Без подсказок не очевидно, что делать с числами

После TZ-7:
- Полностью русский UI с понятными названиями
- Шрифт читается без напряжения
- Каждый виджет «объясняет себя» через «i» tooltip

## 5. Объём работы

- Russification grep + правки: 1.5 дня
- Tooltip система + ~30 подсказок: 2 дня
- Шрифт bump + контраст audit: 0.5 дня
- Pixel font polish на /results: 0.5 дня
- Playwright russification check: 1 день

Итого: **~5-6 дней** работы.

## 6. Что НЕ делаем в TZ-7

- Не меняем структуру навигации (это отдельный UX redesign)
- Не делаем dark/light theme switcher (отдельный TZ)
- Не переписываем компоненты на дизайн-систему — только текстовые правки + tooltips
- Не трогаем landing page (она и так в порядке)

## 7. Связь с другими ТЗ

- TZ-4.5 (persona memory) добавит новые admin surfaces → нужно сразу с подсказками
- TZ-5 (input funnel) добавит `/dashboard/methodology/scenarios/import` → нужно с подсказками
- TZ-6 (performance) изменит /dashboard/system/runtime-metrics → возможно повлияет на тексты

Поэтому TZ-7 имеет смысл делать **после** TZ-4.5 и TZ-6 (или параллельно), но **до** TZ-5 (input funnel).
