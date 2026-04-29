# Pixel UI — каталог токенов и компонентов

> Создан 2026-04-29 как deliverable Фазы 1 плана визуальной перестройки PvP-арены.
> Единственная справочная страница перед тем, как начать строить новый UI боя.
> При расхождении между этим файлом и `pixel-ui.css` / `globals.css` — **источник истины
> всегда CSS**, файл обновляется вручную после рефакторов.

---

## 1. Где что лежит

| Слой | Файл | Назначение |
|---|---|---|
| Pixel-tokens | [src/styles/pixel-ui.css](pixel-ui.css) | CSS-переменные `--ui-*` (бордеры, тени, размеры кнопок, pixel-font scale) + готовые классы `.ui-pixel-card`, `.ui-btn`, `.ui-choice`, `.ui-input`, `.ui-badge`, `.ui-arcade-bg`. **Все новые pixel-сцены должны потреблять только это.** |
| Color tokens | [src/app/globals.css](../app/globals.css) | `--accent`, `--bg-panel`, `--rank-*`, `--gf-*`, light/dark переключение через `.dark` на `<html>`. |
| Component layer | [src/app/globals.css](../app/globals.css) `@layer components` | `.pixel-border`, `.pixel-shadow`, `.pixel-glow`, `.pixel-divider`, `.cyber-card`, `.glow-card`, `.btn-neon`, `.arena-grid-bg`, типографика `.t-kicker / .t-title / .t-card-title / .t-body / .t-label-mono`. |
| Tailwind | [tailwind.config.ts](../../tailwind.config.ts) | `font-pixel` → `var(--font-vt323)`, `font-mono` → Geist Mono, brand/violet/surface/vh-* палитра, `animate-fade-up / scale-in / shimmer / float`. |
| Шрифты | [src/app/layout.tsx](../app/layout.tsx) | `Geist`, `Geist_Mono`, `VT323` через `next/font/google`. **VT323 subset = `latin, latin-ext, vietnamese` — БЕЗ кириллицы** (см. §6 Риски). |
| Pixel-font для canvas | [src/lib/pixel-font.ts](../lib/pixel-font.ts) | Helper `pixelFont(size)` → строка для `ctx.font`, читает `--font-vt323` через `getComputedStyle`. |

---

## 2. Border / shadow / size

```
--ui-border-sm: 1px       минорные разделители
--ui-border-md: 2px       дефолтная пиксельная рамка
--ui-border-lg: 3px       CTA / focus / акцент

--ui-shadow-xs: 2px 2px 0 0 rgba(0,0,0,0.15)
--ui-shadow-sm: 2px 2px 0 0 var(--border-color)
--ui-shadow-md: 3px 3px 0 0 var(--accent)
--ui-shadow-lg: 4px 4px 0 0 #000
--ui-shadow-cta: 4px 4px 0 0 #000, 0 0 12px var(--accent-glow)
--ui-shadow-danger: 3px 3px 0 0 var(--danger)
--ui-shadow-warning: 3px 3px 0 0 var(--warning)
--ui-shadow-success: 3px 3px 0 0 var(--success)

--ui-btn-h-sm: 36px        icon-only / secondary
--ui-btn-h-md: 44px        дефолт
--ui-btn-h-lg: 52px        primary CTA
--ui-btn-h-xl: 64px        hero ("В БОЙ", "НАЧАТЬ")
--ui-tap-min: 48px         WCAG минимум

--ui-gap-sm/md/lg: 8 / 12 / 16

--ui-radius: 0             всегда квадрат, радиус — escape hatch
```

### Pattern: «3D-нажатие» из лобби

Используется на `.ui-btn` и в `PixelInfoButton`:

```css
hover:  transform: translate(-1px, -1px); box-shadow: 3px 3px 0 0 ...;
active: transform: translate(2px, 2px);   box-shadow: none;
```

Воспроизвести **дословно** на любых новых pixel-кнопках. Никаких `scale` / `borderRadius` транзишенов.

---

## 3. Типографика — какой класс когда

| Класс | Где | Пример |
|---|---|---|
| `.t-kicker` (11px, VT323, uppercase, ls 0.18em) | мини-капс над секцией | `SELECT MODE — PVP` |
| `.t-title` (15px, VT323, uppercase, ls 0.14em) | заголовок карточки/секции | «АРЕНА», «ЗНАНИЯ ФЗ-127» |
| `.t-card-title` (14px, default font) | имя режима внутри плитки | «КЛАССИЧЕСКАЯ» |
| `.t-body` (13px, default) | описание под заголовком | подсказка в карточке |
| `.t-label-mono` (11px, monospace) | таймеры / score-delta / статус-чипы | `00:42`, `+47 ELO` |
| `.font-pixel` Tailwind | прямой VT323 | заголовки `<h1>` лобби, label плиток |

