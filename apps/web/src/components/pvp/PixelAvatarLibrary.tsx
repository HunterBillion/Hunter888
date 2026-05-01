"use client";

/**
 * PixelAvatarLibrary — публичный API библиотеки 12 пиксельных аватаров.
 *
 * ╔══════════════════════════════════════════════════════════════════════╗
 * ║   <<< THIS FILE IS THE DEVELOPER ZONE >>>                            ║
 * ║                                                                      ║
 * ║   Художник этот файл НЕ редактирует. Здесь только:                  ║
 * ║   - Тип PixelAvatarCode                                              ║
 * ║   - Компонент <PixelPortrait>                                        ║
 * ║   - Hook usePlayerAvatar() (по level)                                ║
 * ║   - ARCHETYPE_TO_AVATAR маппинг                                      ║
 * ║   - resolveOpponentAvatar() helper                                   ║
 * ║                                                                      ║
 * ║   Спрайты + палитра живут в PixelAvatarSprites.ts (artist zone).    ║
 * ║   ТЗ: apps/web/src/styles/PIXEL_TOKENS.md §11.                      ║
 * ╚══════════════════════════════════════════════════════════════════════╝
 *
 * 2026-05-01: первая реализация.
 */

import * as React from "react";
import {
  type PvPRankTier,
  PVP_RANK_COLORS,
  normalizeRankTier,
} from "@/types";
import { SPRITES, PALETTE } from "./PixelAvatarSprites";

/* ── Public types ───────────────────────────────────── */

/**
 * 12 канонических кодов аватаров. Расширять — только синхронно с
 * PixelAvatarSprites.ts (см. блок-комментарий в EXPORT MAP).
 */
export type PixelAvatarCode =
  // PLAYER (4)
  | "rookie"
  | "operator"
  | "senior"
  | "lead"
  // CLIENT — middle-aged (5)
  | "mother"
  | "driver"
  | "teacher"
  | "entrepreneur"
  | "single_man"
  // CLIENT — senior 60+ (3)
  | "grandma"
  | "grandpa_worker"
  | "vet";

/** Все 12 кодов в массиве — для итерации (demo, leaderboard). */
export const ALL_AVATAR_CODES: PixelAvatarCode[] = [
  "rookie", "operator", "senior", "lead",
  "mother", "driver", "teacher", "entrepreneur", "single_man",
  "grandma", "grandpa_worker", "vet",
];

/** Player vs Client принадлежность (для UI логики). */
export const PLAYER_AVATARS: ReadonlySet<PixelAvatarCode> = new Set<PixelAvatarCode>([
  "rookie", "operator", "senior", "lead",
]);
export function isPlayerAvatar(code: PixelAvatarCode): boolean {
  return PLAYER_AVATARS.has(code);
}

/* ── Color helpers ──────────────────────────────────── */

function tierColorOf(tier?: PvPRankTier | string): string {
  if (!tier) return "var(--text-muted)";
  const norm = normalizeRankTier(typeof tier === "string" ? tier : tier);
  return PVP_RANK_COLORS[norm] ?? "var(--text-muted)";
}

/**
 * Резолвит цвет литерала. Для `t` И `r` — подменяет на tier-цвет.
 * Для всех остальных — возвращает hex из PALETTE.
 * Для `.` (transparent) — возвращает null чтобы пропустить рендер.
 *
 * Почему `r` тоже tier:
 *   §11.4 ТЗ формально перечисляет 19 литералов, но §11.5.2 описывает
 *   гарнитуру operator-а как "ободок гарнитуры (`r`)". Артист в
 *   PixelAvatarSprites.ts использует `r` в operator/senior/grandpa_worker
 *   именно для tier-акцентов на гарнитуре — это легаси-конвенция из
 *   старого `SPRITE_MANAGER` в DuelChat. Поэтому `r` ведёт себя как `t`.
 */
function resolveLiteralColor(ch: string, tier?: PvPRankTier | string): string | null {
  if (ch === "." || ch === undefined) return null;
  if (ch === "t" || ch === "r") return tierColorOf(tier);
  const hex = PALETTE[ch];
  if (!hex || hex === "transparent") return null;
  return hex;
}

/* ── PixelPortrait component ───────────────────────── */

interface PortraitProps {
  /** Один из 12 канонических кодов. */
  code: PixelAvatarCode;
  /** Размер CSS-пикселей (квадрат). По умолчанию 56. */
  size?: number;
  /**
   * Tier — используется ТОЛЬКО для подмены литерала `t` (player-аватары:
   * бейдж/галстук/ободок гарнитуры). Внутри client-спрайтов литерала `t`
   * не должно быть, поэтому tier на client визуально не повлияет.
   * Для рамки (outline) — оборачивай <PixelPortrait/> в твой <PixelAvatar/>.
   */
  tier?: PvPRankTier | string;
  /** Опциональный aria-label (если аватар несёт смысл, не декоративен). */
  label?: string;
}

/**
 * Рендерит 16×16 пиксель-портрет как inline SVG с rect-сеткой.
 * Использует image-rendering: pixelated, чтобы скейл выглядел чётко.
 */
