/**
 * Per-manager KPI targets — Команда v2 follow-up.
 *
 * Endpoints from `app/api/team_kpi.py`:
 *   GET    /team/users/{user_id}/kpi   — read one
 *   GET    /team/kpi                    — bulk read for caller's team
 *   PATCH  /team/users/{user_id}/kpi   — partial update (set/clear)
 *   DELETE /team/users/{user_id}/kpi   — clear all targets
 */
import { api } from "@/lib/api";

export interface KpiTarget {
  user_id: string;
  target_sessions_per_month: number | null;
  target_avg_score: number | null;
  target_max_days_without_session: number | null;
  updated_by: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface KpiTargetBulk {
  targets: KpiTarget[];
}

export interface KpiTargetPatch {
  target_sessions_per_month?: number | null;
  target_avg_score?: number | null;
  target_max_days_without_session?: number | null;
}

export const fetchKpiTarget = (userId: string): Promise<KpiTarget> =>
  api.get<KpiTarget>(`/team/users/${userId}/kpi`);

export const fetchTeamKpiTargets = (): Promise<KpiTargetBulk> =>
  api.get<KpiTargetBulk>("/team/kpi");

export const updateKpiTarget = (
  userId: string,
  patch: KpiTargetPatch,
): Promise<KpiTarget> =>
  api.patch<KpiTarget>(`/team/users/${userId}/kpi`, patch);

export const clearKpiTarget = (userId: string): Promise<void> =>
  api.delete<void>(`/team/users/${userId}/kpi`);

/**
 * Helper: classify progress against a target.
 *   "no_target" — null target → don't show indicator
 *   "ahead"     — actual meets/exceeds target
 *   "behind"    — actual misses target (red)
 *   "no_data"   — actual is null (e.g. brand new manager, never trained)
 */
export type KpiStatus = "no_target" | "ahead" | "behind" | "no_data";

/** "Higher is better" axis (e.g. sessions count, avg score). */
export function kpiStatusGreaterIsBetter(
  actual: number | null,
  target: number | null,
): KpiStatus {
  if (target === null || target === undefined) return "no_target";
  if (actual === null || actual === undefined) return "no_data";
  return actual >= target ? "ahead" : "behind";
}

/** "Lower is better" axis (e.g. days since last session — fewer = good). */
export function kpiStatusLowerIsBetter(
  actual: number | null,
  target: number | null,
): KpiStatus {
  if (target === null || target === undefined) return "no_target";
  if (actual === null || actual === undefined) return "no_data";
  return actual <= target ? "ahead" : "behind";
}