### Font scale (`pixel-ui.css`)

```
--ui-pixel-xs: 11px        чипы / лейблы
--ui-pixel-sm: 13px        button default
--ui-pixel-md: 15px        button-lg / card title
--ui-pixel-lg: 18px        button-xl
--ui-pixel-xl: 24px        page H1
```

---

## 4. Pixel-классы и компоненты

### CSS-классы (use-as-is)

| Класс | Эффект | Где использовать |
|---|---|---|
| `pixel-border` | `outline: 2px solid var(--accent); outline-offset: -2px; border-radius: 0` | внешний контур любой пиксельной карточки. Поддерживает override `--pixel-border-color` через inline-style для перекраски (см. лобби, плитки PVE/PVP). |
| `pixel-border-stepped` | 4 угловых квадрата + outline | leaderboard top-3, pixijs контейнеры. **Не злоупотреблять** — для эмфазы. |
| `pixel-shadow` | `box-shadow: 2px 2px 0 0 rgba(0,0,0,0.3), 4px 4px 0 0 rgba(0,0,0,0.15)` | глубина под pixel-border |
| `pixel-glow` | `text-shadow: 0 0 4px var(--accent), 0 0 8px var(--accent-glow)` | заголовок, hover-text |
| `pixel-divider` | repeating-linear-gradient `border-color 8px / transparent 4px` | разделитель в pixel-стиле |
| `animate-steps` | `animation-timing-function: steps(8, end)` | sprite-feel анимации (важно для RoundIndicator/FighterCard) |
| `render-pixel` | `image-rendering: pixelated; image-rendering: crisp-edges` | `<canvas>`, `<img>` с пиксель-артом — **обязательно для арт-фонов** |
| `arena-grid-bg` / `app-grid-layer--arena` | сетка 32px + точечный декор | фон `/pvp` лобби. Заменим тиро-зависимым `<ArenaBackground>`. |
| `cyber-card` | glass-bg + blur + accent-border + hover lift | боковые панели лобби. **Не пиксель — оставить для лобби-чрома, не вносить в сцену дуэли.** |
| `glow-card` | контейнер с `glow-card-inner` (24px padding, blur) | premium-карточки лобби |
| `btn-neon` | brand button с `accent-glow` hover | fallback-кнопка лобби. Для арены лучше `.ui-btn--primary`/`.ui-btn--xl` (см. §2). |

### React-компоненты (готовые)

| Файл | Экспорт | Назначение |
|---|---|---|
| [src/components/ui/PixelInfoButton.tsx](../components/ui/PixelInfoButton.tsx) | `PixelInfoButton` | 36×36 квадратная кнопка `i` + Portal-modal с пиксельной рамкой. **Эталонный шаблон pixel-modal.** Скопировать структуру для VsBanner / VictoryScreen reveal. |
| [src/components/ui/ScreenShake.tsx](../components/ui/ScreenShake.tsx) | `ScreenShake` | Обёртка с shake-анимацией (использовать на FighterCard при `judge.score`, на цифрах таймера ≤3s). |
| [src/components/ui/Confetti.tsx](../components/ui/Confetti.tsx) | `Confetti` | Канвас-конфетти. Для promotion-фазы PvPVictoryScreen. |
| [src/components/pvp/RankBadge.tsx](../components/pvp/RankBadge.tsx) | `RankBadge` | Чип ранга с иконкой Shield + цветом из `PVP_RANK_COLORS`. **Текущая реализация — не пиксельная** (использует `rounded-xl`, `shadow blur`). Для арены нужна pixel-вариация: `borderRadius: 0`, тень `2px 2px 0 0 currentColor`. |

### Что **отсутствует** (нужно создать в Фазах 2-7)

- `PixelButton` — единого компонента нет. Сейчас `.ui-btn` через `className`. Если в Фазах 3-5 будем класть кнопки в JSX 5+ раз — обернуть в `<PixelButton size="md|lg|xl" variant="primary|danger">` для DRY.
- `PixelCard` — то же самое. Сейчас `<div className="ui-pixel-card">`.
- `<ArenaBackground tier>` — Фаза 6.
- `<FighterCard>`, `<VsBanner>`, `<HPBar>` — Фаза 3.

---

## 5. Тиры и цвета

