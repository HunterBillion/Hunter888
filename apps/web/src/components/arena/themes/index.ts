/**
 * Arena theme tokens — one palette per PvP mode.
 *
 * Sprint 1 (2026-04-20). User feedback: "меняться то что есть под
 * капотом, но я не вижу роста развития" — all 5 modes should feel like
 * one game with mode-specific accents, not five different products.
 *
 * Guideline: keep the UI layout IDENTICAL across modes (that's the
 * ArenaShell contract). Differentiate only through:
 *   - accent (main brand colour of the mode)
 *   - glow (emission tint for rings/shadows)
 *   - subtle mode-specific icon / label in the header
 *
 * Names match the mode values used by ArenaShell `mode` prop.
 */

export type ArenaMode = "arena" | "duel" | "rapid" | "pve" | "tournament";

export interface ArenaTheme {
  mode: ArenaMode;
  label: string;
  /** Primary accent — used for buttons, active tabs, audio player ring. */
  accent: string;
  /** Secondary glow colour for shadows and pulses. */
  glow: string;
  /** Short tagline shown under the mode name in the header. */
  tagline: string;
  /** lucide-react icon name string — looked up by ArenaHeader. */
  icon: string;
}

export const ARENA_THEMES: Record<ArenaMode, ArenaTheme> = {
  arena: {
    mode: "arena",
    label: "Арена знаний",
    accent: "#a78bfa",   // violet — matches the global brand
    glow: "rgba(167,139,250,0.45)",
    tagline: "PvP-битва по 127-ФЗ",
    icon: "Swords",
  },
  duel: {
    mode: "duel",
    label: "Дуэль 1×1",
    accent: "#fb923c",   // orange — combat intensity
    glow: "rgba(251,146,60,0.45)",
    tagline: "Сделка в прямом эфире",
    icon: "Flame",
  },
  rapid: {
    mode: "rapid",
    label: "Rapid Fire",
    accent: "#facc15",   // yellow — speed / urgency
    glow: "rgba(250,204,21,0.5)",
    tagline: "Серия коротких раундов",
    icon: "Zap",
  },
  pve: {
    mode: "pve",
    label: "PvE — Тренажёр",
    accent: "#22d3ee",   // cyan — practice / low-stakes
    glow: "rgba(34,211,238,0.4)",
    tagline: "Бой с ботом против лестницы",
    icon: "Bot",
  },
  tournament: {
    mode: "tournament",
    label: "Турнир",
    accent: "#fbbf24",   // gold — prestige
    glow: "rgba(251,191,36,0.5)",
    tagline: "Плей-офф сезон",
    icon: "Trophy",
  },
};

export function themeFor(mode: ArenaMode): ArenaTheme {
  return ARENA_THEMES[mode] ?? ARENA_THEMES.arena;
}