export function PixelPortrait({
  code,
  size = 56,
  tier,
  label,
}: PortraitProps) {
  const sprite = SPRITES[code];
  // Defensive: если код не в map — fallback на operator (никаких 404).
  const safeSprite = sprite ?? SPRITES.operator;
  const cell = 100 / 16; // viewBox 0..100, ячейка 6.25%

  const rects: React.ReactElement[] = [];
  for (let y = 0; y < safeSprite.length; y += 1) {
    const row = safeSprite[y];
    for (let x = 0; x < row.length; x += 1) {
      const ch = row[x];
      const fill = resolveLiteralColor(ch, tier);
      if (!fill) continue;
      rects.push(
        <rect
          key={`${x}-${y}`}
          x={x * cell + "%"}
          y={y * cell + "%"}
          width={cell + "%"}
          height={cell + "%"}
          fill={fill}
          data-literal={ch}
        />,
      );
    }
  }

  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 100 100"
      preserveAspectRatio="xMidYMid meet"
      style={{ imageRendering: "pixelated", display: "block" }}
      role={label ? "img" : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
    >
      {rects}
    </svg>
  );
}

/* ── usePlayerAvatar hook ─────────────────────────── */

/**
 * Чистая функция: level → один из 4 player-аватаров.
 *   1-9   → rookie
 *   10-29 → operator
 *   30-59 → senior
 *   60+   → lead
 *
 * Не использует Zustand напрямую — просто принимает level. Parent читает
 * из `useAuthStore`/`useGamificationStore` и передаёт сюда.
 *
 * Для null/undefined/NaN/<1 — возвращает `operator` как нейтральный default,
 * чтобы новый игрок без level не получил ни «крутого» lead-а (визуально
 * ложно), ни «стажёра» (это уже лор-ассайн).
 */
export function avatarFromLevel(level: number | undefined | null): PixelAvatarCode {
  if (level == null || !Number.isFinite(level) || level < 1) return "operator";
  if (level >= 60) return "lead";
  if (level >= 30) return "senior";
  if (level >= 10) return "operator";
  return "rookie";
}

/**
 * React-hook вокруг `avatarFromLevel`. Стабильное мемоизированное значение —
 * не пересчитывается на ререндере, только при реальном изменении level.
 *
 * Использование в `/pvp/duel/[id]`:
 *   const selfAvatar = usePlayerAvatar(profile?.level);
 *   <FighterCard code={selfAvatar} ... />
 */
export function usePlayerAvatar(
  level: number | undefined | null,
): PixelAvatarCode {
  return React.useMemo(() => avatarFromLevel(level), [level]);
}

/* ── Archetype → avatar mapping ──────────────────── */

/**
 * Маппинг 25 архетипов из apps/web/src/lib/archetypes.ts → 8 client-аватаров.
 * Расширять при добавлении новых архетипов в lib/archetypes.ts.
 * Fallback на `operator` если ключ не найден.
 */
export const ARCHETYPE_TO_AVATAR: Record<string, PixelAvatarCode> = {
  // Resistance group
  skeptic: "grandpa_worker",
  blamer: "single_man",
  sarcastic: "entrepreneur",
  aggressive: "single_man",
  hostile: "single_man",
  stubborn: "grandpa_worker",
  doubting: "teacher",
  cold: "single_man",
  // Manipulation group
  manipulator: "entrepreneur",
  bargainer: "entrepreneur",
  promiser: "driver",
  // Emotional group
  tired_worker: "driver",
  defeated: "single_man",
  chronic_stress: "mother",
  emotional: "mother",
  panicking: "mother",
  // VIP group
  vip: "entrepreneur",
  wealthy_client: "entrepreneur",
  entrepreneur: "entrepreneur",
  // Senior group (3 portraits available)
  pensioner: "grandma",
  silver_hair: "grandpa_worker",
  veteran: "vet",
  retired_officer: "vet",
  scammed_pensioner: "grandma",
  // Closing group — clients (player-side `lead` исключаем)
  decisive: "entrepreneur",
  ready_to_close: "entrepreneur",
  // Teacher / budget worker
  teacher: "teacher",
  budget_worker: "teacher",
  // Family
  single_mother: "mother",
  multi_child: "mother",
};

/**
 * Берёт archetype-строку из бэка, возвращает безопасный код аватара.
 * Если archetype null/неизвестен — fallback на `operator` (нейтрально).
 */
export function resolveOpponentAvatar(
  archetype: string | null | undefined,
): PixelAvatarCode {
  if (!archetype) return "operator";
  const lower = archetype.toLowerCase().trim();
  return ARCHETYPE_TO_AVATAR[lower] ?? "operator";
}

/* ── Display labels (для demo / settings UI) ──────── */

export const AVATAR_LABELS: Record<PixelAvatarCode, { name: string; subtitle: string }> = {
  rookie: { name: "Стажёр", subtitle: "БФЛ-новичок, 22-25" },
  operator: { name: "Оператор", subtitle: "Колл-центр, 25-35" },
  senior: { name: "Старший менеджер", subtitle: "Эксперт, 30-40" },
  lead: { name: "Тимлид", subtitle: "Руководитель, 35-45" },
  mother: { name: "Мама-многодетная", subtitle: "30-42, кредиты на детей" },
  driver: { name: "Водитель", subtitle: "Такси/доставка, 28-45" },
  teacher: { name: "Учительница", subtitle: "Бюджетник, 35-55" },
  entrepreneur: { name: "Бывший ИП", subtitle: "35-55, закрытый бизнес" },
  single_man: { name: "Одинокий", subtitle: "35-50, в депрессии" },
  grandma: { name: "Бабушка", subtitle: "65-78, обманута мошенниками" },
  grandpa_worker: { name: "Дед-работяга", subtitle: "62-72, кредит на лекарства" },
  vet: { name: "Военный пенсионер", subtitle: "65-75, помог дочке" },
};