Источник: [src/types/index.ts:1766](../types/index.ts:1766) (`PVP_RANK_COLORS`).

| Тир | Текущий цвет (token / hex) | План арены (Фаза 6) |
|---|---|---|
| `unranked` | `var(--text-muted)` | серый base |
| `iron` | `var(--text-muted)` | серо-коричневый, трещины, тусклый факел |
| `bronze` | `#B45309` | бронзовый, тёплый, колонны |
| `silver` | `var(--text-muted)` | серебристо-голубой, лёд, пар |
| `gold` | `var(--warning)` ≈ `#B07A10/E8A630` | золотой, орнамент, луч сверху |
| `platinum` | `#22D3EE` | аквамарин, хрусталь, осколки |
| `diamond` | `var(--info)` ≈ `#2563EB/5B9EE9` | голубой неон, glitch |
| `master` | `var(--danger)` ≈ `#C02228/E5484D` | пурпурная плазма, портал |
| `grandmaster` | `#FF6B35` | вулкан, лава, искры |

> **Внимание:** `silver` сейчас использует `var(--text-muted)` — то же что и `unranked`/`iron`. Для арены нужно различать: предлагаю отдельный `--rank-silver` (уже есть в globals.css: `#8E8EA0` light / `#B0B0C0` dark). Поднять флагом в Фазе 6 при создании `<ArenaBackground tier="silver">`.

### Дополнительные rank-токены (есть в globals.css, не используются в RankBadge)

```
--rank-gold: #B8922E (light) / #D4A84B (dark)
--rank-silver: #8E8EA0 / #B0B0C0
--rank-bronze: #A86E42 / #C8865A
--rank-platinum: #00CED1 / #48D1CC
--rank-diamond: #B9F2FF / #E0FCFF
--streak-color: #C48A15 / #E8A630
```

Перенести `RankBadge` на эти токены в рамках Фазы 6 (один раз — везде).

---

## 6. Риски и блокеры (выявлены аудитом)

### 6.1 VT323 не поддерживает кириллицу

- **Факт:** [layout.tsx:22](../app/layout.tsx:22) подгружает VT323 с subsets `["latin", "latin-ext", "vietnamese"]`.
- **Эффект:** русский текст в `font-pixel` (`АРЕНА`, `БОЙ`, `КО!`, `РАУНД 1`) падает на fallback `monospace` (Geist Mono / Courier New). Это **не** пиксель — глифы плавные.
- **Доказательство:** Открыть `/pvp` в DevTools → Computed `font-family` на элементе с `.font-pixel` для русского заголовка → видно, что фактически рендерится Geist Mono.
- **Варианты решения для Фаз 2-5:**
  1. **Pixelify Sans** (Google Fonts, есть subset `cyrillic`) — рекомендую. Загрузить через `next/font` рядом с VT323, добавить переменную `--font-pixel-cyrillic`, fallback-цепочка в `pixel-ui.css`: `var(--font-vt323), var(--font-pixel-cyrillic), monospace`. Браузер автоматически подберёт глиф из второго шрифта для кириллицы. ⚠ зависит от font-display и unicode-range — нужно настроить `unicode-range: U+0400-04FF` для кириллицы.
  2. **VT323 + custom Cyrillic glyphs** — реалистично только если есть дизайнер. Не рассматриваем.
  3. **Принять текущее поведение** (monospace для русского). Тогда в Фазах 2-5 нельзя использовать `font-pixel` на русском тексте крупнее 14px — не выглядит пиксельно, выглядит «как админка». Для надписей `KO!`, `VS`, `FIGHT!` — оставить **латиницу** или использовать английские термины.
- **Решение требуется до старта Фазы 2** (DuelChat будет показывать русский текст в пиксельных баблах).

### 6.2 Bundle size при 8 фоновых тайлах

- 8 фонов × ~50KB PNG = ~400KB — терпимо, но грузим только активный тир через `next/image priority={false}` или динамический `<link rel="preload">`. План в Фазе 6 это уже учитывает.

### 6.3 Несогласованность RankBadge и плана

- Текущий `RankBadge` (`rounded-xl`, `font-mono`, тени с blur) **не** пиксельный. Если используем его в FighterCard (Фаза 3) — будет визуальный конфликт. Опции:
  - В Фазе 3 написать `<PixelRankBadge>` с `borderRadius: 0`, `box-shadow: 2px 2px 0 0 currentColor`, `font-pixel` (с учётом 6.1 — латинская label, либо Pixelify Sans).
  - Либо целиком перевести `RankBadge` на pixel-стиль и согласовать с лобби (там 5+ мест использования — нужен grep).

