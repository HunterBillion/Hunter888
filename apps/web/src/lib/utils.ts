/**
 * Shared utility functions for the frontend.
 */

import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/** Merge Tailwind classes with clsx */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

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
 * @param color - CSS color value (hex like "var(--danger)" or var() like "var(--accent)")
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

/**
 * Russian date-time formatters — single source of truth for the dashboard
 * surface. Before 2026-05-05 there were ~7 different date formats across
 * the panels (5 мая / 05.05.2026 / 05.05.2026, 14:30:11 / 05 мая 14:30 …).
 * Use one of the named variants below so labels look uniform.
 *
 * All variants parse "YYYY-MM-DD" date-only strings as local-day (not UTC),
 * preventing the "5 мая renders as 4 мая" bug for browsers west of UTC.
 */

function parseLocal(iso: string): Date {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
  if (m) {
    return new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
  }
  return new Date(iso);
}

/** "5 мая" — short, month-name day-number. */
export function formatDateShort(iso: string): string {
  return parseLocal(iso).toLocaleDateString("ru-RU", { day: "numeric", month: "short" });
}

/** "05.05.2026" — numeric, no time. */
export function formatDateFull(iso: string): string {
  return parseLocal(iso).toLocaleDateString("ru-RU", { day: "2-digit", month: "2-digit", year: "numeric" });
}

/** "05.05.2026, 14:30" — for tables / list rows. */
export function formatDateTime(iso: string): string {
  return parseLocal(iso).toLocaleString("ru-RU", {
    day: "2-digit", month: "2-digit", year: "numeric",
    hour: "2-digit", minute: "2-digit",
  });
}

/** "05.05.2026, 14:30:11" — for audit log / forensics. */
export function formatDateTimeFull(iso: string): string {
  return parseLocal(iso).toLocaleString("ru-RU", {
    day: "2-digit", month: "2-digit", year: "numeric",
    hour: "2-digit", minute: "2-digit", second: "2-digit",
  });
}

/**
 * @deprecated mixes a short date with a time — rarely the right choice.
 * Prefer formatDateShort / formatDateTime / formatDateTimeFull.
 */
export function formatDateRu(iso: string): string {
  return new Date(iso).toLocaleDateString("ru-RU", {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}
