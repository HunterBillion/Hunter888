/**
 * Centralised design & runtime constants for the Hunter888 web app.
 *
 * Why: magic numbers, easing curves, localStorage keys and colour literals
 * were scattered across 20+ files. A single source of truth prevents silent
 * breakage (e.g. a typo in a storage key) and keeps future refactors safe.
 */

/* ── Easing curves ─────────────────────────────────────────────────── */

export const EASINGS = {
  /** Snappy overshoot — hero animations, portal, page entrances */
  smooth: [0.16, 1, 0.3, 1] as const,
  /** Elastic bounce — playful interactions, celebratory feedback */
  bounce: [0.34, 1.56, 0.64, 1] as const,
  /** Deceleration — scroll reveals, gentle stops */
  decel: [0, 0.55, 0.45, 1] as const,
  /** Standard Material-style — modals, drawers, overlays */
  standard: [0.4, 0, 0.2, 1] as const,
  /** Gentle ease-in-out — confetti physics, ambient motion */
  gentle: [0.25, 0.46, 0.45, 0.94] as const,
} as const;

/** @deprecated Use `EASINGS.smooth` instead */
export const EASE_SNAP: [number, number, number, number] = [0.16, 1, 0.3, 1];
/** @deprecated Use `EASINGS.standard` instead */
export const EASE_STANDARD: [number, number, number, number] = [0.4, 0, 0.2, 1];
/** @deprecated Use `EASINGS.gentle` instead */
export const EASE_GENTLE: [number, number, number, number] = [0.25, 0.46, 0.45, 0.94];

/* ── Timing (ms) ───────────────────────────────────────────────────── */

export const TIMING = {
  PORTAL_ANIMATION: 800,
  STAGGER_DELAY: 300,
  CARD_DELAY: 600,
  SECTION_DELAY: 1000,
  WELCOME_DELAY: 2500,
  SESSION_TIMEOUT: 1800,
  TIMER_WARNING: 1500,
  LOADING_TIP_INTERVAL: 4000,

  /** Full portal entry animation before dismissal */
  portalDuration: 1800,
  /** Delay before showing welcome toast after portal */
  welcomeDelay: 300,
  /** Welcome toast auto-dismiss */
  welcomeAutoDismiss: 4000,
  /** Delay before showing daily challenge popup */
  challengeDelay: 2500,
  /** Stagger increment for card/list item entrances */
  staggerStep: 0.07,
} as const;

/* ── localStorage / sessionStorage keys ──────────────────────────── */

export const STORAGE_KEYS = {
  PORTAL_SHOWN: 'vh_portal_shown',
  WELCOME_SHOWN: 'vh_welcome_shown',
  LAST_CHALLENGE: 'vh_last_challenge',
  VISIT_COUNT: 'vh_visit_count',
  SHORTCUT_DISMISSED: 'vh_shortcut_dismissed',
  STREAK_CELEBRATED: 'vh_streak_celebrated',
  THEME: 'vh_theme',
  SOUND_ENABLED: 'vh_sound_enabled',
  REDUCED_MOTION: 'vh_reduced_motion',
} as const;

/** @deprecated Use `STORAGE_KEYS` instead — kept for backward compat */
export const STORAGE = {
  // Auth
  refreshToken: 'vh_rt',
  authenticated: 'vh_authenticated',

  // UI state (sessionStorage)
  portalShown: 'vh_portal_shown',
  welcomeShown: 'vh_welcome_shown',
  landingIntro: 'vh_landing_intro',

  // Persistent preferences (localStorage)
  lastChallenge: 'vh_last_challenge',
  micTooltipSeen: 'vh_mic_tooltip_seen',
  soundsMuted: 'vh-sounds-muted',
  accent: 'vh-accent',
  compact: 'vh-compact',
  theme: 'vh-theme',

  // Feature discovery
  shortcutHintVisits: 'vh_shortcut_hint_visits',
} as const;

/* ── Rank colours ─────────────────────────────────────────────────── */

export const RANK_COLORS = {
  gold: { primary: '#FFD700', bg: 'rgba(212,168,75,0.1)', border: 'rgba(212,168,75,0.3)' },
  silver: { primary: '#C0C0C0', bg: 'rgba(192,192,192,0.1)', border: 'rgba(192,192,192,0.3)' },
  bronze: { primary: '#CD7F32', bg: 'rgba(205,127,50,0.1)', border: 'rgba(205,127,50,0.3)' },
} as const;

/** @deprecated Use `RANK_COLORS` instead */
export const RANK = {
  gold: '#FFD700',
  goldRgba: (a: number) => `rgba(255, 215, 0, ${a})`,
  silver: '#C0C0C0',
  silverRgba: (a: number) => `rgba(192, 192, 192, ${a})`,
  bronze: '#CD7F32',
  bronzeRgba: (a: number) => `rgba(205, 127, 50, ${a})`,
} as const;

/* ── Streak colours ───────────────────────────────────────────────── */

export const STREAK = {
  color: '#FF9900',
  light: '#FFB347',
  rgba: (a: number) => `rgba(255, 153, 0, ${a})`,
} as const;

/* ── Streak milestones ────────────────────────────────────────────── */

export const STREAK_MILESTONES = [7, 14, 30, 60, 100] as const;

/* ── Difficulty tiers ─────────────────────────────────────────────── */

export const DIFFICULTY_TIERS = {
  easy: { label: 'Легко', emoji: '🟢', color: 'var(--success)', range: [1, 3] },
  medium: { label: 'Средне', emoji: '🟡', color: 'var(--warning, #F59E0B)', range: [4, 6] },
  hard: { label: 'Сложно', emoji: '🔴', color: 'var(--danger, #FF3333)', range: [7, 9] },
  boss: { label: 'Босс', emoji: '💀', color: '#A855F7', range: [10, 10] },
} as const;

/* ── Gamification ─────────────────────────────────────────────────── */

export const XP_BAR_SEGMENTS = 12;

/* ── Helpers ──────────────────────────────────────────────────────── */

/** Returns a time-of-day greeting in Russian. */
export function getTimeGreeting(): string {
  const hour = new Date().getHours();
  if (hour >= 5 && hour < 12) return 'Доброе утро';
  if (hour >= 12 && hour < 17) return 'Добрый день';
  if (hour >= 17 && hour < 22) return 'Добрый вечер';
  return 'Доброй ночи';
}

/** Maps a score/max pair to a Russian grade label. */
export function getGradeLabel(score: number, max: number): string {
  const pct = max > 0 ? (score / max) * 100 : 0;
  if (pct >= 90) return 'Отлично';
  if (pct >= 70) return 'Хорошо';
  if (pct >= 50) return 'Средне';
  if (pct >= 30) return 'Слабо';
  return 'Критично';
}

/** Returns a CSS color variable matching the grade tier. */
export function getGradeColor(score: number, max: number): string {
  const pct = max > 0 ? (score / max) * 100 : 0;
  if (pct >= 90) return 'var(--success)';
  if (pct >= 70) return 'var(--accent, #6366F1)';
  if (pct >= 50) return 'var(--warning, #F59E0B)';
  if (pct >= 30) return 'var(--danger, #FF3333)';
  return '#FF0040';
}