### 6.4 `prefers-reduced-motion`

- Уже глобально обработан в `globals.css:1354` — анимации сжимаются до 0.01ms. Это значит: ScreenShake, Confetti, score-bump, pixel-glow text-shadow продолжат работать (не анимации в строгом смысле), но `animate-steps`, glitch-text — отключатся. Для Фаз 4-5 (typewriter, count-up) **обязательно** обернуть в проверку `useReducedMotion()` из framer-motion → если true, показывать финальное значение без интерполяции.

---

## 7. Сводная карта переиспользования по фазам

| Фаза | Что переиспользуем без правок | Что создаём новое |
|---|---|---|
| 2 (DuelChat) | `.ui-pixel-card`, `.t-body`, `font-pixel` (см. 6.1), `pixel-border`, `arena-grid-bg` для фона | spike-bubble shape (clip-path), typewriter hook, thinking-dots компонент |
| 3 (Сцена дуэли) | `.t-title`, `.t-label-mono`, `arena-grid-bg`, `pixel-border`, `ScreenShake` | `<ArenaBackground>`, `<FighterCard>`, `<HPBar>`, `<VsBanner>` |
| 4 (Timer) | `.t-label-mono`, `animate-steps`, `ScreenShake` | `<PixelRing segments={16}>`, `useDeadlineCountdown` |
| 5 (Victory) | `Confetti`, `pixel-glow`, `RankBadge` (или `<PixelRankBadge>` — см. 6.3) | 4-фазный orchestrator, count-up хук, KO! баннер |
| 6 (Тиры) | `PVP_RANK_COLORS` token map, `--rank-*` CSS vars | 8 PNG тайлов, `<ArenaBackground>` обёртка |
| 7 (Matchmaking) | `RankBadge`, `MatchmakingOverlay` host, `Confetti` опционально | `<MatchOpponentCard>`, `<PreMatchCountdown>` |
| 8 (Звук) | — | `<ArenaSoundProvider>`, Web Audio sprite engine, mute-toggle |

---

## 8. Чек-лист «не сломать существующее»

Перед merge любой PR Фаз 2-8:

- [ ] Лобби `/pvp` визуально не изменилось (открыть в обоих темах light/dark до и после).
- [ ] Никакие классы `.ui-*` / `.pixel-*` / `.cyber-card` / `.glow-card` / `.t-*` не отредактированы — только добавлены новые. Если редактировал — отдельный PR с обоснованием в описании.
- [ ] В новых компонентах все цвета — через `var(--*)` токены (никаких `#hex` инлайн, кроме случаев где сам токен это hex).
- [ ] Все размеры кнопок ≥ `--ui-tap-min` (48px) на тач-устройствах.
- [ ] Все анимации с длительностью >300ms имеют ветку `useReducedMotion()`.
- [ ] Все pixel-canvas / pixel-png имеют класс `.render-pixel`.
- [ ] Все `font-pixel` на русском тексте размером ≥14px — либо переведены на Pixelify Sans (если решение 6.1.1), либо переведены на латиницу/английские термины (если решение 6.1.3).

---

## 9. Команды для верификации (локально)

```bash
# Лобби — эталонный pixel-стиль
open http://localhost:3000/pvp

# Дуэль (текущее состояние, до Фаз 2-3) — для сравнения «до»
open http://localhost:3000/pvp/duel/test-id

# Каталог компонентов (если в проекте есть Storybook — проверить)
# Если нет — создание Storybook не входит в Фазу 1, но было бы +1 для Фаз 4-5.

# DevTools проверка кириллицы в font-pixel
# 1. Inspect <h1 class="font-pixel"> с русским текстом
# 2. Computed → font-family
# 3. Если фактический шрифт ≠ VT323 → подтверждение §6.1
```

---

## 10. Что НЕ покрыто этим документом

- Логика боя (WS, store, judge.score, finalize) — это домен `Hunter888/.claude/CLAUDE.md` §3.
- Backend payload schema (`match.found.opponent_id`) — Фаза 7 предполагает расширение, но это документ frontend-токенов.
- A11y критерии за пределами `prefers-reduced-motion` (контраст, фокус-кольцо) — есть в `globals.css:777` глобально, частная проверка делается в каждой PR Фазы.

---

**Готов к Фазе 2.** Перед стартом — нужно решение по §6.1 (кириллический pixel-font). Без него DuelChat в Фазе 2 либо будет на латинице, либо на Geist Mono (что = текущее состояние).
