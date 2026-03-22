/**
 * Shared utility functions for the frontend.
 */

/** Returns a CSS color string based on score value. Theme-aware via CSS variables. */
export function scoreColor(score: number | null): string {
  if (score === null || score === undefined) return "var(--text-muted)";
  if (score >= 70) return "var(--neon-green)";
  if (score >= 40) return "var(--neon-amber)";
  return "var(--neon-red)";
}

/** Format duration in seconds to "M:SS" string */
export function formatDuration(seconds: number | null): string {
  if (!seconds) return "—";
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
