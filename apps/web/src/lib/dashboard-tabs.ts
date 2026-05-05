/**
 * Pure helpers for the dashboard's URL-driven tab/sub-tab routing.
 * Lives outside the page component so it can be unit-tested without
 * mounting React, and so that `MethodologyPanel` / `SystemPanel` can
 * reuse the same alias logic if needed.
 *
 * The router for the dashboard is a hand-rolled `?tab=…&sub=…` scheme
 * (rather than nested Next.js routes) because the panels share a chrome
 * — switching tabs should not unmount the chrome.
 *
 * Two requirements drove the helpers:
 *   1. A renamed tab id (`methodology` → `content`) must keep working
 *      via permanent server redirects on real URLs and via in-app
 *      alias on cached SPA state. We map legacy id → canonical id.
 *   2. A garbage / retired id (`?tab=garbage`, `?tab=scoring`) must
 *      not strand the user on a blank panel — we fall back to
 *      `overview` and rewrite the URL accordingly.
 */

export type TabId =
  | "overview"
  | "team"
  | "tournament"
  | "audit"
  | "content"
  | "reports"
  | "system";

/**
 * Legacy → canonical mapping. Server-side redirects in next.config.ts
 * handle real URLs (404→canonical), but in-app `replaceState` and any
 * cached SPA state can still hand us a legacy id; we normalise on read.
 *
 * 2026-05-05 cleanup:
 *   - `methodology` → `content` (operator-friendly noun).
 *   - `analytics`   → merged into `team`.
 *   - `activity`    → renamed to `audit` (label was misleading).
 */
export const TAB_ALIASES: Readonly<Record<string, TabId>> = {
  methodology: "content",
  analytics: "team",
  activity: "audit",
};

const KNOWN_TABS: ReadonlySet<TabId> = new Set([
  "overview",
  "team",
  "tournament",
  "audit",
  "content",
  "reports",
  "system",
]);

/**
 * Resolve a raw `?tab=…` query value to a renderable {@link TabId}.
 *
 *   resolveTabParam(null)            // → null  (no tab in URL → keep current state default)
 *   resolveTabParam("content")       // → "content"
 *   resolveTabParam("methodology")   // → "content"   (legacy alias)
 *   resolveTabParam("garbage")       // → "overview"  (unknown → safe fallback)
 *   resolveTabParam("scoring")       // → "overview"  (retired tab → safe fallback)
 *
 * The page combines this with `rawTabParam !== resolved` to decide
 * whether to rewrite the URL bar, so the address always matches the
 * rendered tab.
 */
export function resolveTabParam(raw: string | null): TabId | null {
  if (raw === null || raw === "") return null;
  const aliased = TAB_ALIASES[raw] ?? raw;
  if ((KNOWN_TABS as Set<string>).has(aliased)) return aliased as TabId;
  return "overview";
}

/**
 * SystemPanel sub-tab IDs. `client_domain` and `runtime` were renamed
 * to user-facing names (events / health) on 2026-05-05.
 */
export type SystemSubTab = "users" | "events" | "health";

export const SYSTEM_SUB_ALIASES: Readonly<Record<string, SystemSubTab>> = {
  client_domain: "events",
  runtime: "health",
};

const KNOWN_SYSTEM_SUBS: ReadonlySet<SystemSubTab> = new Set([
  "users",
  "events",
  "health",
]);

/**
 * Resolve a `?sub=…` value inside the System tab. Same shape as
 * {@link resolveTabParam}: legacy ids → canonical, unknown → fallback.
 *
 *   resolveSystemSub(null)            // → "users"
 *   resolveSystemSub("client_domain") // → "events"
 *   resolveSystemSub("garbage")       // → "users"
 */
export function resolveSystemSub(raw: string | null): SystemSubTab {
  if (raw === null || raw === "") return "users";
  const aliased = SYSTEM_SUB_ALIASES[raw] ?? raw;
  if ((KNOWN_SYSTEM_SUBS as Set<string>).has(aliased)) return aliased as SystemSubTab;
  return "users";
}
