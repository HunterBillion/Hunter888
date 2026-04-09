/**
 * Shared utility functions for the frontend.
 */

/** Returns a CSS color string based on score value. Theme-aware via CSS variables. */
export function scoreColor(score: number | null): string {
  if (score === null || score === undefined) return "var(--text-muted)";
  if (score >= 70) return "var(--success)";
  if (score >= 40) return "var(--warning)";
  return "var(--danger)";
}

/**
 * Returns a score tier label for accessibility (not color-dependent).
 * Use alongside scoreColor to ensure color-blind users can interpret scores.
 */
export function scoreTier(score: number | null): { label: string; icon: "good" | "mid" | "low" | "none" } {
  if (score === null || score === undefined) return { label: "—", icon: "none" };
  if (score >= 70) return { label: "Отлично", icon: "good" };
  if (score >= 40) return { label: "Средне", icon: "mid" };
  return { label: "Слабо", icon: "low" };
}

/**
 * Create a semi-transparent version of a CSS color (works with both hex and var()).
 * Uses color-mix() which is supported in all modern browsers.
 * @param color - CSS color value (hex like "#FF3333" or var() like "var(--accent)")
 * @param percent - opacity percentage (0-100), e.g. 10 = 10% opaque
 */
export function colorAlpha(color: string, percent: number): string {
  return `color-mix(in srgb, ${color} ${percent}%, transparent)`;
}

/** Format duration in seconds to "M:SS" string */
export function formatDuration(seconds: number | null): string {
  if (seconds === null || seconds === undefined) return "—";
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
}

/** Format ISO date string to Russian short format */
export function formatDateRu(iso: string): string {
  return new Date(iso).toLocaleDateString("ru-RU", {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}
